"""Optional window monitoring foundation for LitLaunch app-mode runtimes."""

from litlaunch.windowing.base import (
    WindowInfo,
    WindowMonitor,
    WindowMonitorConfig,
    WindowMonitorEvent,
    WindowMonitorResult,
    WindowMonitorStatus,
    WindowTarget,
)
from litlaunch.windowing.noop import NoopWindowMonitor
from litlaunch.windowing.polling import PollingWindowMonitor
from litlaunch.windowing.windows import (
    WindowsChromiumWindowMonitor,
    WindowsWindowProvider,
    create_window_monitor,
    is_chromium_window,
)

__all__ = [
    "NoopWindowMonitor",
    "PollingWindowMonitor",
    "WindowsChromiumWindowMonitor",
    "WindowsWindowProvider",
    "WindowInfo",
    "WindowMonitor",
    "WindowMonitorConfig",
    "WindowMonitorEvent",
    "WindowMonitorResult",
    "WindowMonitorStatus",
    "WindowTarget",
    "create_window_monitor",
    "is_chromium_window",
]
