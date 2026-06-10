"""High-level monitored webapp runtime orchestration."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from litlaunch.config import LauncherConfig, LaunchMode
from litlaunch.exceptions import ConfigurationError
from litlaunch.launcher import StreamlitLauncher
from litlaunch.lifecycle import LaunchState
from litlaunch.monitored_common import (
    coerce_launcher,
    create_monitor,
    session_is_running,
)
from litlaunch.platforms import PlatformDetector, PlatformInfo
from litlaunch.profiles import LaunchProfile
from litlaunch.runtime_console import render_window_monitor_result
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
    """Structured result for a monitored runtime run."""

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

    launcher = coerce_launcher(launcher_or_config, launcher_factory)
    if launcher.config.mode != LaunchMode.WEBAPP:
        raise ConfigurationError("run_monitored_webapp requires mode='webapp'.")
    if graceful_timeout_seconds <= 0:
        raise ConfigurationError("graceful_timeout_seconds must be positive.")

    config = window_monitor_config or WindowMonitorConfig()
    resolved_monitor = monitor or create_monitor(
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
                or not session_is_running(session),
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
                stopped_cleanly=not session_is_running(session),
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
            stopped_cleanly=session is None or not session_is_running(session),
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
            stopped_cleanly=not session_is_running(session),
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
            stopped_cleanly=not session_is_running(session),
        )

    return MonitoredRunResult(
        exit_code=1,
        session=session,
        monitor_result=result,
        message=result.message,
        launched=True,
        stopped_cleanly=not session_is_running(session),
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
        stopped_cleanly=session.process is None or not session_is_running(session),
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
    """Run browser mode with best-effort browser-window observation."""

    from litlaunch.monitored_browser import run_monitored_browser_window as _run

    return _run(
        launcher_or_config,
        window_monitor_config=window_monitor_config,
        graceful_timeout_seconds=graceful_timeout_seconds,
        platform_detector=platform_detector,
        window_monitor_factory=window_monitor_factory,
        monitor=monitor,
        launcher_factory=launcher_factory,
    )


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
