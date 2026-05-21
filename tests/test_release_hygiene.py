from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_release.py"


def load_release_script():
    spec = importlib.util.spec_from_file_location("check_release", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_release_check_script_exists_and_help_mentions_build_and_twine():
    module = load_release_script()

    help_text = module.build_parser().format_help()

    assert SCRIPT_PATH.is_file()
    assert "Build LitLaunch release artifacts" in help_text
    assert "twine" in help_text
    assert "--skip-smoke" in help_text


def test_release_script_smoke_includes_installed_inspect_and_command_checks():
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert '"inspect"' in source
    assert '"report"' in source
    assert '"help"' in source
    assert '"command"' in source
    assert '"examples" / "minimal_app" / "app.py"' in source


def test_release_script_reads_current_version():
    module = load_release_script()

    assert module.read_project_version() == "0.91.22b0"


def test_release_script_detects_forbidden_archive_entries():
    module = load_release_script()

    forbidden = module.find_forbidden_archive_entries(
        (
            "litlaunch-0.91.22b0/src/litlaunch/__pycache__/x.pyc",
            "litlaunch-0.91.22b0/.ruff_cache/CACHEDIR.TAG",
            "litlaunch-0.91.22b0/.claude/settings.json",
            "litlaunch-0.91.22b0/src/litlaunch/module.py",
        )
    )

    assert forbidden == (
        "litlaunch-0.91.22b0/src/litlaunch/__pycache__/x.pyc",
        "litlaunch-0.91.22b0/.ruff_cache/CACHEDIR.TAG",
        "litlaunch-0.91.22b0/.claude/settings.json",
    )


def test_release_script_detects_suspicious_repo_root_artifacts():
    module = load_release_script()

    with tempfile.TemporaryDirectory(
        prefix="litlaunch-test-",
        dir=REPO_ROOT,
    ) as temp_dir:
        root = Path(temp_dir)
        suspicious = root / "3.10`"
        suspicious.write_text("", encoding="utf-8")
        legitimate = root / "README.md"
        legitimate.write_text("# Project\n", encoding="utf-8")

        assert module.find_suspicious_repo_root_artifacts(root) == (suspicious,)


def test_release_script_accepts_normal_empty_root_files():
    module = load_release_script()

    with tempfile.TemporaryDirectory(
        prefix="litlaunch-test-",
        dir=REPO_ROOT,
    ) as temp_dir:
        root = Path(temp_dir)
        keep = root / ".gitkeep"
        keep.write_text("", encoding="utf-8")

        assert module.find_suspicious_repo_root_artifacts(root) == ()


@pytest.mark.parametrize(
    "entry",
    [
        "/absolute/path.py",
        "litlaunch-0.91.22b0/../escape.py",
        "litlaunch-0.91.22b0/.git/config",
        "litlaunch-0.91.22b0/.venv/pyvenv.cfg",
    ],
)
def test_release_script_rejects_unsafe_archive_entries(entry):
    module = load_release_script()

    assert module.find_forbidden_archive_entries((entry,)) == (entry,)


def test_release_script_allows_normal_archive_entries():
    module = load_release_script()

    assert (
        module.find_forbidden_archive_entries(
            (
                "litlaunch-0.91.22b0/README.md",
                "litlaunch-0.91.22b0/src/litlaunch/__init__.py",
                "litlaunch-0.91.22b0/src/litlaunch/py.typed",
            )
        )
        == ()
    )


def test_release_script_rejects_internal_docs_in_sdist():
    module = load_release_script()

    with pytest.raises(RuntimeError, match="Internal integration docs"):
        module.inspect_sdist_names(
            (
                "litlaunch-0.91.22b0/README.md",
                "litlaunch-0.91.22b0/LICENSE",
                "litlaunch-0.91.22b0/pyproject.toml",
                "litlaunch-0.91.22b0/docs/overview.md",
                "litlaunch-0.91.22b0/docs/internal/README.md",
                "litlaunch-0.91.22b0/src/litlaunch/__init__.py",
                "litlaunch-0.91.22b0/src/litlaunch/py.typed",
            ),
            "0.91.22b0",
        )


def test_release_script_require_archive_entry_raises_for_missing_entry():
    module = load_release_script()

    with pytest.raises(RuntimeError, match="Missing required archive entry"):
        module.require_archive_entry(("README.md",), "LICENSE", lambda name: False)
