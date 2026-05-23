"""High-level monitored webapp runtime orchestration."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from litlaunch.browsers import BrowserKind
from litlaunch.config import LauncherConfig, LaunchMode
from litlaunch.console import ConsolePhase
from litlaunch.exceptions import ConfigurationError
from litlaunch.launcher import StreamlitLauncher
from litlaunch.lifecycle import LaunchState
from litlaunch.platforms import PlatformDetector, PlatformInfo
from litlaunch.profiles import LaunchProfile
from litlaunch.runtime_console import (
    render_phase_start,
    render_phase_success,
    render_phase_warning,
    render_window_monitor_result,
)
from litlaunch.session import RuntimeSession
from litlaunch.windowing import (
    NoopWindowMonitor,
    WindowInfo,
    WindowMonitor,
    WindowMonitorConfig,
    WindowMonitorResult,
    WindowMonitorStatus,
    WindowTarget,
    create_window_monitor,
)


@dataclass(frozen=True)
class MonitoredRunResult:
    """Structured result for a monitored webapp run."""

    exit_code: int
    session: RuntimeSession | None
    monitor_result: WindowMonitorResult | None
    message: str
    launched: bool
    stopped_cleanly: bool


def run_monitored_webapp(
    launcher_or_config: StreamlitLauncher | LauncherConfig,
    *,
    window_monitor_config: WindowMonitorConfig | None = None,
    graceful_timeout_seconds: float = 3.0,
    platform_detector: PlatformDetector | None = None,
    window_monitor_factory: Callable[
        [PlatformInfo], WindowMonitor
    ] = create_window_monitor,
    monitor: WindowMonitor | None = None,
    launcher_factory: type[StreamlitLauncher] = StreamlitLauncher,
) -> MonitoredRunResult:
    """Run a webapp, observe its app-mode window, and stop backend on close.

    Window monitoring remains observation-only. Browser windows are not owned,
    killed, closed, or controlled by this helper.
    """

    launcher = _coerce_launcher(launcher_or_config, launcher_factory)
    if launcher.config.mode != LaunchMode.WEBAPP:
        raise ConfigurationError("run_monitored_webapp requires mode='webapp'.")
    if graceful_timeout_seconds <= 0:
        raise ConfigurationError("graceful_timeout_seconds must be positive.")

    config = window_monitor_config or WindowMonitorConfig()
    resolved_monitor = monitor or _create_monitor(
        platform_detector=platform_detector,
        window_monitor_factory=window_monitor_factory,
    )
    baseline_target = WindowTarget(launcher.config.title, app_mode=True)

    if isinstance(resolved_monitor, NoopWindowMonitor):
        result = resolved_monitor.wait_for_close(
            baseline_target,
            backend_is_running=lambda: False,
            config=config,
        )
        return MonitoredRunResult(
            exit_code=1,
            session=None,
            monitor_result=result,
            message="Monitor: window monitoring is unavailable.",
            launched=False,
            stopped_cleanly=True,
        )

    session: RuntimeSession | None = None
    try:
        baseline = resolved_monitor.capture(baseline_target)
    except Exception as exc:
        result = WindowMonitorResult(
            supported=False,
            observed=False,
            closed=False,
            status=WindowMonitorStatus.ERROR,
            message=f"Window monitoring baseline capture failed: {exc}",
        )
        return MonitoredRunResult(
            exit_code=1,
            session=None,
            monitor_result=result,
            message=result.message,
            launched=False,
            stopped_cleanly=True,
        )

    startup_probe = _StartupWindowProbe(
        resolved_monitor,
        baseline_handles=tuple(window.handle for window in baseline),
    )
    startup_probe.start()
    try:
        session = launcher.run()
        startup_probe.stop()
        if not session.ok:
            return MonitoredRunResult(
                exit_code=1,
                session=session,
                monitor_result=None,
                message=session.result.message,
                launched=False,
                stopped_cleanly=session.process is None
                or not _session_is_running(session),
            )

        startup_close_result = startup_probe.closed_before_monitor_result()
        if startup_close_result is not None:
            session.add_event(
                LaunchState.WINDOW_CLOSED,
                startup_close_result.message,
                render=False,
            )
            render_window_monitor_result(
                session.console_renderer,
                startup_close_result,
            )
            session.stop(graceful_timeout_seconds=graceful_timeout_seconds)
            return MonitoredRunResult(
                exit_code=0,
                session=session,
                monitor_result=startup_close_result,
                message=startup_close_result.message,
                launched=True,
                stopped_cleanly=not _session_is_running(session),
            )

        target = WindowTarget(
            launcher.config.title,
            url=session.url,
            browser_kind=getattr(session.browser, "kind", None),
            app_mode=True,
            baseline_handles=tuple(window.handle for window in baseline),
        )
        result = session.monitor_window(
            resolved_monitor,
            target,
            config=config,
            graceful_timeout_seconds=graceful_timeout_seconds,
        )
    except KeyboardInterrupt:
        startup_probe.stop()
        if session is not None and session.ok:
            session.stop(graceful_timeout_seconds=graceful_timeout_seconds)
        return MonitoredRunResult(
            exit_code=0,
            session=session,
            monitor_result=None,
            message="Window monitoring interrupted; runtime stopped.",
            launched=session is not None,
            stopped_cleanly=not _session_is_running(session),
        )
    finally:
        startup_probe.stop()

    if result.closed:
        return MonitoredRunResult(
            exit_code=0,
            session=session,
            monitor_result=result,
            message=result.message,
            launched=True,
            stopped_cleanly=not _session_is_running(session),
        )
    if result.status == WindowMonitorStatus.BACKEND_EXITED:
        return MonitoredRunResult(
            exit_code=0,
            session=session,
            monitor_result=result,
            message=result.message,
            launched=True,
            stopped_cleanly=True,
        )
    if result.status in {
        WindowMonitorStatus.UNSUPPORTED,
        WindowMonitorStatus.TIMEOUT,
        WindowMonitorStatus.ERROR,
    }:
        session.stop(graceful_timeout_seconds=graceful_timeout_seconds)
        return MonitoredRunResult(
            exit_code=1,
            session=session,
            monitor_result=result,
            message=result.message,
            launched=True,
            stopped_cleanly=not _session_is_running(session),
        )

    return MonitoredRunResult(
        exit_code=1,
        session=session,
        monitor_result=result,
        message=result.message,
        launched=True,
        stopped_cleanly=not _session_is_running(session),
    )


def run_profile(
    profile: LaunchProfile,
    *,
    launcher: StreamlitLauncher | None = None,
    launcher_factory: type[StreamlitLauncher] = StreamlitLauncher,
    platform_detector: PlatformDetector | None = None,
    window_monitor_factory: Callable[
        [PlatformInfo], WindowMonitor
    ] = create_window_monitor,
    monitor: WindowMonitor | None = None,
) -> MonitoredRunResult:
    """Run a launch profile through the normal or monitored runtime path."""

    resolved_launcher = launcher or launcher_factory(profile.config)
    if profile.monitor_window:
        return run_monitored_webapp(
            resolved_launcher,
            window_monitor_config=profile.window_monitor_config,
            graceful_timeout_seconds=profile.graceful_timeout_seconds,
            platform_detector=platform_detector,
            window_monitor_factory=window_monitor_factory,
            monitor=monitor,
        )
    if profile.monitor_browser_window:
        return run_monitored_browser_window(
            resolved_launcher,
            window_monitor_config=profile.browser_window_monitor_config,
            graceful_timeout_seconds=profile.graceful_timeout_seconds,
            platform_detector=platform_detector,
            window_monitor_factory=window_monitor_factory,
            monitor=monitor,
        )

    session = resolved_launcher.run()
    return MonitoredRunResult(
        exit_code=0 if session.ok else 1,
        session=session,
        monitor_result=None,
        message=session.result.message,
        launched=session.ok,
        stopped_cleanly=session.process is None or not _session_is_running(session),
    )


def run_monitored_browser_window(
    launcher_or_config: StreamlitLauncher | LauncherConfig,
    *,
    window_monitor_config: WindowMonitorConfig | None = None,
    graceful_timeout_seconds: float = 3.0,
    platform_detector: PlatformDetector | None = None,
    window_monitor_factory: Callable[
        [PlatformInfo], WindowMonitor
    ] = create_window_monitor,
    monitor: WindowMonitor | None = None,
    launcher_factory: type[StreamlitLauncher] = StreamlitLauncher,
) -> MonitoredRunResult:
    """Run browser mode with best-effort browser-window observation.

    This path observes only a newly opened top-level browser window. It never
    controls, closes, kills, or infers ownership over unrelated browser state.
    """

    launcher = _coerce_launcher(launcher_or_config, launcher_factory)
    if launcher.config.mode != LaunchMode.BROWSER:
        raise ConfigurationError(
            "run_monitored_browser_window requires mode='browser'."
        )
    if graceful_timeout_seconds <= 0:
        raise ConfigurationError("graceful_timeout_seconds must be positive.")

    config = window_monitor_config or WindowMonitorConfig(
        appear_timeout_seconds=8.0,
        poll_interval_seconds=0.25,
        stable_poll_count=2,
        require_app_mode=False,
    )
    if config.require_app_mode:
        config = WindowMonitorConfig(
            appear_timeout_seconds=config.appear_timeout_seconds,
            poll_interval_seconds=config.poll_interval_seconds,
            stable_poll_count=config.stable_poll_count,
            require_app_mode=False,
        )

    resolved_monitor = monitor or _create_monitor(
        platform_detector=platform_detector,
        window_monitor_factory=window_monitor_factory,
    )

    if isinstance(resolved_monitor, NoopWindowMonitor):
        session = launcher.run()
        result = _browser_window_fallback_result(
            "Browser-window monitoring is unavailable on this platform; "
            "Ctrl+C remains the shutdown path.",
            status=WindowMonitorStatus.UNSUPPORTED,
        )
        _render_browser_window_monitor_fallback(session, result)
        return MonitoredRunResult(
            exit_code=0 if session.ok else 1,
            session=session,
            monitor_result=result,
            message=result.message,
            launched=session.ok,
            stopped_cleanly=session.process is None or not _session_is_running(session),
        )

    baseline_target = WindowTarget("", browser_kind=None, app_mode=False)
    try:
        baseline = resolved_monitor.capture(baseline_target)
    except Exception:
        baseline = ()

    session: RuntimeSession | None = None
    try:
        session = launcher.run()
        _attach_console_renderer(session, launcher)
        if not session.ok:
            return MonitoredRunResult(
                exit_code=1,
                session=session,
                monitor_result=None,
                message=session.result.message,
                launched=False,
                stopped_cleanly=session.process is None
                or not _session_is_running(session),
            )

        target = WindowTarget(
            launcher.config.title,
            url=session.url,
            browser_kind=_session_browser_kind(session)
            or _explicit_browser_kind(launcher.config),
            app_mode=False,
            baseline_handles=tuple(window.handle for window in baseline),
        )
        result = _wait_for_browser_window_lifecycle(
            session,
            resolved_monitor,
            target,
            config=config,
            graceful_timeout_seconds=graceful_timeout_seconds,
        )
    except KeyboardInterrupt:
        if session is not None and session.ok:
            session.stop(graceful_timeout_seconds=graceful_timeout_seconds)
        return MonitoredRunResult(
            exit_code=0,
            session=session,
            monitor_result=None,
            message="Session stopped by user.",
            launched=session is not None,
            stopped_cleanly=not _session_is_running(session)
            if session is not None
            else True,
        )

    return MonitoredRunResult(
        exit_code=0 if session.ok else 1,
        session=session,
        monitor_result=result,
        message=result.message,
        launched=session.ok,
        stopped_cleanly=session.process is None or not _session_is_running(session),
    )


def _wait_for_browser_window_lifecycle(
    session: RuntimeSession,
    monitor: WindowMonitor,
    target: WindowTarget,
    *,
    config: WindowMonitorConfig,
    graceful_timeout_seconds: float,
) -> WindowMonitorResult:
    render_phase_start(
        session.console_renderer,
        ConsolePhase.MONITOR,
        "scanning for browser instance",
    )
    result = _select_new_browser_window(
        monitor,
        target,
        backend_is_running=session.is_running,
        config=config,
    )
    if not isinstance(result, WindowInfo):
        _render_browser_window_monitor_fallback(session, result)
        return result

    render_phase_success(
        session.console_renderer,
        ConsolePhase.MONITOR,
        "Success! Tracking browser window",
    )
    close_result = _wait_for_browser_window_close(
        session,
        monitor,
        target,
        result,
        config=config,
    )
    if close_result.closed:
        session.add_event(
            LaunchState.WINDOW_CLOSED,
            close_result.message,
            render=False,
        )
        render_window_monitor_result(session.console_renderer, close_result)
        session.stop(graceful_timeout_seconds=graceful_timeout_seconds)
    elif close_result.status == WindowMonitorStatus.BACKEND_EXITED:
        session.add_event(LaunchState.TERMINATED, close_result.message, render=False)
        render_window_monitor_result(session.console_renderer, close_result)
    else:
        _render_browser_window_monitor_fallback(session, close_result)
    return close_result


def _select_new_browser_window(
    monitor: WindowMonitor,
    target: WindowTarget,
    *,
    backend_is_running: Callable[[], bool],
    config: WindowMonitorConfig,
) -> WindowInfo | WindowMonitorResult:
    import time

    deadline = time.monotonic() + config.appear_timeout_seconds
    candidate: WindowInfo | None = None
    stable_count = 0

    while time.monotonic() <= deadline:
        if not backend_is_running():
            return _browser_window_fallback_result(
                "Backend exited before a browser-window target was observed.",
                status=WindowMonitorStatus.BACKEND_EXITED,
            )
        try:
            candidates = _browser_window_candidates(monitor, target)
        except Exception as exc:
            return _browser_window_fallback_result(
                f"Browser-window capture failed: {exc}",
                status=WindowMonitorStatus.ERROR,
            )
        if len(candidates) > 1:
            return _browser_window_fallback_result(
                "Multiple new browser windows matched; Ctrl+C remains the "
                "shutdown path.",
                status=WindowMonitorStatus.UNSUPPORTED,
                observed=True,
            )

        selected = candidates[0] if candidates else None
        if selected is None:
            candidate = None
            stable_count = 0
        elif candidate is not None and selected.handle == candidate.handle:
            stable_count += 1
        else:
            candidate = selected
            stable_count = 1

        if candidate is not None and stable_count >= config.stable_poll_count:
            return candidate
        time.sleep(config.poll_interval_seconds)

    return _browser_window_fallback_result(
        "No new browser window was observed; Ctrl+C remains the shutdown path.",
        status=WindowMonitorStatus.TIMEOUT,
    )


def _wait_for_browser_window_close(
    session: RuntimeSession,
    monitor: WindowMonitor,
    target: WindowTarget,
    target_window: WindowInfo,
    *,
    config: WindowMonitorConfig,
) -> WindowMonitorResult:
    import time

    while True:
        if not session.is_running():
            return WindowMonitorResult(
                supported=True,
                observed=True,
                closed=False,
                status=WindowMonitorStatus.BACKEND_EXITED,
                message="Backend exited while browser window was being monitored.",
                target=target_window,
            )
        try:
            active_handles = {window.handle for window in monitor.capture(target)}
        except Exception as exc:
            return WindowMonitorResult(
                supported=True,
                observed=True,
                closed=False,
                status=WindowMonitorStatus.ERROR,
                message=f"Browser-window capture failed: {exc}",
                target=target_window,
            )
        if target_window.handle not in active_handles:
            return WindowMonitorResult(
                supported=True,
                observed=True,
                closed=True,
                status=WindowMonitorStatus.WINDOW_CLOSED,
                message="Browser window closed.",
                target=target_window,
            )
        time.sleep(config.poll_interval_seconds)


def _browser_window_candidates(
    monitor: WindowMonitor,
    target: WindowTarget,
) -> tuple[WindowInfo, ...]:
    baseline = set(target.baseline_handles)
    return tuple(
        window
        for window in monitor.capture(target)
        if window.handle not in baseline
        and _is_browser_window_candidate(window, target)
    )


def _is_browser_window_candidate(window: WindowInfo, target: WindowTarget) -> bool:
    if not _window_matches_browser_kind(window, target.browser_kind):
        return False
    title = window.title.strip().lower()
    if not title:
        return False
    target_title = target.title.strip().lower()
    if target_title and target_title in title:
        return True
    if target.url:
        from urllib.parse import urlparse

        host = (urlparse(target.url).hostname or "").strip().lower()
        if host and (host in title or title.startswith(f"{host}_/")):
            return True
    return False


def _window_matches_browser_kind(
    window: WindowInfo,
    browser_kind: BrowserKind | None,
) -> bool:
    if browser_kind is None:
        return True
    process_name = (window.process_name or "").strip().lower()
    if process_name.endswith(".exe"):
        process_name = process_name[:-4]
    if browser_kind == BrowserKind.EDGE:
        return process_name in {"msedge", "microsoft-edge", "microsoft-edge-stable"}
    if browser_kind == BrowserKind.CHROME:
        return process_name in {
            "chrome",
            "chromium",
            "chromium-browser",
            "google-chrome",
            "google-chrome-stable",
        }
    return False


def _explicit_browser_kind(config: LauncherConfig) -> BrowserKind | None:
    value = (
        config.browser.value
        if hasattr(config.browser, "value")
        else str(config.browser)
    )
    if value == "edge":
        return BrowserKind.EDGE
    if value == "chrome":
        return BrowserKind.CHROME
    return None


def _session_browser_kind(session: RuntimeSession) -> BrowserKind | None:
    browser = getattr(session, "browser", None)
    kind = getattr(browser, "kind", None)
    if kind in {BrowserKind.EDGE, BrowserKind.CHROME}:
        return kind
    return None


def _browser_window_fallback_result(
    message: str,
    *,
    status: WindowMonitorStatus,
    observed: bool = False,
) -> WindowMonitorResult:
    return WindowMonitorResult(
        supported=status
        not in {
            WindowMonitorStatus.UNSUPPORTED,
            WindowMonitorStatus.UNAVAILABLE,
        },
        observed=observed,
        closed=False,
        status=status,
        message=message,
    )


def _render_browser_window_monitor_fallback(
    session: RuntimeSession,
    result: WindowMonitorResult,
) -> None:
    render_phase_warning(session.console_renderer, ConsolePhase.MONITOR, result.message)


def _coerce_launcher(
    launcher_or_config: StreamlitLauncher | LauncherConfig,
    launcher_factory: type[StreamlitLauncher],
) -> StreamlitLauncher:
    if isinstance(launcher_or_config, LauncherConfig):
        return launcher_factory(launcher_or_config)
    return launcher_or_config


def _attach_console_renderer(
    session: RuntimeSession,
    launcher: StreamlitLauncher,
) -> None:
    if getattr(session, "console_renderer", None) is not None:
        return
    renderer = getattr(launcher, "console_renderer", None)
    if renderer is not None:
        try:
            session.console_renderer = renderer
        except Exception:
            return


def _create_monitor(
    *,
    platform_detector: PlatformDetector | None,
    window_monitor_factory: Callable[[PlatformInfo], WindowMonitor],
) -> WindowMonitor:
    detector = platform_detector or PlatformDetector()
    platform_info = detector.detect()
    return window_monitor_factory(platform_info)


def _session_is_running(session: RuntimeSession) -> bool:
    is_running = getattr(session, "is_running", None)
    if callable(is_running):
        return bool(is_running())
    return False


class _StartupWindowProbe:
    """Observe app-mode windows during the browser-launch handoff gap."""

    def __init__(
        self,
        monitor: WindowMonitor,
        *,
        baseline_handles: tuple[str, ...],
        poll_interval_seconds: float = 0.05,
    ) -> None:
        self.monitor = monitor
        self.target = WindowTarget(
            "Streamlit App",
            app_mode=True,
            baseline_handles=baseline_handles,
        )
        self.poll_interval_seconds = poll_interval_seconds
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._observed: WindowInfo | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def closed_before_monitor_result(self) -> WindowMonitorResult | None:
        with self._lock:
            observed = self._observed
        if observed is None:
            return None

        try:
            active_handles = {
                window.handle for window in self.monitor.capture(self.target)
            }
        except Exception:
            return None
        if observed.handle in active_handles:
            return None
        return WindowMonitorResult(
            supported=True,
            observed=True,
            closed=True,
            status=WindowMonitorStatus.WINDOW_CLOSED,
            message="App-mode window closed before monitoring started.",
            target=observed,
        )

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                candidates = self._candidate_windows()
            except Exception:
                return
            if candidates:
                with self._lock:
                    self._observed = candidates[-1]
            self._stop.wait(self.poll_interval_seconds)

    def _candidate_windows(self) -> tuple[WindowInfo, ...]:
        baseline = set(self.target.baseline_handles)
        return tuple(
            window
            for window in self.monitor.capture(self.target)
            if window.handle not in baseline
        )
