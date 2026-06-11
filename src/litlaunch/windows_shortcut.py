"""Windows shortcut helpers shared by launch and shortcut generation."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from litlaunch.exceptions import ConfigurationError


def write_windows_shortcut(
    *,
    shortcut_path: Path,
    target_path: str,
    arguments: str,
    working_directory: Path,
    icon_path: Path | None = None,
) -> None:
    """Create a Windows .lnk shortcut through the supported Shell COM API."""

    script = (
        "param(\n"
        "  [string]$ShortcutPath,\n"
        "  [string]$TargetPath,\n"
        "  [string]$ShortcutArguments,\n"
        "  [string]$WorkingDirectory,\n"
        "  [string]$IconPath\n"
        ")\n"
        "$ErrorActionPreference = 'Stop'\n"
        "$shell = New-Object -ComObject WScript.Shell\n"
        "$shortcut = $shell.CreateShortcut($ShortcutPath)\n"
        "$shortcut.TargetPath = $TargetPath\n"
        "$shortcut.Arguments = $ShortcutArguments\n"
        "$shortcut.WorkingDirectory = $WorkingDirectory\n"
        "if ($IconPath) { $shortcut.IconLocation = $IconPath }\n"
        "$shortcut.Save()\n"
    )
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="litlaunch-shortcut-") as temp_dir:
        script_path = Path(temp_dir) / "create-shortcut.ps1"
        script_path.write_text(script, encoding="utf-8")
        command = (
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            str(shortcut_path),
            target_path,
            arguments,
            str(working_directory),
            str(icon_path) if icon_path is not None else "",
        )
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            detail = getattr(exc, "stderr", "") or str(exc)
            raise ConfigurationError(
                f"Could not create Windows shortcut: {detail}"
            ) from exc


def join_windows_arguments(parts: tuple[str, ...]) -> str:
    """Return a Windows shortcut argument string."""

    return " ".join(_quote_windows_argument(part) for part in parts)


def _quote_windows_argument(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
