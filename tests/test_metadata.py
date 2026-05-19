from pathlib import Path

import tomllib

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
    assert "twine>=6" in dev_dependencies


def test_changelog_exists_and_mentions_current_version():
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert "## 0.10.0" in changelog
    assert "## 0.9.1" in changelog
    assert "## 0.9.0" in changelog
    assert "## 0.8.4" in changelog
    assert "## 0.8.3" in changelog
    assert "## 0.8.2" in changelog
    assert "## 0.8.1" in changelog
    assert "## 0.8.0" in changelog
