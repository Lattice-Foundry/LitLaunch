"""Shared helpers for monitored runtime orchestration."""

from __future__ import annotations

from collections.abc import Callable

from litlaunch.config import LauncherConfig
from litlaunch.launcher import StreamlitLauncher
from litlaunch.platforms import PlatformDetector, PlatformInfo
from litlaunch.session import RuntimeSession
from litlaunch.windowing import WindowMonitor


def coerce_launcher(
    launcher_or_config: StreamlitLauncher | LauncherConfig,
    launcher_factory: type[StreamlitLauncher],
) -> StreamlitLauncher:
    """Return a launcher for an existing launcher or config value."""

    if isinstance(launcher_or_config, LauncherConfig):
        return launcher_factory(launcher_or_config)
    return launcher_or_config


def attach_console_renderer(
    session: RuntimeSession,
    launcher: StreamlitLauncher,
) -> None:
    """Attach a launcher's console renderer to a session when missing."""

    if getattr(session, "console_renderer", None) is not None:
        return
    renderer = getattr(launcher, "console_renderer", None)
    if renderer is not None:
        try:
            session.console_renderer = renderer
        except Exception:
            return


def create_monitor(
    *,
    platform_detector: PlatformDetector | None,
    window_monitor_factory: Callable[[PlatformInfo], WindowMonitor],
) -> WindowMonitor:
    """Create a platform-aware window monitor."""

    detector = platform_detector or PlatformDetector()
    platform_info = detector.detect()
    return window_monitor_factory(platform_info)


def session_is_running(session: RuntimeSession) -> bool:
    """Return whether a runtime session still appears active."""

    is_running = getattr(session, "is_running", None)
    if callable(is_running):
        return bool(is_running())
    return False
