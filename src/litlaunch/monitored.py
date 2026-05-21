"""High-level monitored webapp runtime orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from litlaunch.config import LauncherConfig, LaunchMode
from litlaunch.exceptions import ConfigurationError
from litlaunch.launcher import StreamlitLauncher
from litlaunch.platforms import PlatformDetector, PlatformInfo
from litlaunch.profiles import LaunchProfile
from litlaunch.session import RuntimeSession
from litlaunch.windowing import (
    NoopWindowMonitor,
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

    session = launcher.run()
    if not session.ok:
        return MonitoredRunResult(
            exit_code=1,
            session=session,
            monitor_result=None,
            message=session.result.message,
            launched=False,
            stopped_cleanly=session.process is None or not _session_is_running(session),
        )

    target = WindowTarget(
        launcher.config.title,
        url=session.url,
        browser_kind=getattr(session.browser, "kind", None),
        app_mode=True,
        baseline_handles=tuple(window.handle for window in baseline),
    )
    try:
        result = session.monitor_window(
            resolved_monitor,
            target,
            config=config,
            graceful_timeout_seconds=graceful_timeout_seconds,
        )
    except KeyboardInterrupt:
        session.stop(graceful_timeout_seconds=graceful_timeout_seconds)
        return MonitoredRunResult(
            exit_code=0,
            session=session,
            monitor_result=None,
            message="Window monitoring interrupted; runtime stopped.",
            launched=True,
            stopped_cleanly=not _session_is_running(session),
        )

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

    session = resolved_launcher.run()
    return MonitoredRunResult(
        exit_code=0 if session.ok else 1,
        session=session,
        monitor_result=None,
        message=session.result.message,
        launched=session.ok,
        stopped_cleanly=session.process is None or not _session_is_running(session),
    )


def _coerce_launcher(
    launcher_or_config: StreamlitLauncher | LauncherConfig,
    launcher_factory: type[StreamlitLauncher],
) -> StreamlitLauncher:
    if isinstance(launcher_or_config, LauncherConfig):
        return launcher_factory(launcher_or_config)
    return launcher_or_config


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
