from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

import pytest
from packaging.version import Version

from litlaunch.version import __version__

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
    version = module.read_project_version()

    assert version == __version__
    assert not Version(version).is_prerelease


@pytest.mark.parametrize("version", ["1.0.0b1", "1.0.0rc1"])
def test_release_script_allows_beta_classifier_with_prerelease_version(version: str):
    module = load_release_script()

    module.ensure_classifier_version_consistency(
        version,
        ("Development Status :: 4 - Beta",),
    )


def test_release_script_allows_stable_classifier_with_stable_version():
    module = load_release_script()

    module.ensure_classifier_version_consistency(
        "1.0.0",
        ("Development Status :: 5 - Production/Stable",),
    )


def test_release_script_rejects_stable_classifier_with_prerelease_version():
    module = load_release_script()

    with pytest.raises(RuntimeError, match="Stable package classifier"):
        module.ensure_classifier_version_consistency(
            "1.0.0rc1",
            ("Development Status :: 5 - Production/Stable",),
        )


def test_release_script_detects_forbidden_archive_entries():
    module = load_release_script()
    prefix = f"litlaunch-{module.read_project_version()}"

    forbidden = module.find_forbidden_archive_entries(
        (
            f"{prefix}/src/litlaunch/__pycache__/x.pyc",
            f"{prefix}/.ruff_cache/CACHEDIR.TAG",
            f"{prefix}/.claude/settings.json",
            f"{prefix}/src/litlaunch/module.py",
        )
    )

    assert forbidden == (
        f"{prefix}/src/litlaunch/__pycache__/x.pyc",
        f"{prefix}/.ruff_cache/CACHEDIR.TAG",
        f"{prefix}/.claude/settings.json",
    )


def test_release_script_detects_suspicious_repo_root_artifacts():
    module = load_release_script()

    with tempfile.TemporaryDirectory(prefix="litlaunch-release-test-") as temp_dir:
        root = Path(temp_dir)
        suspicious = root / "3.10`"
        suspicious.write_text("", encoding="utf-8")
        legitimate = root / "README.md"
        legitimate.write_text("# Project\n", encoding="utf-8")

        assert module.find_suspicious_repo_root_artifacts(root) == (suspicious,)


def test_release_script_detects_forbidden_repo_tree_artifacts():
    module = load_release_script()

    with tempfile.TemporaryDirectory(prefix="litlaunch-release-test-") as temp_dir:
        root = Path(temp_dir)
        cache_dir = root / "src" / "litlaunch" / "__pycache__"
        cache_dir.mkdir(parents=True)
        bytecode = cache_dir / "module.pyc"
        bytecode.write_bytes(b"cache")
        root_temp = root / "litlaunch-test-leftover"
        root_temp.mkdir()
        report = root / "litlaunch-report.html"
        report.write_text("<html></html>", encoding="utf-8")
        ignored = root / ".venv" / "Lib" / "site-packages" / "__pycache__"
        ignored.mkdir(parents=True)
        (ignored / "module.pyc").write_bytes(b"cache")

        forbidden = module.find_forbidden_repo_tree_artifacts(root)

        assert forbidden == (report, root_temp, cache_dir, bytecode)


def test_release_script_accepts_normal_empty_root_files():
    module = load_release_script()

    with tempfile.TemporaryDirectory(prefix="litlaunch-release-test-") as temp_dir:
        root = Path(temp_dir)
        keep = root / ".gitkeep"
        keep.write_text("", encoding="utf-8")

        assert module.find_suspicious_repo_root_artifacts(root) == ()


def test_release_script_accepts_ignored_repo_tree_artifacts():
    module = load_release_script()

    with tempfile.TemporaryDirectory(prefix="litlaunch-release-test-") as temp_dir:
        root = Path(temp_dir)
        cache_dir = root / ".venv" / "Lib" / "site-packages" / "__pycache__"
        cache_dir.mkdir(parents=True)
        (cache_dir / "module.pyc").write_bytes(b"cache")

        assert module.find_forbidden_repo_tree_artifacts(root) == ()


@pytest.mark.parametrize(
    "token",
    [
        "py" + "pi-" + ("A" * 24),
        "gh" + "p_" + ("A" * 24),
        "github" + "_pat_" + ("A" * 32),
        "gl" + "pat-" + ("A" * 24),
    ],
)
def test_release_script_detects_potential_credentials_in_text_files(token: str):
    module = load_release_script()

    with tempfile.TemporaryDirectory(prefix="litlaunch-release-test-") as temp_dir:
        root = Path(temp_dir)
        notes = root / "notes"
        notes.mkdir()
        secret_file = notes / "api.txt"
        secret_file.write_text(f"token={token}\n", encoding="utf-8")

        findings = module.find_potential_credentials(root)

        assert findings == ((secret_file, "line 1"),)


