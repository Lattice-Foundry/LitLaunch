"""Public API for LitLaunch."""

from litlaunch.browsers import (
    BrowserCapability,
    BrowserKind,
    BrowserLauncher,
    BrowserLaunchResult,
    BrowserResolution,
)
from litlaunch.colors import (
    THEME_COLORS,
    ThemeColor,
    get_theme_color,
    is_hex_color,
    is_theme_color_name,
)
from litlaunch.config import BrowserChoice, LauncherConfig, LaunchMode
from litlaunch.console import (
    ConsoleMode,
    ConsolePhase,
    ConsoleRenderer,
    ConsoleTheme,
)
from litlaunch.exceptions import ConfigurationError, LitLaunchError
from litlaunch.health import HealthChecker
from litlaunch.inspect import (
    DiagnosticCollector,
    DiagnosticItem,
    DiagnosticSection,
    DiagnosticsReport,
    DiagnosticStatus,
    JSONDiagnosticsRenderer,
    SanitizedBundleRenderer,
    TextDiagnosticsRenderer,
)
from litlaunch.launcher import StreamlitLauncher
from litlaunch.lifecycle import LaunchEvent, LaunchResult, LaunchState
from litlaunch.platforms import (
    Architecture,
    OperatingSystem,
    PlatformDetector,
    PlatformInfo,
)
from litlaunch.ports import PortManager
from litlaunch.process import ManagedProcess, ProcessManager
from litlaunch.session import RuntimeSession
from litlaunch.shutdown import (
    LauncherRuntime,
    ShutdownHook,
    ShutdownHookRegistry,
    ShutdownHookResult,
    ShutdownResult,
)
from litlaunch.streamlit import StreamlitCommandBuilder
from litlaunch.version import __version__
from litlaunch.windowing import (
    NoopWindowMonitor,
    PollingWindowMonitor,
    WindowInfo,
    WindowMonitor,
    WindowMonitorConfig,
    WindowMonitorEvent,
    WindowMonitorResult,
    WindowMonitorStatus,
    WindowsChromiumWindowMonitor,
    WindowsWindowProvider,
    WindowTarget,
    create_window_monitor,
    is_chromium_window,
)

__all__ = [
    "Architecture",
    "BrowserCapability",
    "BrowserChoice",
    "BrowserKind",
    "BrowserLaunchResult",
    "BrowserLauncher",
    "BrowserResolution",
    "ConfigurationError",
    "ConsoleMode",
    "ConsolePhase",
    "ConsoleRenderer",
    "ConsoleTheme",
    "get_theme_color",
    "HealthChecker",
    "DiagnosticCollector",
    "DiagnosticItem",
    "DiagnosticSection",
    "DiagnosticStatus",
    "DiagnosticsReport",
    "JSONDiagnosticsRenderer",
    "SanitizedBundleRenderer",
    "LaunchMode",
    "LauncherConfig",
    "LitLaunchError",
    "LaunchEvent",
    "LaunchResult",
    "LaunchState",
    "LauncherRuntime",
    "OperatingSystem",
    "PlatformDetector",
    "PlatformInfo",
    "ManagedProcess",
    "NoopWindowMonitor",
    "PortManager",
    "PollingWindowMonitor",
    "ProcessManager",
    "RuntimeSession",
    "ShutdownHook",
    "ShutdownHookRegistry",
    "ShutdownHookResult",
    "ShutdownResult",
    "StreamlitCommandBuilder",
    "StreamlitLauncher",
    "TextDiagnosticsRenderer",
    "WindowsChromiumWindowMonitor",
    "WindowsWindowProvider",
    "WindowInfo",
    "WindowMonitor",
    "WindowMonitorConfig",
    "WindowMonitorEvent",
    "WindowMonitorResult",
    "WindowMonitorStatus",
    "WindowTarget",
    "__version__",
    "create_window_monitor",
    "is_chromium_window",
    "is_hex_color",
    "is_theme_color_name",
    "THEME_COLORS",
    "ThemeColor",
]
