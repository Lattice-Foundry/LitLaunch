from pathlib import Path

import pytest

from litlaunch import (
    BrowserChoice,
    ConfigurationError,
    HostSizingPolicy,
    LauncherConfig,
    LaunchMode,
    TrustMode,
)


def test_default_config_normalizes_correctly():
    config = LauncherConfig(app_path="app.py")

    assert str(config.app_path) == "app.py"
    assert config.title == "Streamlit App"
    assert config.mode == LaunchMode.BROWSER
    assert config.browser == BrowserChoice.AUTO
    assert config.host == "127.0.0.1"
    assert config.port is None
    assert config.auto_port is True
    assert config.show_streamlit_chrome is False
    assert config.show_streamlit_output is False
    assert config.allow_browser_fallback is True
    assert config.trust_mode == TrustMode.DEVELOPMENT
    assert config.host_sizing == HostSizingPolicy.OFF


def test_string_mode_and_browser_normalize_to_enums():
    config = LauncherConfig(app_path="app.py", mode="webapp", browser="chrome")

    assert config.mode == LaunchMode.WEBAPP
    assert config.browser == BrowserChoice.CHROME


def test_invalid_mode_raises_configuration_error():
    with pytest.raises(ConfigurationError, match="Invalid mode"):
        LauncherConfig(app_path="app.py", mode="desktop")


def test_invalid_browser_raises_configuration_error():
    with pytest.raises(ConfigurationError, match="Invalid browser"):
        LauncherConfig(app_path="app.py", browser="safari")


def test_trust_mode_string_normalizes_to_enum():
    config = LauncherConfig(app_path="app.py", trust_mode="strict_local")

    assert config.trust_mode == TrustMode.STRICT_LOCAL


def test_show_streamlit_chrome_normalizes_to_bool():
    config = LauncherConfig(app_path="app.py", show_streamlit_chrome=1)

    assert config.show_streamlit_chrome is True


def test_show_streamlit_output_normalizes_to_bool():
    config = LauncherConfig(app_path="app.py", show_streamlit_output=1)

    assert config.show_streamlit_output is True


def test_invalid_trust_mode_raises_configuration_error():
    with pytest.raises(ConfigurationError, match="Invalid trust_mode"):
        LauncherConfig(app_path="app.py", trust_mode="public_internet")


def test_initial_host_sizing_normalizes_to_public_policy():
    config = LauncherConfig(app_path="app.py", host_sizing="initial")

    assert config.host_sizing == HostSizingPolicy.INITIAL


@pytest.mark.parametrize(
    "value",
    ["enabled", "continuous", "auto", "fit", "viewport", "resize", True, False],
)
def test_host_sizing_rejects_values_outside_exact_public_vocabulary(value):
    with pytest.raises(ConfigurationError, match="Invalid host_sizing"):
        LauncherConfig(app_path="app.py", host_sizing=value)


def test_empty_app_path_raises_configuration_error():
    with pytest.raises(ConfigurationError, match="app_path cannot be empty"):
        LauncherConfig(app_path=" ")


def test_empty_title_raises_configuration_error():
    with pytest.raises(ConfigurationError, match="title cannot be empty"):
        LauncherConfig(app_path="app.py", title=" ")


@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "127.0.0.1",
        "::1",
        "0.0.0.0",
        "example.com",
        "my-app.local",
    ],
)
def test_valid_hosts_are_accepted(host):
    config = LauncherConfig(app_path="app.py", host=host)

    assert config.host == host


@pytest.mark.parametrize(
    "host",
    [
        "bad host",
        "http://localhost",
        "-bad.local",
        "bad-.local",
        "",
        "name_with_underscore",
    ],
)
def test_invalid_hosts_raise_configuration_error(host):
    with pytest.raises(ConfigurationError, match="host"):
        LauncherConfig(app_path="app.py", host=host)


@pytest.mark.parametrize("port", [0, 65536, -1, True, "8501"])
def test_invalid_port_raises_configuration_error(port):
    with pytest.raises(ConfigurationError, match="port must be an integer"):
        LauncherConfig(app_path="app.py", port=port)


def test_port_none_forces_auto_port_true():
    config = LauncherConfig(app_path="app.py", port=None, auto_port=False)

    assert config.auto_port is True


def test_port_range_normalizes_from_sequence():
    config = LauncherConfig(app_path="app.py", port_range=[8501, 8599])

    assert config.port_range == (8501, 8599)


def test_port_range_normalizes_from_string():
    config = LauncherConfig(app_path="app.py", port_range="8501:8599")

    assert config.port_range == (8501, 8599)


def test_port_range_requires_valid_order():
    with pytest.raises(ConfigurationError, match="start must be less"):
        LauncherConfig(app_path="app.py", port_range=[8599, 8501])


def test_port_must_be_inside_port_range():
    with pytest.raises(ConfigurationError, match="inside port_range"):
        LauncherConfig(app_path="app.py", port=8600, port_range=[8501, 8599])


def test_cwd_normalizes_to_optional_path():
    config = LauncherConfig(app_path="app.py", cwd="workspace")

    assert str(config.cwd) == "workspace"


def test_empty_cwd_raises_configuration_error():
    with pytest.raises(ConfigurationError, match="cwd cannot be empty"):
        LauncherConfig(app_path="app.py", cwd=" ")


