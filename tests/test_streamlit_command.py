import sys

from litlaunch import LauncherConfig
from litlaunch.streamlit import StreamlitCommandBuilder


def test_command_is_tuple_not_string():
    command = StreamlitCommandBuilder(LauncherConfig(app_path="app.py")).build()

    assert isinstance(command, tuple)
    assert not isinstance(command, str)


def test_command_starts_with_python_module_streamlit_run():
    command = StreamlitCommandBuilder(LauncherConfig(app_path="app.py")).build()

    assert command[:4] == (sys.executable, "-m", "streamlit", "run")


def test_app_path_with_spaces_remains_one_argument():
    command = StreamlitCommandBuilder(
        LauncherConfig(app_path="apps/My App/app.py"),
    ).build()

    app_arg = command[4]
    assert "My App" in app_arg
    assert command.count(app_arg) == 1


def test_browser_mode_uses_expected_headless_default():
    command = StreamlitCommandBuilder(LauncherConfig(app_path="app.py")).build()

    assert command[command.index("--server.headless") + 1] == "false"


def test_webapp_mode_uses_expected_headless_default():
    command = StreamlitCommandBuilder(
        LauncherConfig(app_path="app.py", mode="webapp"),
    ).build()

    assert command[command.index("--server.headless") + 1] == "true"


def test_host_and_port_flags_are_included_correctly():
    command = StreamlitCommandBuilder(
        LauncherConfig(app_path="app.py", host="localhost", port=8502),
    ).build()

    assert command[command.index("--server.address") + 1] == "localhost"
    assert command[command.index("--server.port") + 1] == "8502"


def test_app_args_appear_after_separator():
    command = StreamlitCommandBuilder(
        LauncherConfig(app_path="app.py", app_args=["--workspace", "demo"]),
    ).build()

    separator_index = command.index("--")
    assert command[separator_index + 1 :] == ("--workspace", "demo")


def test_user_streamlit_flags_are_included_before_app_args():
    command = StreamlitCommandBuilder(
        LauncherConfig(
            app_path="app.py",
            streamlit_flags={"server.maxUploadSize": 1024, "--logger.level": "debug"},
            app_args=["--workspace", "demo"],
        ),
    ).build()

    separator_index = command.index("--")
    assert "--server.maxUploadSize" in command[:separator_index]
    assert "1024" in command[:separator_index]
    assert "--logger.level" in command[:separator_index]
    assert "debug" in command[:separator_index]
