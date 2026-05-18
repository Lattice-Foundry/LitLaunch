import litlaunch
from litlaunch import (
    BrowserChoice,
    ConfigurationError,
    LauncherConfig,
    LaunchMode,
    LitLaunchError,
    StreamlitLauncher,
)


def test_public_imports_are_available():
    assert LauncherConfig(app_path="app.py").mode == LaunchMode.BROWSER
    assert BrowserChoice.AUTO.value == "auto"
    assert issubclass(ConfigurationError, LitLaunchError)
    assert StreamlitLauncher


def test_public_all_is_explicit():
    assert sorted(litlaunch.__all__) == [
        "BrowserChoice",
        "ConfigurationError",
        "LaunchMode",
        "LauncherConfig",
        "LitLaunchError",
        "StreamlitLauncher",
    ]
