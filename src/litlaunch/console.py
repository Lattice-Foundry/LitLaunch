"""Dependency-free console rendering for LitLaunch runtime events."""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar, TextIO

from litlaunch.browsers import BrowserResolution
from litlaunch.colors import (
    THEME_COLORS,
    muted_amber,
    muted_gray,
    powershell_red,
    streamlit_blue,
    success_green,
    terminal_green,
)
from litlaunch.lifecycle import LaunchEvent, LaunchState
from litlaunch.shutdown import ShutdownHookResult
from litlaunch.windowing import WindowMonitorResult, WindowMonitorStatus

ANSI_PATTERN = re.compile(r"\033\[[0-9;]*m")


class ConsoleMode(str, Enum):
    """Console output verbosity."""

    QUIET = "quiet"
    NORMAL = "normal"
    VERBOSE = "verbose"


class ConsolePhase(str, Enum):
    """Runtime phase labels used by LitLaunch console output."""

    BACKEND = "Backend"
    HEALTH = "Health"
    BROWSER = "Browser"
    MONITOR = "Monitor"
    RUNTIME = "Runtime"
    SHUTDOWN = "Shutdown"
    STOPPING_BACKEND = "Stopping backend"
    HOOK = "Hook"


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
    **{name: color.ansi for name, color in THEME_COLORS.items()},
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

    prefix: ClassVar[str] = "[LitLaunch]"

    primary: str = terminal_green
    accent: str = streamlit_blue
    brand: str = terminal_green
    label: str = streamlit_blue
    success: str = success_green
    warning: str = muted_amber
    error: str = powershell_red
    muted: str = muted_gray
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

    def runtime_start(self, message: str = "Starting runtime") -> None:
        """Render the fixed LitLaunch runtime prefix and start message."""

        if self.mode == ConsoleMode.QUIET:
            return
        prefix = self._style(self.theme.prefix, self.theme.brand)
        self._emit(f"{prefix} {message}")

    def step(self, message: str) -> None:
        """Render a normal runtime milestone."""

        if self.mode == ConsoleMode.QUIET:
            return
        self._emit(f"{self._style('>', self.theme.accent)} {message}")

    def phase(
        self,
        phase: ConsolePhase | str,
        message: str,
        *,
        elapsed_seconds: float | None = None,
        level: str = "info",
    ) -> None:
        """Render one concise runtime phase line."""

        if self.mode == ConsoleMode.QUIET and level not in {"warning", "error"}:
            return
        label = phase.value if isinstance(phase, ConsolePhase) else str(phase)
        label_text = self._style(f"{label}:", self.theme.label)
        elapsed = (
            f" in {format_elapsed(elapsed_seconds)}"
            if elapsed_seconds is not None
            else ""
        )
        line = f"{self.theme.prefix}   {label_text} {message}{elapsed}"
        if level == "warning":
            self.warning(line)
        elif level == "error":
            self.error(line)
        elif level == "success":
            self.success(line)
        else:
            self._emit(line)

    def phase_start(self, phase: ConsolePhase | str, message: str) -> None:
        """Render a phase start line."""

        self.phase(phase, message)

    def phase_success(
        self,
        phase: ConsolePhase | str,
        message: str,
        *,
        elapsed_seconds: float | None = None,
    ) -> None:
        """Render a successful phase line."""

        self.phase(
            phase,
            message,
            elapsed_seconds=elapsed_seconds,
            level="success",
        )

    def phase_warning(self, phase: ConsolePhase | str, message: str) -> None:
        """Render a warning phase line."""

        self.phase(phase, message, level="warning")

    def phase_error(self, phase: ConsolePhase | str, message: str) -> None:
        """Render an error phase line."""

        self.phase(phase, message, level="error")

    def runtime_ready(self, url: str | None = None) -> None:
        """Render a concise runtime-ready message."""

        message = "Runtime ready" if url is None else f"Runtime ready at {url}"
        self.success(f"{self.theme.prefix} {message}")

    def render_browser_resolution(
        self,
        resolution: BrowserResolution,
        *,
        prefer_app_mode: bool,
    ) -> None:
        """Render a concise browser fallback summary."""

        selected = resolution.selected
        if selected is None:
            self.phase_error(ConsolePhase.BROWSER, resolution.message)
            return

        first = resolution.fallback_chain[0] if resolution.fallback_chain else selected
        fallback_used = selected.kind != first.kind
        mode_text = "app-mode" if selected.supports_app_mode else "full-browser"
        if fallback_used:
            preserved = selected.supports_app_mode if prefer_app_mode else True
            downgrade = "" if preserved else "; app-mode was not preserved"
            self.phase_warning(
                ConsolePhase.BROWSER,
                (
                    f"{first.name} unavailable; using {selected.name} "
                    f"({mode_text}){downgrade}. Use --browser or install the "
                    "preferred browser to change this."
                ),
            )
            return

        self.detail(f"Browser strategy: {selected.name} ({mode_text}).")

    def render_window_monitor_result(self, result: WindowMonitorResult) -> None:
        """Render a window monitor result without changing monitor behavior."""

        if (
            result.status == WindowMonitorStatus.UNSUPPORTED
            or result.status == WindowMonitorStatus.TIMEOUT
            or result.status == WindowMonitorStatus.ERROR
        ):
            self.phase_error(ConsolePhase.MONITOR, result.message)
        elif result.closed or result.status == WindowMonitorStatus.WINDOW_OBSERVED:
            self.phase_success(ConsolePhase.MONITOR, result.message)
        elif result.status == WindowMonitorStatus.BACKEND_EXITED:
            self.phase_warning(ConsolePhase.MONITOR, result.message)
        else:
            self.phase(ConsolePhase.MONITOR, result.message)

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

        self.phase(ConsolePhase.HOOK, self._with_optional_label_color(label, color))

    def _render_shutdown_hook_result(self, result: ShutdownHookResult) -> None:
        """Render one shutdown hook result."""

        label = self._with_optional_label_color(result.label, result.color)
        message = f"{label}: {result.message}"
        if result.ok:
            self.phase_success(ConsolePhase.HOOK, message)
        else:
            self.phase_error(ConsolePhase.HOOK, message)

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


def format_elapsed(seconds: float) -> str:
    """Format elapsed seconds for concise console output."""

    return f"{max(0.0, seconds):.1f}s"


def _normalize_mode(mode: ConsoleMode | str) -> ConsoleMode:
    if isinstance(mode, ConsoleMode):
        return mode
    return ConsoleMode(str(mode).strip().lower())
