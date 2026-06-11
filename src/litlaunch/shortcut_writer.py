"""Reusable launch shortcut generation for LitLaunch profiles."""

from __future__ import annotations

import shutil
import stat
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from litlaunch.artifacts import default_shortcut_path
from litlaunch.exceptions import ConfigurationError
from litlaunch.platforms import OperatingSystem, PlatformInfo
from litlaunch.profiles import LaunchProfile
from litlaunch.windows_shortcut import join_windows_arguments, write_windows_shortcut


class ShortcutKind(str, Enum):
    """Supported shortcut artifact styles."""

    NATIVE = "native"
    SCRIPT = "script"


@dataclass(frozen=True)
class ShortcutFile:
    """A file contained by a generated shortcut artifact."""

    relative_path: Path
    content: str
    executable: bool = False


@dataclass(frozen=True)
class ShortcutRequest:
    """Inputs for building a profile launch shortcut."""

    profile: LaunchProfile
    platform: PlatformInfo
    config_path: Path | None = None
    output_path: Path | None = None
    name: str | None = None
    kind: ShortcutKind | str = ShortcutKind.NATIVE


@dataclass(frozen=True)
class ShortcutPlan:
    """Resolved shortcut path and file content."""

    profile_name: str
    platform: OperatingSystem
    kind: ShortcutKind
    app_root: Path
    output_path: Path
    command: tuple[str, ...]
    app_icon: Path | None
    content: str
    executable: bool
    files: tuple[ShortcutFile, ...] = ()


def build_shortcut_plan(request: ShortcutRequest) -> ShortcutPlan:
    """Build a deterministic OS-appropriate shortcut plan."""

    profile = request.profile
    kind = _normalize_shortcut_kind(request.kind)
    app_root = _resolve_app_root(profile)
    basename = request.name or profile.name
    extension = _shortcut_extension(request.platform.os, kind)
    output_path = (
        Path(request.output_path)
        if request.output_path is not None
        else default_shortcut_path(app_root, basename, extension)
    )
    command = _shortcut_command(
        profile.name,
        request.config_path,
        python_executable=request.platform.python_executable,
    )
    return _render_shortcut_plan(
        profile_name=profile.name,
        platform=request.platform.os,
        kind=kind,
        app_root=app_root,
        output_path=output_path,
        command=command,
        app_icon=profile.config.app_icon,
    )


def write_shortcut(plan: ShortcutPlan, *, force: bool = False) -> ShortcutPlan:
    """Write a shortcut plan to disk."""

    if plan.output_path.exists() and not force:
        raise ConfigurationError(
            f"Shortcut already exists: {plan.output_path}. Use --force to overwrite."
        )
    if plan.output_path.exists() and force:
        _remove_existing_shortcut(plan.output_path)

    plan.output_path.parent.mkdir(parents=True, exist_ok=True)
    if plan.platform == OperatingSystem.WINDOWS and plan.kind == ShortcutKind.NATIVE:
        _write_windows_lnk(plan)
        return plan

    if plan.files:
        plan.output_path.mkdir(parents=True, exist_ok=True)
        for file in plan.files:
            path = plan.output_path / file.relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(file.content, encoding="utf-8", newline="")
            if file.executable:
                _mark_executable(path)
        return plan

    plan.output_path.write_text(plan.content, encoding="utf-8", newline="")
    if plan.executable:
        _mark_executable(plan.output_path)
    return plan


def _normalize_shortcut_kind(value: ShortcutKind | str) -> ShortcutKind:
    try:
        return value if isinstance(value, ShortcutKind) else ShortcutKind(str(value))
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ShortcutKind)
        raise ConfigurationError(
            f"Unknown shortcut kind: {value}. Choose {allowed}."
        ) from exc


def _resolve_app_root(profile: LaunchProfile) -> Path:
    if profile.config.cwd is not None:
        return profile.config.cwd
    app_parent = profile.config.app_path.parent
    if str(app_parent):
        return app_parent
    return Path.cwd()


def _shortcut_icon_path(path: Path, app_root: Path) -> Path:
    return path if path.is_absolute() else app_root / path


def _shortcut_extension(os_name: OperatingSystem, kind: ShortcutKind) -> str:
    if kind == ShortcutKind.SCRIPT:
        if os_name == OperatingSystem.WINDOWS:
            return ".bat"
        if os_name == OperatingSystem.MACOS:
            return ".command"
        return ".sh"
    if os_name == OperatingSystem.WINDOWS:
        return ".lnk"
    if os_name == OperatingSystem.MACOS:
        return ".app"
    return ".desktop"


def _shortcut_command(
    profile_name: str,
    config_path: Path | None,
    *,
    python_executable: str,
) -> tuple[str, ...]:
    command = [
        python_executable or sys.executable,
        "-m",
        "litlaunch.cli",
        "--profile",
        profile_name,
    ]
    if config_path is not None:
        command.extend(("--config", str(Path(config_path).resolve())))
    return tuple(command)


