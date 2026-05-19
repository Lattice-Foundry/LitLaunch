import re
from importlib.metadata import version

import litlaunch
from litlaunch import (
    BrowserChoice,
    ConfigurationError,
    LauncherConfig,
    LaunchEvent,
    LaunchMode,
    LaunchResult,
    LaunchState,
    LitLaunchError,
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
    assert StreamlitLauncher


def test_public_all_is_explicit():
    assert sorted(litlaunch.__all__) == [
        "BrowserChoice",
        "ConfigurationError",
        "LaunchEvent",
        "LaunchMode",
        "LaunchResult",
        "LaunchState",
        "LauncherConfig",
        "LitLaunchError",
        "StreamlitLauncher",
        "__version__",
    ]


def test_version_is_public_and_internal_baseline():
    assert litlaunch.__version__ == "0.1.0"
    assert __version__ == "0.1.0"
    assert re.fullmatch(r"\d+\.\d+\.\d+", litlaunch.__version__)


def test_package_metadata_version_matches_public_version():
    assert version("litlaunch") == litlaunch.__version__
