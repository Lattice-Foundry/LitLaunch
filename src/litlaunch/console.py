"""Dependency-free console rendering for LitLaunch runtime events."""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import TextIO

from litlaunch.lifecycle import LaunchEvent, LaunchState
from litlaunch.shutdown import ShutdownHookResult

ANSI_PATTERN = re.compile(r"\033\[[0-9;]*m")


class ConsoleMode(str, Enum):
    """Console output verbosity."""

    QUIET = "quiet"
    NORMAL = "normal"
    VERBOSE = "verbose"


class ConsoleColor(str, Enum):
    """Named console colors supported by the default theme."""

    STREAMLIT_BLUE = "streamlit_blue"
    ACCENT = "accent"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    MUTED = "muted"
    RESET = "reset"


ANSI_COLORS: Mapping[str, str] = {
    "streamlit_blue": "\033[38;2;28;131;225m",
    "indigo": "\033[38;2;99;102;241m",
    "cyan": "\033[38;2;6;182;212m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "gray": "\033[90m",
    "reset": "\033[0m",
}


@dataclass(frozen=True)
class ConsoleTheme:
    """Named color choices for LitLaunch console output."""

    primary: str = "streamlit_blue"
    accent: str = "indigo"
    success: str = "green"
    warning: str = "yellow"
    error: str = "red"
    muted: str = "gray"
    use_color: bool = field(default_factory=lambda: "NO_COLOR" not in os.environ)


class ConsoleRenderer:
    """Render concise console output to an injected stream."""

    def __init__(
        self,
        *,
        theme: ConsoleTheme | None = None,
        mode: ConsoleMode | str = ConsoleMode.NORMAL,
        stream: TextIO | None = None,
        env: Mapping[str, str] | None = None,
        redacted_values: Sequence[str] = (),
    ) -> None:
        self.theme = theme or ConsoleTheme()
        self.mode = _normalize_mode(mode)
        self.stream = stream if stream is not None else sys.stdout
        self.env = env if env is not None else os.environ
        self._redacted_values = tuple(
            str(value) for value in redacted_values if str(value)
        )

    @property
    def use_color(self) -> bool:
        """Return whether ANSI color should be emitted."""

        return self.theme.use_color and "NO_COLOR" not in self.env

    def add_redaction(self, value: str | None) -> None:
        """Redact an exact sensitive value from future output."""

        if value:
            self._redacted_values = (*self._redacted_values, str(value))

    def header(self, title: str, subtitle: str | None = None) -> None:
        """Render a launch header."""

        if self.mode == ConsoleMode.QUIET:
            return
        self._emit(self._style(title, self.theme.primary))
        if subtitle:
            self._emit(self._style(subtitle, self.theme.muted))

    def step(self, message: str) -> None:
        """Render a normal runtime milestone."""

        if self.mode == ConsoleMode.QUIET:
            return
        self._emit(f"{self._style('>', self.theme.accent)} {message}")

    def success(self, message: str) -> None:
        """Render a success message."""

        if self.mode == ConsoleMode.QUIET:
            return
        self._emit(f"{self._style('ok', self.theme.success)} {message}")

    def warning(self, message: str) -> None:
        """Render a warning message."""

        self._emit(f"{self._style('warn', self.theme.warning)} {message}")

    def error(self, message: str) -> None:
        """Render an error message."""

        self._emit(f"{self._style('error', self.theme.error)} {message}")

    def info(self, message: str) -> None:
        """Render an informational message."""

        if self.mode == ConsoleMode.QUIET:
            return
        self._emit(message)

    def detail(self, message: str) -> None:
        """Render a verbose-only detail line."""

        if self.mode != ConsoleMode.VERBOSE:
            return
        self._emit(f"{self._style('-', self.theme.muted)} {message}")

    def blank(self) -> None:
        """Render a blank line."""

        if self.mode == ConsoleMode.QUIET:
            return
        self._emit("")

    def render_launch_event(self, event: LaunchEvent) -> None:
        """Render one launcher lifecycle event."""

        if event.state == LaunchState.FAILED:
            self.error(event.message)
        elif event.state == LaunchState.TERMINATED:
            self.success(event.message)
        elif event.state == LaunchState.TERMINATING:
            self.warning(event.message)
        elif event.state in {
            LaunchState.HEALTHY,
            LaunchState.RUNNING,
            LaunchState.PROCESS_RUNNING,
        }:
            self.success(event.message)
        else:
            self.step(event.message)

    def _render_shutdown_hook_start(self, label: str, color: str | None = None) -> None:
        """Render shutdown hook start metadata."""

        self.step(self._with_optional_label_color(f"Shutdown hook: {label}", color))

    def _render_shutdown_hook_result(self, result: ShutdownHookResult) -> None:
        """Render one shutdown hook result."""

        message = self._with_optional_label_color(result.message, result.color)
        if result.ok:
            self.success(message)
        else:
            self.error(message)

    def _emit(self, text: str) -> None:
        safe_text = self._redact(str(text))
        self.stream.write(f"{safe_text}\n")
        flush = getattr(self.stream, "flush", None)
        if callable(flush):
            flush()

    def _style(self, text: str, color_name: str) -> str:
        if not self.use_color:
            return text
        color = ANSI_COLORS.get(color_name, "")
        reset = ANSI_COLORS["reset"]
        return f"{color}{text}{reset}" if color else text

    def _with_optional_label_color(self, message: str, color: str | None) -> str:
        if color is None:
            return message
        label, separator, rest = message.partition(":")
        if not separator:
            return self._style(message, color)
        return f"{self._style(label + separator, color)}{rest}"

    def _redact(self, text: str) -> str:
        redacted = text
        for value in self._redacted_values:
            redacted = redacted.replace(value, "[redacted]")
        return redacted


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from console output."""

    return ANSI_PATTERN.sub("", text)


def _normalize_mode(mode: ConsoleMode | str) -> ConsoleMode:
    if isinstance(mode, ConsoleMode):
        return mode
    return ConsoleMode(str(mode).strip().lower())
