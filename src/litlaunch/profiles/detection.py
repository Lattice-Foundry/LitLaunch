"""Reusable app-root detection for profile creation workflows."""

from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass
from pathlib import Path

from litlaunch.exceptions import ConfigurationError

from .core import _presentation_path, load_profiles


@dataclass(frozen=True)
class AppRootDetection:
    """Deterministic defaults detected from an app root."""

    cwd: Path
    project_folder_name: str
    suggested_profile_name: str
    suggested_title: str
    app_path: Path | None
    app_path_strength: str | None
    config_path: Path
    config_exists: bool
    existing_profile_names: tuple[str, ...]
    streamlit_available: bool


def detect_app_root(cwd: str | Path | None = None) -> AppRootDetection:
    """Detect deterministic profile defaults from a working directory."""

    root = Path.cwd() if cwd is None else Path(cwd)
    root = _presentation_path(root)
    config_path = root / "litlaunch.toml"
    existing_profile_names = _existing_profile_names(config_path)
    return AppRootDetection(
        cwd=root,
        project_folder_name=root.name,
        suggested_profile_name=slugify_profile_name(root.name),
        suggested_title=title_from_folder(root.name),
        app_path=_detect_app_path(root),
        app_path_strength=_detect_app_path_strength(root),
        config_path=config_path,
        config_exists=config_path.is_file(),
        existing_profile_names=existing_profile_names,
        streamlit_available=importlib.util.find_spec("streamlit") is not None,
    )


def slugify_profile_name(value: str) -> str:
    """Return a valid profile-name suggestion from arbitrary text."""

    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip().lower()).strip("-")
    return slug or "my-webapp"


def title_from_folder(value: str) -> str:
    """Return a readable app-title suggestion from a folder name."""

    cleaned = re.sub(r"[_-]+", " ", value).strip()
    return cleaned.title() if cleaned else "My App"


def _detect_app_path(root: Path) -> Path | None:
    for name in ("app.py", "streamlit_app.py", "main.py"):
        path = root / name
        if path.is_file():
            return Path(name)
    return None


def _detect_app_path_strength(root: Path) -> str | None:
    app_path = _detect_app_path(root)
    if app_path is None:
        return None
    if app_path.name in {"app.py", "streamlit_app.py"}:
        return "strong"
    return "weak"


def _existing_profile_names(config_path: Path) -> tuple[str, ...]:
    if not config_path.is_file():
        return ()
    try:
        return tuple(sorted(load_profiles(config_path)))
    except ConfigurationError:
        return ()
