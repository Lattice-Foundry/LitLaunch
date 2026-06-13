import tempfile
from pathlib import Path

import pytest

from litlaunch import (
    BrowserChoice,
    ConfigurationError,
    LaunchMode,
    LaunchProfile,
    TrustMode,
    WindowMonitorConfig,
    load_profile,
    load_profiles,
)


@pytest.fixture
def tmp_path():
    with tempfile.TemporaryDirectory(prefix="litlaunch-profile-test-") as path:
        yield Path(path)


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_litlaunch_toml_profile(tmp_path):
    app = write(tmp_path / "app.py", "print('hello')\n")
    icon = tmp_path / "assets" / "app.ico"
    icon.parent.mkdir()
    icon.write_bytes(b"icon")
    config_path = write(
        tmp_path / "litlaunch.toml",
        """
[profiles.my-webapp]
app_path = "app.py"
title = "My App"
app_icon = "assets/app.ico"
mode = "webapp"
browser = "edge"
trust_mode = "internal_network"
host = "127.0.0.1"
port = 8501
port_range = [8501, 8599]
auto_port = false
headless = true
show_streamlit_chrome = true
show_streamlit_output = true
allow_browser_fallback = false
cwd = "."
runtime_state_root = ".runtime/litlaunch"
streamlit_args = ["--server.runOnSave", "true"]
app_args = ["--workspace", "demo"]
extra_browser_args = ["--new-window"]
runtime_event_log = ".litlaunch/runtime-events.log"
graceful_timeout = 15

[profiles.my-webapp.extra_env]
APP_ENV = "local"

[profiles.my-webapp.streamlit_flags]
"server.maxUploadSize" = 200

[profiles.my-webapp.window_monitor]
enabled = true
appear_timeout = 60
poll_interval = 1
stable_polls = 2

[profiles.my-webapp.browser_window_monitor]
enabled = true
appear_timeout = 8
poll_interval = 0.25
stable_polls = 2
""",
    )

    profile = load_profile("my-webapp", config_path)

    assert isinstance(profile, LaunchProfile)
    assert profile.name == "my-webapp"
    assert profile.config.app_path == app
    assert profile.config.title == "My App"
    assert profile.config.app_icon == icon
    assert profile.config.mode == LaunchMode.WEBAPP
    assert profile.config.browser == BrowserChoice.EDGE
    assert profile.config.trust_mode == TrustMode.INTERNAL_NETWORK
    assert profile.config.port == 8501
    assert profile.config.port_range == (8501, 8599)
    assert profile.config.auto_port is False
    assert profile.config.headless is True
    assert profile.config.show_streamlit_chrome is True
    assert profile.config.show_streamlit_output is True
    assert profile.config.allow_browser_fallback is False
    assert profile.config.cwd == tmp_path
    assert profile.config.runtime_state_root == tmp_path / ".runtime" / "litlaunch"
    assert profile.config.extra_env["APP_ENV"] == "local"
    assert profile.config.streamlit_flags["server.maxUploadSize"] == 200
    assert profile.config.streamlit_args == ("--server.runOnSave", "true")
    assert profile.config.app_args == ("--workspace", "demo")
    assert profile.config.extra_browser_args == ("--new-window",)
    assert profile.config.runtime_event_log == tmp_path / ".litlaunch" / (
        "runtime-events.log"
    )
    assert profile.monitor_window is True
    assert profile.graceful_timeout_seconds == 15.0
    assert profile.window_monitor_config == WindowMonitorConfig(
        appear_timeout_seconds=60.0,
        poll_interval_seconds=1.0,
        stable_poll_count=2,
    )
    assert profile.monitor_browser_window is True
    assert profile.browser_window_monitor_config == WindowMonitorConfig(
        appear_timeout_seconds=8.0,
        poll_interval_seconds=0.25,
        stable_poll_count=2,
        require_app_mode=False,
    )


def test_loads_pyproject_profile(tmp_path):
    app = write(tmp_path / "app.py", "print('hello')\n")
    config_path = write(
        tmp_path / "pyproject.toml",
        """
[tool.litlaunch.profiles.default]
app_path = "app.py"
title = "Pyproject App"
mode = "browser"
browser = "default"
""",
    )

    profiles = load_profiles(config_path)

    assert profiles["default"].config.app_path == app
    assert profiles["default"].config.title == "Pyproject App"
    assert profiles["default"].config.browser == BrowserChoice.DEFAULT


def test_invalid_profile_trust_mode_raises(tmp_path):
    write(tmp_path / "app.py", "print('hello')\n")
    config_path = write(
        tmp_path / "litlaunch.toml",
        """
[profiles.web]
app_path = "app.py"
trust_mode = "public_internet"
""",
    )

    with pytest.raises(ConfigurationError, match="Invalid trust_mode"):
        load_profile("web", config_path)


def test_discovers_single_profile_source(tmp_path):
    app = write(tmp_path / "app.py", "print('hello')\n")
    write(
        tmp_path / "litlaunch.toml",
        """
[profiles.default]
app_path = "app.py"
""",
    )

    profile = load_profile("default", cwd=tmp_path)

    assert profile.config.app_path == app


def test_ambiguous_discovered_profile_sources_fail(tmp_path):
    write(
        tmp_path / "litlaunch.toml",
        """
[profiles.default]
app_path = "app.py"
""",
    )
    write(
        tmp_path / "pyproject.toml",
        """
[tool.litlaunch.profiles.default]
app_path = "app.py"
""",
    )

    with pytest.raises(ConfigurationError, match="Ambiguous"):
        load_profiles(cwd=tmp_path)


def test_explicit_config_path_wins_when_multiple_sources_exist(tmp_path):
    app = write(tmp_path / "app.py", "print('hello')\n")
    litlaunch_config = write(
        tmp_path / "litlaunch.toml",
        """
[profiles.default]
app_path = "app.py"
title = "LitLaunch TOML"
""",
    )
    write(
        tmp_path / "pyproject.toml",
        """
[tool.litlaunch.profiles.default]
app_path = "other.py"
title = "Pyproject"
""",
    )

    profile = load_profile("default", litlaunch_config)

    assert profile.config.app_path == app
    assert profile.config.title == "LitLaunch TOML"


def test_profile_validation_errors_are_clear(tmp_path):
    with pytest.raises(ConfigurationError, match="not found"):
        load_profiles(tmp_path / "missing.toml")

    invalid = write(tmp_path / "bad.toml", "[profiles.default\n")
    with pytest.raises(ConfigurationError, match="Invalid TOML"):
        load_profiles(invalid)

    missing_app = write(
        tmp_path / "missing_app.toml",
        """
[profiles.default]
title = "No App"
""",
    )
    with pytest.raises(ConfigurationError, match="requires app_path"):
        load_profile("default", missing_app)

    bad_monitor = write(
        tmp_path / "bad_monitor.toml",
        """
[profiles.default]
app_path = "app.py"

[profiles.default.window_monitor]
stable_polls = 0
""",
    )
    with pytest.raises(ConfigurationError, match="stable_poll_count"):
        load_profile("default", bad_monitor)


def test_profile_names_are_validated(tmp_path):
    config_path = write(
        tmp_path / "litlaunch.toml",
        """
[profiles.default]
app_path = "app.py"
""",
    )

    with pytest.raises(ConfigurationError, match="profile name"):
        load_profile("bad name", config_path)