def test_runtime_state_root_normalizes_to_optional_path():
    config = LauncherConfig(app_path="app.py", runtime_state_root="runtime")

    assert config.runtime_state_root == Path("runtime")


def test_empty_runtime_state_root_raises_configuration_error():
    with pytest.raises(ConfigurationError, match="runtime_state_root cannot be empty"):
        LauncherConfig(app_path="app.py", runtime_state_root=" ")


def test_runtime_event_log_normalizes_to_optional_path():
    config = LauncherConfig(
        app_path="app.py",
        runtime_event_log=".litlaunch/runtime-events.log",
    )

    assert config.runtime_event_log == Path(".litlaunch/runtime-events.log")


def test_empty_runtime_event_log_raises_configuration_error():
    with pytest.raises(ConfigurationError, match="runtime_event_log cannot be empty"):
        LauncherConfig(app_path="app.py", runtime_event_log=" ")


def test_app_icon_validates_existing_supported_file(tmp_path):
    icon = tmp_path / "app.ico"
    icon.write_bytes(b"icon")

    config = LauncherConfig(app_path="app.py", app_icon=icon)

    assert config.app_icon == icon


def test_app_icon_rejects_missing_directory_and_extension(tmp_path):
    with pytest.raises(ConfigurationError, match="app_icon does not exist"):
        LauncherConfig(app_path="app.py", app_icon=tmp_path / "missing.ico")

    directory = tmp_path / "icons"
    directory.mkdir()
    with pytest.raises(ConfigurationError, match="app_icon must be a file"):
        LauncherConfig(app_path="app.py", app_icon=directory)

    text_icon = tmp_path / "icon.txt"
    text_icon.write_text("not an icon", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="app_icon must use one"):
        LauncherConfig(app_path="app.py", app_icon=text_icon)


def test_extra_env_is_copy_safe_and_string_normalized():
    env = {"APP_MODE": "demo", "COUNT": 3}
    config = LauncherConfig(app_path="app.py", extra_env=env)

    env["APP_MODE"] = "changed"

    assert config.extra_env["APP_MODE"] == "demo"
    assert config.extra_env["COUNT"] == "3"
    with pytest.raises(TypeError):
        config.extra_env["OTHER"] = "value"


def test_extra_env_rejects_invalid_mapping_values():
    with pytest.raises(ConfigurationError, match="extra_env must be a mapping"):
        LauncherConfig(app_path="app.py", extra_env=["A=B"])
    with pytest.raises(ConfigurationError, match="variable names"):
        LauncherConfig(app_path="app.py", extra_env={" ": "value"})
    with pytest.raises(ConfigurationError, match="NUL"):
        LauncherConfig(app_path="app.py", extra_env={"A": "bad\x00value"})


def test_streamlit_app_and_extra_browser_args_become_tuples():
    config = LauncherConfig(
        app_path="app.py",
        streamlit_args=["--server.runOnSave", "true"],
        app_args=["--workspace", "demo"],
        extra_browser_args=["--new-window"],
    )

    assert config.streamlit_args == ("--server.runOnSave", "true")
    assert config.app_args == ("--workspace", "demo")
    assert config.extra_browser_args == ("--new-window",)


def test_streamlit_args_reject_plain_string():
    with pytest.raises(ConfigurationError, match="streamlit_args must be a sequence"):
        LauncherConfig(app_path="app.py", streamlit_args="--server.runOnSave true")


def test_streamlit_flags_mapping_is_copy_safe():
    flags = {"server.maxUploadSize": 1024}
    config = LauncherConfig(app_path="app.py", streamlit_flags=flags)

    flags["server.maxUploadSize"] = 2048

    assert config.streamlit_flags["server.maxUploadSize"] == 1024
    with pytest.raises(TypeError):
        config.streamlit_flags["other"] = "value"


def test_streamlit_flags_sequence_becomes_tuple():
    config = LauncherConfig(
        app_path="app.py",
        streamlit_flags=["--logger.level", "debug"],
    )

    assert config.streamlit_flags == ("--logger.level", "debug")


def test_webapp_mode_rejects_headless_false_without_explicit_streamlit_override():
    with pytest.raises(ConfigurationError, match="headless=True"):
        LauncherConfig(app_path="app.py", mode="webapp", headless=False)


def test_webapp_mode_allows_explicit_streamlit_headless_override_mapping():
    config = LauncherConfig(
        app_path="app.py",
        mode="webapp",
        headless=False,
        streamlit_flags={"server.headless": False},
    )

    assert config.headless is False
    assert config.streamlit_flags["server.headless"] is False


def test_webapp_mode_allows_explicit_streamlit_headless_override_sequence():
    config = LauncherConfig(
        app_path="app.py",
        mode="webapp",
        headless=False,
        streamlit_flags=("--server.headless=false",),
    )

    assert config.headless is False
    assert config.streamlit_flags == ("--server.headless=false",)


def test_webapp_mode_allows_explicit_raw_streamlit_headless_override():
    config = LauncherConfig(
        app_path="app.py",
        mode="webapp",
        headless=False,
        streamlit_args=("--server.headless=false",),
    )

    assert config.headless is False
    assert config.streamlit_args == ("--server.headless=false",)
