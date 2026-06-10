"""Managed browser-window monitoring for browser-mode launches."""

from __future__ import annotations

from collections.abc import Callable

from litlaunch.browsers import BrowserKind
from litlaunch.config import LauncherConfig, LaunchMode
from litlaunch.console import ConsolePhase
from litlaunch.exceptions import ConfigurationError
from litlaunch.launcher import StreamlitLauncher
from litlaunch.lifecycle import LaunchState
from litlaunch.monitored import MonitoredRunResult
from litlaunch.monitored_common import (
    attach_console_renderer,
    coerce_launcher,
    create_monitor,
    session_is_running,
)
from litlaunch.platforms import PlatformDetector, PlatformInfo
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

    launcher = coerce_launcher(launcher_or_config, launcher_factory)
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

    resolved_monitor = monitor or create_monitor(
        platform_detector=platform_detector,
        window_monitor_factory=window_monitor_factory,
    )

    if isinstance(resolved_monitor, NoopWindowMonitor):
        fallback_session = launcher.run()
        result = browser_window_fallback_result(
            "Browser-window monitoring is unavailable on this platform; "
            "Ctrl+C remains the shutdown path.",
            status=WindowMonitorStatus.UNSUPPORTED,
        )
        render_browser_window_monitor_fallback(fallback_session, result)
        return MonitoredRunResult(
            exit_code=0 if fallback_session.ok else 1,
            session=fallback_session,
            monitor_result=result,
            message=result.message,
            launched=fallback_session.ok,
            stopped_cleanly=fallback_session.process is None
            or not session_is_running(fallback_session),
        )

    baseline_target = WindowTarget("", browser_kind=None, app_mode=False)
    try:
        baseline = resolved_monitor.capture(baseline_target)
    except Exception:
        baseline = ()

    session: RuntimeSession | None = None
    try:
        session = launcher.run()
        attach_console_renderer(session, launcher)
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

        target = WindowTarget(
            launcher.config.title,
            url=session.url,
            browser_kind=session_browser_kind(session)
            or explicit_browser_kind(launcher.config),
            app_mode=False,
            baseline_handles=tuple(window.handle for window in baseline),
        )
        result = wait_for_browser_window_lifecycle(
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
            stopped_cleanly=not session_is_running(session)
            if session is not None
            else True,
        )

    return MonitoredRunResult(
        exit_code=0 if session.ok else 1,
        session=session,
        monitor_result=result,
        message=result.message,
        launched=session.ok,
        stopped_cleanly=session.process is None or not session_is_running(session),
    )


def wait_for_browser_window_lifecycle(
    session: RuntimeSession,
    monitor: WindowMonitor,
    target: WindowTarget,
    *,
    config: WindowMonitorConfig,
    graceful_timeout_seconds: float,
) -> WindowMonitorResult:
    """Wait for a newly opened browser window and stop when it closes."""

    render_phase_start(
        session.console_renderer,
        ConsolePhase.MONITOR,
        "scanning for browser instance",
    )
    session.event_emitter.emit(
        "monitor_started",
        category="monitor",
        message="Browser-window monitoring started.",
        details={"mode": "browser", "target": target.title},
    )
    result = select_new_browser_window(
        monitor,
        target,
        backend_is_running=session.is_running,
        config=config,
    )
    if not isinstance(result, WindowInfo):
        render_browser_window_monitor_fallback(session, result)
        return result

    render_phase_success(
        session.console_renderer,
        ConsolePhase.MONITOR,
        "Success! Tracking browser window",
    )
    close_result = wait_for_browser_window_close(
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
        render_browser_window_monitor_fallback(session, close_result)
    return close_result


def select_new_browser_window(
    monitor: WindowMonitor,
    target: WindowTarget,
    *,
    backend_is_running: Callable[[], bool],
    config: WindowMonitorConfig,
) -> WindowInfo | WindowMonitorResult:
    """Select one stable browser window that appeared after baseline capture."""

    import time

    deadline = time.monotonic() + config.appear_timeout_seconds
    candidate: WindowInfo | None = None
    stable_count = 0

    while time.monotonic() <= deadline:
        if not backend_is_running():
            return browser_window_fallback_result(
                "Backend exited before a browser-window target was observed.",
                status=WindowMonitorStatus.BACKEND_EXITED,
            )
        try:
            candidates = browser_window_candidates(monitor, target)
        except Exception as exc:
            return browser_window_fallback_result(
                f"Browser-window capture failed: {exc}",
                status=WindowMonitorStatus.ERROR,
            )
        if len(candidates) > 1:
            return browser_window_fallback_result(
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

    return browser_window_fallback_result(
        "No new browser window was observed; Ctrl+C remains the shutdown path.",
        status=WindowMonitorStatus.TIMEOUT,
    )


def wait_for_browser_window_close(
    session: RuntimeSession,
    monitor: WindowMonitor,
    target: WindowTarget,
    target_window: WindowInfo,
    *,
    config: WindowMonitorConfig,
) -> WindowMonitorResult:
    """Wait until the selected browser window disappears."""

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


def browser_window_candidates(
    monitor: WindowMonitor,
    target: WindowTarget,
) -> tuple[WindowInfo, ...]:
    """Return candidate browser windows not present in the baseline."""

    baseline = set(target.baseline_handles)
    return tuple(
        window
        for window in monitor.capture(target)
        if window.handle not in baseline and is_browser_window_candidate(window, target)
    )


def is_browser_window_candidate(window: WindowInfo, target: WindowTarget) -> bool:
    """Return whether a window is a plausible managed browser-window target."""

    if not window_matches_browser_kind(window, target.browser_kind):
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


def window_matches_browser_kind(
    window: WindowInfo,
    browser_kind: BrowserKind | None,
) -> bool:
    """Return whether a window process matches the expected browser kind."""

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


def explicit_browser_kind(config: LauncherConfig) -> BrowserKind | None:
    """Return the requested Chromium browser kind when explicit."""

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


def session_browser_kind(session: RuntimeSession) -> BrowserKind | None:
    """Return the actual Chromium browser kind from a runtime session."""

    browser = getattr(session, "browser", None)
    kind = getattr(browser, "kind", None)
    if kind in {BrowserKind.EDGE, BrowserKind.CHROME}:
        return kind
    return None


def browser_window_fallback_result(
    message: str,
    *,
    status: WindowMonitorStatus,
    observed: bool = False,
) -> WindowMonitorResult:
    """Build a browser-window monitor fallback result."""

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


def render_browser_window_monitor_fallback(
    session: RuntimeSession,
    result: WindowMonitorResult,
) -> None:
    """Render browser-window monitor fallback messaging."""

    render_phase_warning(session.console_renderer, ConsolePhase.MONITOR, result.message)
