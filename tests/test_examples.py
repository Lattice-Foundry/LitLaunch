import py_compile
from pathlib import Path

from litlaunch import LauncherConfig, StreamlitLauncher

REPO_ROOT = Path(__file__).parents[1]
EXAMPLE_APP = REPO_ROOT / "examples" / "minimal_app" / "app.py"
EXAMPLE_README = REPO_ROOT / "examples" / "minimal_app" / "README.md"
GITATTRIBUTES = REPO_ROOT / ".gitattributes"
GITIGNORE = REPO_ROOT / ".gitignore"


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


def test_py_typed_marker_exists():
    assert (REPO_ROOT / "src" / "litlaunch" / "py.typed").is_file()


def test_claude_directory_is_ignored():
    gitignore = GITIGNORE.read_text(encoding="utf-8")

    assert ".claude/" in gitignore


def test_gitattributes_normalizes_text_to_lf():
    gitattributes = GITATTRIBUTES.read_text(encoding="utf-8")

    assert GITATTRIBUTES.is_file()
    assert "* text=auto eol=lf" in gitattributes


def test_readme_no_longer_uses_early_foundation_status():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "Current status: early foundation" not in readme
    assert "Python 3.14.5" in readme
    normalized = " ".join(readme.split()).lower()
    assert "diagnostics dashboard" in normalized
    assert "window monitoring is observational only" in normalized
    assert "packaging guidance" in normalized
    assert "examples/minimal_app" in readme


def test_minimal_example_readme_reflects_current_cli():
    readme = EXAMPLE_README.read_text(encoding="utf-8")

    assert "future CLI support is expected" not in readme
    assert "Until the CLI lands" not in readme
    assert "litlaunch run examples/minimal_app/app.py" in readme
    assert "Python 3.14.5" in readme
    assert "source tree as a development/demo fixture" in readme


def test_minimal_example_uses_canonical_github_urls():
    app = EXAMPLE_APP.read_text(encoding="utf-8")
    old_litlaunch = "LatticeFoundry/" + "litlaunch"
    old_rolethread = "LatticeFoundry/" + "rolethread"

    assert "https://github.com/Lattice-Foundry/LitLaunch" in app
    assert "https://github.com/Lattice-Foundry/RoleThread" in app
    assert old_litlaunch not in app
    assert old_rolethread not in app


def test_package_internals_do_not_reference_rolethread():
    for path in (REPO_ROOT / "src" / "litlaunch").rglob("*.py"):
        assert "RoleThread" not in path.read_text(encoding="utf-8")
