"""Generated artifact and runtime-state paths for LitLaunch."""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

from litlaunch.config import LauncherConfig

ARTIFACT_DIR_NAME = ".litlaunch"
REPORTS_DIR_NAME = "reports"
SHORTCUTS_DIR_NAME = "shortcuts"
TMP_DIR_NAME = "tmp"
BROWSER_PROFILES_DIR_NAME = "browser-profiles"
BROWSER_SHORTCUTS_DIR_NAME = "browser-shortcuts"
OWNED_MARKER = ".litlaunch-owned"


def project_root_for_config(config: LauncherConfig) -> Path:
    """Return the project root LitLaunch should use for generated artifacts."""

    if config.cwd is not None:
        return config.cwd
    app_parent = config.app_path.parent
    if str(app_parent) in ("", "."):
        return Path.cwd()
    return app_parent


def artifact_dir(root: Path | None = None) -> Path:
    """Return the root generated-artifacts directory for a project."""

    return (root or Path.cwd()) / ARTIFACT_DIR_NAME


def runtime_state_root_for_config(config: LauncherConfig) -> Path:
    """Return the root LitLaunch should use for ephemeral runtime state."""

    if config.runtime_state_root is not None:
        root = config.runtime_state_root.expanduser()
        if root.is_absolute():
            return root
        return project_root_for_config(config) / root
    return default_runtime_state_root()


def default_runtime_state_root() -> Path:
    """Return the default temp-owned LitLaunch runtime state root."""

    return Path(tempfile.gettempdir()) / "litlaunch" / "runtime"


def reports_dir(root: Path | None = None, *, create: bool = False) -> Path:
    """Return the reports artifact directory."""

    path = artifact_dir(root) / REPORTS_DIR_NAME
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def shortcuts_dir(root: Path | None = None, *, create: bool = False) -> Path:
    """Return the shortcut artifact directory."""

    path = artifact_dir(root) / SHORTCUTS_DIR_NAME
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def browser_profiles_dir(root: Path | None = None, *, create: bool = False) -> Path:
    """Return the managed browser-profile runtime directory."""

    path = (root or default_runtime_state_root()) / BROWSER_PROFILES_DIR_NAME
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def browser_shortcuts_dir(root: Path | None = None, *, create: bool = False) -> Path:
    """Return the managed browser shortcut runtime directory."""

    path = (root or default_runtime_state_root()) / BROWSER_SHORTCUTS_DIR_NAME
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def default_report_path(
    root: Path | None = None, *, create_parent: bool = False
) -> Path:
    """Return the default human-readable HTML report path."""

    return reports_dir(root, create=create_parent) / "litlaunch-report.html"


def default_shortcut_path(root: Path, basename: str, extension: str) -> Path:
    """Return the default project-local shortcut path."""

    return shortcuts_dir(root) / f"{basename}{extension}"


def create_managed_browser_profile_dir(root: Path | None = None) -> Path:
    """Create a LitLaunch-owned temporary browser profile directory."""

    parent = browser_profiles_dir(root, create=True)
    path = parent / f"litlaunch-browser-{uuid.uuid4().hex}"
    path.mkdir()
    mark_litlaunch_owned(path)
    return path


def mark_litlaunch_owned(path: Path) -> None:
    """Mark a generated directory as safe for LitLaunch cleanup."""

    (path / OWNED_MARKER).write_text("owned by LitLaunch\n", encoding="utf-8")


def is_litlaunch_owned(path: Path) -> bool:
    """Return whether a directory has LitLaunch's cleanup ownership marker."""

    return (path / OWNED_MARKER).is_file()


def cleanup_litlaunch_owned_dir(path: Path) -> None:
    """Best-effort cleanup for a directory LitLaunch created and marked."""

    if not path.exists():
        return
    if not path.is_dir():
        return
    if not is_litlaunch_owned(path):
        return
    shutil.rmtree(path, ignore_errors=True)
