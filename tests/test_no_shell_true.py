from pathlib import Path


def test_shell_true_literal_does_not_appear_in_package_source():
    package_root = Path(__file__).parents[1] / "src" / "litlaunch"

    for path in package_root.rglob("*.py"):
        assert "shell=True" not in path.read_text(encoding="utf-8"), path
