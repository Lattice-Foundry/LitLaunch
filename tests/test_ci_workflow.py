from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_workflow_exists_with_expected_triggers():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert WORKFLOW_PATH.is_file()
    assert "push:" in workflow
    assert "pull_request:" in workflow
    assert "workflow_dispatch:" in workflow


def test_ci_workflow_runs_test_lint_format_and_release_hygiene():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert 'python -m pip install -e ".[dev]"' in workflow
    assert "python -m pytest" in workflow
    assert "python -m ruff check ." in workflow
    assert "python -m ruff format --check ." in workflow
    assert "python scripts/check_release.py" in workflow


def test_ci_workflow_includes_cross_platform_python_matrix():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    for os_name in ("windows-latest", "ubuntu-latest", "macos-latest"):
        assert os_name in workflow
    for python_version in ('"3.10"', '"3.12"', '"3.14"'):
        assert python_version in workflow
