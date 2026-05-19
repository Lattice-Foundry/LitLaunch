import re
from importlib.metadata import version

import litlaunch
from litlaunch import (
    Architecture,
    BrowserChoice,
    ConfigurationError,
    LauncherConfig,
    LaunchEvent,
    LaunchMode,
    LaunchResult,
    LaunchState,
    LitLaunchError,
    OperatingSystem,
    PlatformDetector,
    PlatformInfo,
    StreamlitLauncher,
    __version__,
)


def test_public_imports_are_available():
    assert LauncherConfig(app_path="app.py").mode == LaunchMode.BROWSER
    assert BrowserChoice.AUTO.value == "auto"
    assert issubclass(ConfigurationError, LitLaunchError)
    assert LaunchState.CREATED.value == "created"
    assert LaunchEvent
    assert LaunchResult
    assert OperatingSystem.WINDOWS.value == "windows"
    assert Architecture.X64.value == "x64"
    assert PlatformDetector
    assert PlatformInfo
    assert StreamlitLauncher


def test_public_all_is_explicit():
    assert sorted(litlaunch.__all__) == [
        "Architecture",
        "BrowserChoice",
        "ConfigurationError",
        "LaunchEvent",
        "LaunchMode",
        "LaunchResult",
        "LaunchState",
        "LauncherConfig",
        "LitLaunchError",
        "OperatingSystem",
        "PlatformDetector",
        "PlatformInfo",
        "StreamlitLauncher",
        "__version__",
    ]


def test_version_is_public_and_internal_baseline():
    assert litlaunch.__version__ == "0.2.0"
    assert __version__ == "0.2.0"
    assert re.fullmatch(r"\d+\.\d+\.\d+", litlaunch.__version__)


def test_package_metadata_version_matches_public_version():
    assert version("litlaunch") == litlaunch.__version__
