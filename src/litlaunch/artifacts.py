"""Project-local generated artifact paths for LitLaunch."""

from __future__ import annotations

import tempfile
from pathlib import Path

from litlaunch.config import LauncherConfig

ARTIFACT_DIR_NAME = ".litlaunch"
REPORTS_DIR_NAME = "reports"
SHORTCUTS_DIR_NAME = "shortcuts"
TMP_DIR_NAME = "tmp"
BROWSER_PROFILES_DIR_NAME = "browser-profiles"
BROWSER_SHORTCUTS_DIR_NAME = "browser-shortcuts"


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
    """Return the managed browser-profile temp directory."""

    path = artifact_dir(root) / TMP_DIR_NAME / BROWSER_PROFILES_DIR_NAME
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def browser_shortcuts_dir(root: Path | None = None, *, create: bool = False) -> Path:
    """Return the managed browser shortcut temp directory."""

    path = artifact_dir(root) / TMP_DIR_NAME / BROWSER_SHORTCUTS_DIR_NAME
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
    """Create a project-local temporary browser profile directory."""

    parent = browser_profiles_dir(root, create=True)
    return Path(tempfile.mkdtemp(prefix="litlaunch-browser-", dir=parent))
