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


def test_browser_mode_suppresses_streamlit_native_browser_by_default():
    command = StreamlitCommandBuilder(LauncherConfig(app_path="app.py")).build()

    assert command[command.index("--server.headless") + 1] == "true"


def test_browser_mode_allows_explicit_streamlit_native_browser_opt_in():
    command = StreamlitCommandBuilder(
        LauncherConfig(app_path="app.py", headless=False),
    ).build()

    assert command[command.index("--server.headless") + 1] == "false"


def test_webapp_mode_uses_expected_headless_default():
    command = StreamlitCommandBuilder(
        LauncherConfig(app_path="app.py", mode="webapp"),
    ).build()

    assert command[command.index("--server.headless") + 1] == "true"


def test_streamlit_chrome_is_hidden_by_default():
    command = StreamlitCommandBuilder(LauncherConfig(app_path="app.py")).build()

    assert command[command.index("--client.toolbarMode") + 1] == "minimal"


def test_show_streamlit_chrome_omits_litlaunch_toolbar_mode_default():
    command = StreamlitCommandBuilder(
        LauncherConfig(app_path="app.py", show_streamlit_chrome=True),
    ).build()

    assert "--client.toolbarMode" not in command


def test_user_streamlit_chrome_flag_prevents_duplicate_default_injection():
    command = StreamlitCommandBuilder(
        LauncherConfig(
            app_path="app.py",
            streamlit_flags={"client.toolbarMode": "viewer"},
        ),
    ).build()

    assert command.count("--client.toolbarMode") == 1
    assert command[command.index("--client.toolbarMode") + 1] == "viewer"


def test_raw_streamlit_chrome_arg_prevents_duplicate_default_injection():
    command = StreamlitCommandBuilder(
        LauncherConfig(
            app_path="app.py",
            streamlit_args=("--client.toolbarMode=viewer",),
        ),
    ).build()

    assert command.count("--client.toolbarMode") == 0
    assert command.count("--client.toolbarMode=viewer") == 1


def test_host_and_port_flags_are_included_correctly():
    command = StreamlitCommandBuilder(
        LauncherConfig(app_path="app.py", host="localhost", port=8502),
    ).build()

    assert command[command.index("--server.address") + 1] == "localhost"
    assert command[command.index("--server.port") + 1] == "8502"


def test_explicit_build_port_overrides_config_port():
    command = StreamlitCommandBuilder(
        LauncherConfig(app_path="app.py", port=8501),
    ).build(port=8600)

    assert command[command.index("--server.port") + 1] == "8600"


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


def test_raw_streamlit_args_preserve_order_before_app_args():
    command = StreamlitCommandBuilder(
        LauncherConfig(
            app_path="app.py",
            streamlit_args=(
                "--server.runOnSave",
                "true",
                "--theme.base=dark",
                "--logger.enableRich",
            ),
            app_args=("--workspace", "demo"),
        ),
    ).build()

    separator_index = command.index("--")
    assert command[separator_index - 4 : separator_index] == (
        "--server.runOnSave",
        "true",
        "--theme.base=dark",
        "--logger.enableRich",
    )
    assert command[separator_index + 1 :] == ("--workspace", "demo")


def test_raw_streamlit_args_allow_repeated_flags():
    command = StreamlitCommandBuilder(
        LauncherConfig(
            app_path="app.py",
            streamlit_args=(
                "--server.folderWatchBlacklist",
                "data",
                "--server.folderWatchBlacklist",
                "logs",
            ),
        ),
    ).build()

    assert command.count("--server.folderWatchBlacklist") == 2
    assert command[-4:] == (
        "--server.folderWatchBlacklist",
        "data",
        "--server.folderWatchBlacklist",
        "logs",
    )


def test_non_conflicting_user_streamlit_flags_are_appended_after_litlaunch_defaults():
    command = StreamlitCommandBuilder(
        LauncherConfig(
            app_path="app.py",
            streamlit_flags={"logger.level": "debug"},
        ),
    ).build()

    default_index = command.index("--server.headless")
    user_index = command.index("--logger.level")
    assert default_index < user_index
    assert command[user_index + 1] == "debug"


def test_user_builtin_streamlit_flag_prevents_duplicate_default_injection():
    command = StreamlitCommandBuilder(
        LauncherConfig(
            app_path="app.py",
            port=8501,
            streamlit_flags={"server.port": 9000, "server.headless": True},
        ),
    ).build()

    assert command.count("--server.port") == 1
    assert command[command.index("--server.port") + 1] == "9000"
    assert command.count("--server.headless") == 1
    assert command[command.index("--server.headless") + 1] == "true"


def test_sequence_builtin_streamlit_flag_prevents_duplicate_default_injection():
    command = StreamlitCommandBuilder(
        LauncherConfig(
            app_path="app.py",
            host="127.0.0.1",
            streamlit_flags=("--server.address", "0.0.0.0"),
        ),
    ).build()

    assert command.count("--server.address") == 1
    assert command[command.index("--server.address") + 1] == "0.0.0.0"


def test_inline_sequence_builtin_streamlit_flag_prevents_duplicate_default_injection():
    command = StreamlitCommandBuilder(
        LauncherConfig(
            app_path="app.py",
            port=8501,
            streamlit_flags=("--server.port=9000",),
        ),
    ).build()

    assert command.count("--server.port") == 0
    assert command.count("--server.port=9000") == 1


def test_raw_builtin_streamlit_args_prevent_duplicate_default_injection():
    command = StreamlitCommandBuilder(
        LauncherConfig(
            app_path="app.py",
            port=8501,
            streamlit_args=("--server.port", "9000", "--server.headless=false"),
        ),
    ).build()

    assert command.count("--server.port") == 1
    assert command[command.index("--server.port") + 1] == "9000"
    assert command.count("--server.headless") == 0
    assert command.count("--server.headless=false") == 1
