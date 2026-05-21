"""Public API for LitLaunch."""

from litlaunch.backend import (
    BackendCommand,
    BackendCommandContext,
    BackendCommandProvider,
    StreamlitBackendCommandProvider,
)
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
    hook_orange,
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
from litlaunch.exceptions import (
    BrowserError,
    CommandBuildError,
    ConfigurationError,
    LitLaunchError,
    PortError,
    ProcessError,
)
from litlaunch.health import HealthChecker
from litlaunch.inspect import (
    DiagnosticCollector,
    DiagnosticItem,
    DiagnosticSection,
    DiagnosticsReport,
    DiagnosticStatus,
    HTMLDiagnosticsRenderer,
    JSONDiagnosticsRenderer,
    SanitizedBundleRenderer,
)
from litlaunch.launcher import StreamlitLauncher
from litlaunch.lifecycle import LaunchEvent, LaunchPlan, LaunchResult, LaunchState
from litlaunch.monitored import MonitoredRunResult, run_monitored_webapp, run_profile
from litlaunch.platforms import (
    Architecture,
    OperatingSystem,
    PlatformDetector,
    PlatformInfo,
)
from litlaunch.ports import PortManager
from litlaunch.process import ManagedProcess, ProcessManager
from litlaunch.profiles import LaunchProfile, load_profile, load_profiles
from litlaunch.session import RuntimeSession
from litlaunch.shutdown import (
    LauncherRuntime,
    ShutdownClient,
    ShutdownConfig,
    ShutdownHook,
    ShutdownHookRegistry,
    ShutdownHookResult,
    ShutdownRequestResult,
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
    "BrowserError",
    "BackendCommand",
    "BackendCommandContext",
    "BackendCommandProvider",
    "CommandBuildError",
    "ConfigurationError",
    "ConsoleMode",
    "ConsolePhase",
    "ConsoleRenderer",
    "ConsoleTheme",
    "get_theme_color",
    "hook_orange",
    "HealthChecker",
    "DiagnosticCollector",
    "DiagnosticItem",
    "DiagnosticSection",
    "DiagnosticStatus",
    "DiagnosticsReport",
    "HTMLDiagnosticsRenderer",
    "JSONDiagnosticsRenderer",
    "SanitizedBundleRenderer",
    "LaunchMode",
    "LauncherConfig",
    "LaunchProfile",
    "LitLaunchError",
    "LaunchEvent",
    "LaunchPlan",
    "LaunchResult",
    "LaunchState",
    "LauncherRuntime",
    "OperatingSystem",
    "PlatformDetector",
    "PlatformInfo",
    "ManagedProcess",
    "MonitoredRunResult",
    "NoopWindowMonitor",
    "PortManager",
    "PollingWindowMonitor",
    "PortError",
    "ProcessError",
    "ProcessManager",
    "load_profile",
    "load_profiles",
    "RuntimeSession",
    "run_profile",
    "run_monitored_webapp",
    "ShutdownClient",
    "ShutdownConfig",
    "ShutdownHook",
    "ShutdownHookRegistry",
    "ShutdownHookResult",
    "ShutdownRequestResult",
    "ShutdownResult",
    "StreamlitCommandBuilder",
    "StreamlitBackendCommandProvider",
    "StreamlitLauncher",
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
