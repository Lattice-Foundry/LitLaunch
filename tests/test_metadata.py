from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib

REPO_ROOT = Path(__file__).parents[1]


def test_pyproject_metadata_includes_console_and_typing_classifiers():
    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    classifiers = set(pyproject["project"]["classifiers"])
    assert "Environment :: Console" in classifiers
    assert "Topic :: Utilities" in classifiers
    assert "Typing :: Typed" in classifiers
    assert pyproject["project"]["requires-python"] == ">=3.10"


def test_pyproject_dev_extras_include_release_tools():
    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    dev_dependencies = set(pyproject["project"]["optional-dependencies"]["dev"])
    assert "build>=1.2" in dev_dependencies
    assert "tomli>=2; python_version < '3.11'" in dev_dependencies
    assert "twine>=6" in dev_dependencies


def test_changelog_exists_and_mentions_current_version():
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert "## 0.22.0" in changelog
    assert "## 0.21.0" in changelog
    assert "## 0.20.0" in changelog
    assert "## 0.19.0" in changelog
    assert "## 0.16.1" in changelog
    assert "## 0.16.0" in changelog
    assert "## 0.15.0" in changelog
    assert "## 0.14.0" in changelog
    assert "## 0.13.2" in changelog
    assert "## 0.13.1" in changelog
    assert "## 0.13.0" in changelog
    assert "## 0.12.0" in changelog
    assert "## 0.11.0" in changelog
    assert "## 0.10.0" in changelog
    assert "## 0.9.1" in changelog
    assert "## 0.9.0" in changelog
    assert "## 0.8.4" in changelog
    assert "## 0.8.3" in changelog
    assert "## 0.8.2" in changelog
    assert "## 0.8.1" in changelog
    assert "## 0.8.0" in changelog


def test_docs_foundation_exists_and_links_from_readme():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    docs = [
        "overview.md",
        "philosophy.md",
        "installation.md",
        "quickstart.md",
        "cli.md",
        "browser_support.md",
        "window_monitoring.md",
        "inspect.md",
        "troubleshooting.md",
        "architecture.md",
        "integration/rolethread.md",
        "integration/packaging_notes.md",
    ]

    for doc in docs:
        path = REPO_ROOT / "docs" / doc
        assert path.is_file()
        assert path.read_text(encoding="utf-8").strip()
        assert f"docs/{doc}" in readme


def test_internal_docs_are_excluded_from_sdist_config():
    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    exclude = pyproject["tool"]["hatch"]["build"]["targets"]["sdist"]["exclude"]
    assert "/docs/internal" in exclude


def test_dead_diagnostics_module_has_been_removed():
    assert not (REPO_ROOT / "src" / "litlaunch" / "diagnostics.py").exists()


def test_internal_docs_exist_but_are_not_linked_from_public_docs():
    internal_docs = [
        "README.md",
        "rolethread_integration_plan.md",
        "rolethread_handoff_checklist.md",
        "rolethread_runtime_mapping.md",
        "rolethread_test_matrix.md",
        "known_beta_issues.md",
    ]

    for doc in internal_docs:
        path = REPO_ROOT / "docs" / "internal" / doc
        text = path.read_text(encoding="utf-8")
        assert path.is_file()
        assert "INTERNAL / TEMPORARY INTEGRATION DOCUMENTATION" in text
        assert text.strip()

    public_paths = [REPO_ROOT / "README.md"]
    public_paths.extend((REPO_ROOT / "docs").glob("*.md"))
    public_paths.extend((REPO_ROOT / "docs" / "integration").glob("*.md"))

    for path in public_paths:
        assert "docs/internal" not in path.read_text(encoding="utf-8")
