import tempfile
from pathlib import Path

from litlaunch.profile_detection import detect_app_root


def write(path: Path, text: str = "print('hello')\n") -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_detects_app_py_as_strong_default():
    with tempfile.TemporaryDirectory(prefix="RoleThread Test-", dir=Path.cwd()) as path:
        root = Path(path)
        write(root / "app.py")

        detection = detect_app_root(root)

        assert detection.app_path == Path("app.py")
        assert detection.app_path_strength == "strong"
        assert detection.suggested_profile_name.startswith("rolethread-test")
        assert detection.suggested_title.startswith("Rolethread Test")
        assert detection.config_path == root.resolve() / "litlaunch.toml"
        assert detection.config_exists is False


def test_detects_streamlit_app_py_before_main_py():
    with tempfile.TemporaryDirectory(
        prefix="litlaunch-detect-",
        dir=Path.cwd(),
    ) as path:
        root = Path(path)
        write(root / "main.py")
        write(root / "streamlit_app.py")

        detection = detect_app_root(root)

        assert detection.app_path == Path("streamlit_app.py")
        assert detection.app_path_strength == "strong"


def test_detects_main_py_as_weak_fallback():
    with tempfile.TemporaryDirectory(
        prefix="litlaunch-detect-",
        dir=Path.cwd(),
    ) as path:
        root = Path(path)
        write(root / "main.py")

        detection = detect_app_root(root)

        assert detection.app_path == Path("main.py")
        assert detection.app_path_strength == "weak"


def test_detects_existing_litlaunch_config_and_profiles():
    with tempfile.TemporaryDirectory(
        prefix="litlaunch-detect-",
        dir=Path.cwd(),
    ) as path:
        root = Path(path)
        write(root / "app.py")
        write(
            root / "litlaunch.toml",
            """
[profiles.web]
app_path = "app.py"

[profiles.browser]
app_path = "app.py"
mode = "browser"
""",
        )

        detection = detect_app_root(root)

        assert detection.config_exists is True
        assert detection.existing_profile_names == ("browser", "web")
