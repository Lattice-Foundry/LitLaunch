"""Streamlit command construction."""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence

from litlaunch.config import LauncherConfig, LaunchMode
from litlaunch.exceptions import CommandBuildError


class StreamlitCommandBuilder:
    """Build deterministic Streamlit command arguments from launcher config."""

    def __init__(
        self,
        config: LauncherConfig,
        *,
        python_executable: str | None = None,
    ) -> None:
        self.config = config
        self.python_executable = python_executable or sys.executable

    def build(self) -> tuple[str, ...]:
        """Return a shell-free command tuple for Streamlit."""

        if not self.python_executable:
            raise CommandBuildError("A Python executable is required.")

        command: list[str] = [
            str(self.python_executable),
            "-m",
            "streamlit",
            "run",
            str(self.config.app_path),
            "--server.address",
            self.config.host,
            "--server.headless",
            _format_bool(self._resolve_headless()),
        ]

        if self.config.port is not None:
            command.extend(("--server.port", str(self.config.port)))

        command.extend(_format_streamlit_flags(self.config.streamlit_flags))

        if self.config.app_args:
            command.append("--")
            command.extend(self.config.app_args)

        return tuple(command)

    def _resolve_headless(self) -> bool:
        if self.config.headless is not None:
            return bool(self.config.headless)
        return self.config.mode == LaunchMode.WEBAPP


def _format_streamlit_flags(
    flags: Mapping[str, str | int | float | bool | None] | Sequence[str],
) -> tuple[str, ...]:
    if isinstance(flags, Mapping):
        parts: list[str] = []
        for key, value in flags.items():
            flag = _format_flag_name(key)
            parts.append(flag)
            if value is not None:
                parts.append(_format_flag_value(value))
        return tuple(parts)
    return tuple(str(item) for item in flags)


def _format_flag_name(name: str) -> str:
    stripped = str(name).strip()
    if not stripped:
        raise CommandBuildError("Streamlit flag names cannot be empty.")
    if stripped.startswith("--"):
        return stripped
    return f"--{stripped}"


def _format_flag_value(value: str | int | float | bool) -> str:
    if isinstance(value, bool):
        return _format_bool(value)
    return str(value)


def _format_bool(value: bool) -> str:
    return "true" if value else "false"