def test_release_script_ignores_credentials_in_dependency_trees():
    module = load_release_script()

    with tempfile.TemporaryDirectory(prefix="litlaunch-release-test-") as temp_dir:
        root = Path(temp_dir)
        ignored = root / ".venv" / "Lib" / "site-packages"
        ignored.mkdir(parents=True)
        token = "gh" + "p_" + ("A" * 24)
        (ignored / "config.txt").write_text(f"{token}\n", encoding="utf-8")

        assert module.find_potential_credentials(root) == ()


def test_release_script_skips_binary_or_unreadable_credential_candidates():
    module = load_release_script()

    with tempfile.TemporaryDirectory(prefix="litlaunch-release-test-") as temp_dir:
        root = Path(temp_dir)
        binary = root / "image.png"
        binary.write_bytes(b"\x89PNG\r\n\x1a\n" + b"pypi-" + (b"A" * 24))
        unreadable_text = root / "notes.txt"
        unreadable_text.write_bytes(b"\xff\xfe\x00pypi-" + (b"A" * 24))

        assert module.find_potential_credentials(root) == ()


def test_release_script_skips_large_credential_candidates():
    module = load_release_script()

    with tempfile.TemporaryDirectory(prefix="litlaunch-release-test-") as temp_dir:
        root = Path(temp_dir)
        large = root / "large.txt"
        large.write_text(
            "x" * (module.CREDENTIAL_SCAN_MAX_BYTES + 1) + "\n" + "pypi-" + ("A" * 24),
            encoding="utf-8",
        )

        assert module.find_potential_credentials(root) == ()


def test_release_script_rejects_unsafe_archive_entries():
    module = load_release_script()
    prefix = f"litlaunch-{module.read_project_version()}"

    entries = (
        "/absolute/path.py",
        f"{prefix}/../escape.py",
        f"{prefix}/.git/config",
        f"{prefix}/.venv/pyvenv.cfg",
    )

    assert module.find_forbidden_archive_entries(entries) == entries


def test_release_script_allows_normal_archive_entries():
    module = load_release_script()
    prefix = f"litlaunch-{module.read_project_version()}"

    assert (
        module.find_forbidden_archive_entries(
            (
                f"{prefix}/README.md",
                f"{prefix}/src/litlaunch/__init__.py",
                f"{prefix}/src/litlaunch/py.typed",
            )
        )
        == ()
    )


def test_release_script_rejects_internal_docs_in_sdist():
    module = load_release_script()
    version = module.read_project_version()
    prefix = f"litlaunch-{version}"

    with pytest.raises(RuntimeError, match="Internal integration docs"):
        module.inspect_sdist_names(
            (
                f"{prefix}/README.md",
                f"{prefix}/LICENSE",
                f"{prefix}/pyproject.toml",
                f"{prefix}/docs/Public/Guides/overview.md",
                f"{prefix}/docs/internal/README.md",
                f"{prefix}/src/litlaunch/__init__.py",
                f"{prefix}/src/litlaunch/py.typed",
            ),
            version,
        )


def test_release_script_rejects_local_notes_in_sdist():
    module = load_release_script()
    version = module.read_project_version()
    prefix = f"litlaunch-{version}"

    with pytest.raises(RuntimeError, match="Local notes"):
        module.inspect_sdist_names(
            (
                f"{prefix}/README.md",
                f"{prefix}/LICENSE",
                f"{prefix}/pyproject.toml",
                f"{prefix}/docs/Public/Guides/overview.md",
                f"{prefix}/notes/api.txt",
                f"{prefix}/src/litlaunch/__init__.py",
                f"{prefix}/src/litlaunch/py.typed",
            ),
            version,
        )


def test_release_script_rejects_engineering_research_in_sdist():
    module = load_release_script()
    version = module.read_project_version()
    prefix = f"litlaunch-{version}"

    with pytest.raises(RuntimeError, match="Engineering research"):
        module.inspect_sdist_names(
            (
                f"{prefix}/README.md",
                f"{prefix}/LICENSE",
                f"{prefix}/pyproject.toml",
                f"{prefix}/docs/Public/Guides/overview.md",
                f"{prefix}/docs/research/host_sizing_notes.md",
                f"{prefix}/src/litlaunch/__init__.py",
                f"{prefix}/src/litlaunch/py.typed",
            ),
            version,
        )


def test_release_script_require_archive_entry_raises_for_missing_entry():
    module = load_release_script()

    with pytest.raises(RuntimeError, match="Missing required archive entry"):
        module.require_archive_entry(("README.md",), "LICENSE", lambda name: False)
