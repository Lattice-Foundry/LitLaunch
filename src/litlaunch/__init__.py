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
from litlaunch.launcher import StreamlitLauncher
from litlaunch.lifecycle import LaunchEvent, LaunchResult, LaunchState
from litlaunch.platforms import (
    Architecture,
    OperatingSystem,
    PlatformDetector,
    PlatformInfo,
)
from litlaunch.session import RuntimeSession
from litlaunch.shutdown import (
    LauncherRuntime,
    ShutdownHook,
    ShutdownHookRegistry,
    ShutdownHookResult,
    ShutdownResult,
)
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
    "RuntimeSession",
    "ShutdownHook",
    "ShutdownHookRegistry",
    "ShutdownHookResult",
    "ShutdownResult",
    "StreamlitLauncher",
    "__version__",
]
