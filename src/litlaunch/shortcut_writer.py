"""Reusable launch shortcut generation for LitLaunch profiles."""

from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

from litlaunch.exceptions import ConfigurationError
from litlaunch.platforms import OperatingSystem, PlatformInfo
from litlaunch.profiles import LaunchProfile


@dataclass(frozen=True)
class ShortcutRequest:
    """Inputs for building a profile launch shortcut."""

    profile: LaunchProfile
    platform: PlatformInfo
    config_path: Path | None = None
    output_path: Path | None = None
    name: str | None = None


@dataclass(frozen=True)
class ShortcutPlan:
    """Resolved shortcut path and file content."""

    profile_name: str
    platform: OperatingSystem
    app_root: Path
    output_path: Path
    command: tuple[str, ...]
    content: str
    executable: bool


def build_shortcut_plan(request: ShortcutRequest) -> ShortcutPlan:
    """Build a deterministic OS-appropriate shortcut plan."""

    profile = request.profile
    app_root = _resolve_app_root(profile)
    basename = request.name or profile.name
    extension = _shortcut_extension(request.platform.os)
    output_path = (
        request.output_path
        if request.output_path is not None
        else app_root / f"{basename}{extension}"
    )
    command = _shortcut_command(profile.name, request.config_path)
    content, executable = _render_shortcut(
        platform=request.platform.os,
        app_root=app_root,
        command=command,
    )
    return ShortcutPlan(
        profile_name=profile.name,
        platform=request.platform.os,
        app_root=app_root,
        output_path=Path(output_path),
        command=command,
        content=content,
        executable=executable,
    )


def write_shortcut(plan: ShortcutPlan, *, force: bool = False) -> ShortcutPlan:
    """Write a shortcut plan to disk."""

    if plan.output_path.exists() and not force:
        raise ConfigurationError(
            f"Shortcut already exists: {plan.output_path}. Use --force to overwrite."
        )
    plan.output_path.parent.mkdir(parents=True, exist_ok=True)
    plan.output_path.write_text(plan.content, encoding="utf-8", newline="")
    if plan.executable:
        current_mode = plan.output_path.stat().st_mode
        plan.output_path.chmod(
            current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        )
    return plan


def _resolve_app_root(profile: LaunchProfile) -> Path:
    if profile.config.cwd is not None:
        return profile.config.cwd
    app_parent = profile.config.app_path.parent
    if str(app_parent):
        return app_parent
    return Path.cwd()


def _shortcut_extension(os_name: OperatingSystem) -> str:
    if os_name == OperatingSystem.WINDOWS:
        return ".bat"
    if os_name == OperatingSystem.MACOS:
        return ".command"
    return ".sh"


def _shortcut_command(
    profile_name: str,
    config_path: Path | None,
) -> tuple[str, ...]:
    command = ["litlaunch", "--profile", profile_name]
    if config_path is not None:
        command.extend(("--config", str(config_path)))
    return tuple(command)


def _render_shortcut(
    *,
    platform: OperatingSystem,
    app_root: Path,
    command: tuple[str, ...],
) -> tuple[str, bool]:
    if platform == OperatingSystem.WINDOWS:
        content = "\r\n".join(
            (
                "@echo off",
                f"cd /d {_quote_windows(str(app_root))}",
                _join_windows(command),
                "",
            )
        )
        return content, False
    content = "\n".join(
        (
            "#!/usr/bin/env sh",
            "set -e",
            f"cd {_quote_posix(str(app_root))}",
            _join_posix(command),
            "",
        )
    )
    return content, True


def _join_windows(parts: tuple[str, ...]) -> str:
    return " ".join(_quote_windows(part) for part in parts)


def _join_posix(parts: tuple[str, ...]) -> str:
    return " ".join(_quote_posix(part) for part in parts)


def _quote_windows(value: str) -> str:
    escaped = value
    for raw, replacement in (
        ("^", "^^"),
        ("%", "%%"),
        ('"', '^"'),
        ("&", "^&"),
        ("<", "^<"),
        (">", "^>"),
        ("|", "^|"),
    ):
        escaped = escaped.replace(raw, replacement)
    return f'"{escaped}"'


def _quote_posix(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"
