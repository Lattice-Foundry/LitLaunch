import py_compile
from pathlib import Path

from litlaunch import LauncherConfig, StreamlitLauncher

REPO_ROOT = Path(__file__).parents[1]
EXAMPLE_APP = REPO_ROOT / "examples" / "minimal_app" / "app.py"
EXAMPLE_README = REPO_ROOT / "examples" / "minimal_app" / "README.md"


def test_minimal_example_app_exists():
    assert EXAMPLE_APP.is_file()


def test_minimal_example_readme_exists():
    assert EXAMPLE_README.is_file()


def test_minimal_example_app_compiles():
    py_compile.compile(str(EXAMPLE_APP), doraise=True)


def test_launcher_builds_command_for_minimal_example_app():
    config = LauncherConfig(app_path=EXAMPLE_APP, port=8501)
    command = StreamlitLauncher(config).build_command()

    assert command[:4][-3:] == ("-m", "streamlit", "run")
    assert str(EXAMPLE_APP) in command
    assert command[command.index("--server.port") + 1] == "8501"


def test_nested_example_path_remains_one_command_argument():
    config = LauncherConfig(app_path=EXAMPLE_APP)
    command = StreamlitLauncher(config).build_command()

    app_arg = command[4]
    assert app_arg == str(EXAMPLE_APP)
    assert command.count(app_arg) == 1
    assert "examples" in app_arg
    assert "minimal_app" in app_arg
