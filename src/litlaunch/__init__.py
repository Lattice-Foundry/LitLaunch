"""Public API for LitLaunch."""

from litlaunch.browsers import (
    BrowserCapability,
    BrowserKind,
    BrowserLauncher,
    BrowserLaunchResult,
    BrowserResolution,
)
from litlaunch.config import BrowserChoice, LauncherConfig, LaunchMode
from litlaunch.console import (
    ConsoleMode,
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
    "ConsoleRenderer",
    "ConsoleTheme",
    "HealthChecker",
    "DiagnosticCollector",
    "DiagnosticItem",
    "DiagnosticSection",
    "DiagnosticStatus",
    "DiagnosticsReport",
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
    "PortManager",
    "ProcessManager",
    "RuntimeSession",
    "ShutdownHook",
    "ShutdownHookRegistry",
    "ShutdownHookResult",
    "ShutdownResult",
    "StreamlitCommandBuilder",
    "StreamlitLauncher",
    "TextDiagnosticsRenderer",
    "__version__",
]
