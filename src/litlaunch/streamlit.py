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

    def build(self, *, port: int | None = None) -> tuple[str, ...]:
        """Return a shell-free command tuple for Streamlit."""

        if not self.python_executable:
            raise CommandBuildError("A Python executable is required.")

        user_flag_names = _streamlit_flag_names(self.config.streamlit_flags)
        command: list[str] = [
            str(self.python_executable),
            "-m",
            "streamlit",
            "run",
            str(self.config.app_path),
        ]
        if "server.address" not in user_flag_names:
            command.extend(("--server.address", self.config.host))
        if "server.headless" not in user_flag_names:
            command.extend(
                ("--server.headless", _format_bool(self._resolve_headless()))
            )

        resolved_port = self.config.port if port is None else port
        if resolved_port is not None and "server.port" not in user_flag_names:
            command.extend(("--server.port", str(resolved_port)))

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


def _streamlit_flag_names(
    flags: Mapping[str, str | int | float | bool | None] | Sequence[str],
) -> frozenset[str]:
    if isinstance(flags, Mapping):
        return frozenset(_normalize_flag_name(key) for key in flags)

    names: set[str] = set()
    for item in flags:
        value = str(item).strip()
        if value.startswith("--"):
            names.add(_normalize_flag_name(value))
    return frozenset(names)


def _normalize_flag_name(name: str) -> str:
    stripped = str(name).strip()
    if stripped.startswith("--"):
        stripped = stripped[2:]
    return stripped.split("=", 1)[0].strip().lower()


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
