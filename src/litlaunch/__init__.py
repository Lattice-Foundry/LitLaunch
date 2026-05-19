"""Public API for LitLaunch."""

from litlaunch.browsers import (
    BrowserCapability,
    BrowserKind,
    BrowserLauncher,
    BrowserLaunchResult,
    BrowserResolution,
)
from litlaunch.config import BrowserChoice, LauncherConfig, LaunchMode
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
    "LaunchMode",
    "LauncherConfig",
    "LitLaunchError",
    "LaunchEvent",
    "LaunchResult",
    "LaunchState",
    "OperatingSystem",
    "PlatformDetector",
    "PlatformInfo",
    "RuntimeSession",
    "StreamlitLauncher",
    "__version__",
]