def _render_shortcut_plan(
    *,
    profile_name: str,
    platform: OperatingSystem,
    kind: ShortcutKind,
    app_root: Path,
    output_path: Path,
    command: tuple[str, ...],
    app_icon: Path | None,
) -> ShortcutPlan:
    if kind == ShortcutKind.NATIVE and platform == OperatingSystem.WINDOWS:
        content = _render_windows_lnk_preview(
            app_root=app_root,
            command=command,
            app_icon=app_icon,
        )
        return ShortcutPlan(
            profile_name=profile_name,
            platform=platform,
            kind=kind,
            app_root=app_root,
            output_path=output_path,
            command=command,
            app_icon=app_icon,
            content=content,
            executable=False,
        )

    if kind == ShortcutKind.NATIVE and platform == OperatingSystem.LINUX:
        content = _render_linux_desktop(
            profile_name,
            app_root=app_root,
            command=command,
            app_icon=app_icon,
        )
        return ShortcutPlan(
            profile_name=profile_name,
            platform=platform,
            kind=kind,
            app_root=app_root,
            output_path=output_path,
            command=command,
            app_icon=app_icon,
            content=content,
            executable=True,
        )

    if kind == ShortcutKind.NATIVE and platform == OperatingSystem.MACOS:
        files = _render_macos_app_files(
            profile_name, app_root=app_root, command=command
        )
        content = "\n\n".join(
            f"# {file.relative_path.as_posix()}\n{file.content}" for file in files
        )
        return ShortcutPlan(
            profile_name=profile_name,
            platform=platform,
            kind=kind,
            app_root=app_root,
            output_path=output_path,
            command=command,
            app_icon=app_icon,
            content=content,
            executable=True,
            files=files,
        )

    content, executable = _render_script_shortcut(
        platform=platform,
        app_root=app_root,
        command=command,
    )
    return ShortcutPlan(
        profile_name=profile_name,
        platform=platform,
        kind=kind,
        app_root=app_root,
        output_path=output_path,
        command=command,
        app_icon=app_icon,
        content=content,
        executable=executable,
    )


def _render_windows_lnk_preview(
    *,
    app_root: Path,
    command: tuple[str, ...],
    app_icon: Path | None,
) -> str:
    target, *arguments = command
    lines = [
        "Windows shortcut (.lnk)",
        f"Target: {target}",
        f"Arguments: {_join_windows_arguments(tuple(arguments))}",
        f"Start in: {app_root}",
    ]
    if app_icon is not None:
        lines.append(f"Icon: {_shortcut_icon_path(app_icon, app_root)}")
    lines.append("")
    return "\n".join(lines)


def _write_windows_lnk(plan: ShortcutPlan) -> None:
    target, *arguments = plan.command
    write_windows_shortcut(
        shortcut_path=plan.output_path,
        target_path=target,
        arguments=_join_windows_arguments(tuple(arguments)),
        working_directory=plan.app_root,
        icon_path=(
            _shortcut_icon_path(plan.app_icon, plan.app_root)
            if plan.app_icon is not None
            else None
        ),
    )


def _render_linux_desktop(
    profile_name: str,
    *,
    app_root: Path,
    command: tuple[str, ...],
    app_icon: Path | None,
) -> str:
    name = _display_name(profile_name)
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={_escape_desktop_value(name)}",
        f"Exec={_join_desktop_exec(command)}",
        f"Path={_escape_desktop_value(str(app_root))}",
        "Terminal=true",
        "Categories=Development;",
    ]
    if app_icon is not None:
        icon_value = _escape_desktop_value(str(_shortcut_icon_path(app_icon, app_root)))
        lines.append(f"Icon={icon_value}")
    lines.append("")
    return "\n".join(lines)


def _render_macos_app_files(
    profile_name: str,
    *,
    app_root: Path,
    command: tuple[str, ...],
) -> tuple[ShortcutFile, ...]:
    bundle_id = _macos_bundle_id(profile_name)
    plist = "\n".join(
        (
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
            '<plist version="1.0">',
            "<dict>",
            "  <key>CFBundleExecutable</key>",
            "  <string>launch</string>",
            "  <key>CFBundleIdentifier</key>",
            f"  <string>{bundle_id}</string>",
            "  <key>CFBundleName</key>",
            f"  <string>{_xml_escape(_display_name(profile_name))}</string>",
            "  <key>CFBundlePackageType</key>",
            "  <string>APPL</string>",
            "</dict>",
            "</plist>",
            "",
        )
    )
    launcher = "\n".join(
        (
            "#!/bin/sh",
            "set -e",
            f"cd {_quote_posix(str(app_root))}",
            f"exec {_join_posix(command)}",
            "",
        )
    )
    return (
        ShortcutFile(Path("Contents") / "Info.plist", plist),
        ShortcutFile(Path("Contents") / "MacOS" / "launch", launcher, executable=True),
    )


def _render_script_shortcut(
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


def _remove_existing_shortcut(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _mark_executable(path: Path) -> None:
    current_mode = path.stat().st_mode
    path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _join_windows(parts: tuple[str, ...]) -> str:
    return " ".join(_quote_windows(part) for part in parts)


def _join_windows_arguments(parts: tuple[str, ...]) -> str:
    return join_windows_arguments(parts)


def _join_posix(parts: tuple[str, ...]) -> str:
    return " ".join(_quote_posix(part) for part in parts)


def _join_desktop_exec(parts: tuple[str, ...]) -> str:
    return " ".join(_quote_desktop_exec(part) for part in parts)


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


def _quote_desktop_exec(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("`", "\\`")
    )
    if any(char.isspace() for char in escaped) or any(
        char in escaped for char in ('"', "'", "\\", "$", "`")
    ):
        return f'"{escaped}"'
    return escaped


def _escape_desktop_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n")


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _display_name(name: str) -> str:
    return name.replace("-", " ").replace("_", " ").title()


def _macos_bundle_id(name: str) -> str:
    cleaned = "".join(
        char.lower() if char.isalnum() else "." for char in name.strip()
    ).strip(".")
    while ".." in cleaned:
        cleaned = cleaned.replace("..", ".")
    return f"app.litlaunch.{cleaned or 'shortcut'}"
