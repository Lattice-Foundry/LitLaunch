"""Dependency-free console rendering for LitLaunch runtime events."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar, TextIO

from litlaunch.browsers import BrowserResolution
from litlaunch.colors import (
    hook_orange,
    muted_amber,
    muted_gray,
    powershell_red,
    streamlit_blue,
    success_green,
    terminal_green,
)
from litlaunch.console_style import (
    ANSI_PATTERN,
    status_prefix,
    strip_ansi,
    style_text,
)
from litlaunch.lifecycle import LaunchEvent, LaunchState
from litlaunch.shutdown import HookConsoleVisibility, ShutdownHookResult
from litlaunch.windowing import WindowInfo, WindowMonitorResult, WindowMonitorStatus


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
    SHUTDOWN = "Shutdown"
    HOOK = "Hook"


CONSOLE_CATEGORY_LABELS = frozenset(
    {
        "Runtime",
        "Backend",
        "Health",
        "Hook",
        "Browser",
        "Monitor",
        "Shutdown",
    }
)
CONSOLE_CATEGORY_WIDTH = max(len(label) for label in CONSOLE_CATEGORY_LABELS)


def _format_category_label(category: str) -> str:
    padding = " " * max(1, CONSOLE_CATEGORY_WIDTH - len(category) + 1)
    return f"{category}:{padding}"


@dataclass(frozen=True)
class ConsoleTheme:
    """Named color choices for LitLaunch console output."""

    prefix: ClassVar[str] = "LitLaunch"

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
        prefix = self._style(self.theme.prefix, self.theme.success)
        message_text = self._style(_ensure_ellipsis(message), self.theme.accent)
        self.success(f"{prefix} {message_text}")

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
        label_color = (
            hook_orange if label == ConsolePhase.HOOK.value else self.theme.label
        )
        label_text = self._style(_format_category_label(label), label_color)
        message_text = (
            (
                f"{_capitalize_sentence_start(_strip_sentence_punctuation(message))} "
                f"in {format_elapsed(elapsed_seconds)}"
            )
            if elapsed_seconds is not None
            else _punctuate_phase_message(message)
        )
        line = f"{label_text}{message_text}"
        if level == "warning":
            self.warning(line)
        elif level == "error":
            self.error(line)
        elif level == "success":
            self.success(line)
        else:
            self.success(line)

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

    def failure_guidance(
        self,
        summary: str,
        *,
        likely_cause: str | None = None,
        next_steps: Sequence[str] = (),
        suggest_inspect: bool = False,
        docs_hint: str | None = None,
        detail: str | None = None,
        level: str = "error",
    ) -> None:
        """Render calm, actionable failure guidance."""

        if level == "warning":
            self.warning(summary)
        else:
            self.error(summary)
        if self.mode == ConsoleMode.QUIET:
            return
        if self.mode == ConsoleMode.NORMAL:
            if likely_cause:
                self._guidance_line("Likely cause", likely_cause)
            self._guidance_line("Next", "Use verbose mode for more runtime details.")
            return
        if likely_cause:
            self._guidance_line("Likely cause", likely_cause)
        for step in next_steps:
            if _is_verbose_hint(step):
                continue
            self._guidance_line("Next", step)
        if suggest_inspect:
            self._guidance_line(
                "Next",
                'Run "litlaunch inspect" for local diagnostics.',
            )
        if docs_hint:
            self._guidance_line("Docs", docs_hint)
        if detail:
            self.detail(f"Failure detail: {detail}")

    def guidance_line(self, label: str, message: str) -> None:
        """Render one cause/next/docs guidance line."""

        self._guidance_line(label, message)

    def runtime_ready(self, url: str | None = None) -> None:
        """Render a concise runtime-ready message."""

        message = (
            "Runtime: ready" if url is None else f"Runtime: ready locally at {url}"
        )
        self.success(message)

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
        mode_text = (
            "app-mode"
            if prefer_app_mode and selected.supports_app_mode
            else "full-browser"
        )
        if fallback_used:
            preserved = selected.supports_app_mode if prefer_app_mode else True
            self.phase_warning(
                ConsolePhase.BROWSER,
                f"{first.name} unavailable",
            )
            if self.mode != ConsoleMode.QUIET:
                fallback_mode = f"{mode_text} instead"
                if not preserved:
                    fallback_mode = f"{mode_text} instead; app-mode was not preserved"
                self._guidance_line("Next", f"Using {selected.name} {fallback_mode}.")
                self._guidance_line(
                    "Next",
                    "Use --browser to select a different browser.",
                )
            return

        self.detail(f"Browser strategy: {selected.name} ({mode_text}).")

    def render_window_monitor_result(self, result: WindowMonitorResult) -> None:
        """Render a window monitor result without changing monitor behavior."""

        if result.status in {
            WindowMonitorStatus.UNSUPPORTED,
            WindowMonitorStatus.UNAVAILABLE,
        }:
            self.failure_guidance(
                "Monitor: window monitoring is unavailable.",
                likely_cause=result.message,
                next_steps=(
                    "Omit --monitor-window to launch without close detection.",
                    (
                        "Use Chromium app-mode on Windows for the strongest "
                        "supported path."
                    ),
                ),
            )
        elif result.status == WindowMonitorStatus.TIMEOUT:
            self._render_window_monitor_timeout(result)
        elif result.status == WindowMonitorStatus.ERROR:
            self.failure_guidance(
                "Monitor: window monitoring failed.",
                likely_cause=result.message,
                next_steps=(
                    "Omit --monitor-window to run without close detection.",
                    "Use verbose mode to inspect monitor setup details.",
                ),
            )
        elif result.closed:
            message = _strip_sentence_punctuation(result.message) or "Window closed"
            self.phase_success(
                ConsolePhase.MONITOR,
                f"{message}; requesting shutdown",
            )
        elif result.status == WindowMonitorStatus.WINDOW_OBSERVED:
            self.phase_success(ConsolePhase.MONITOR, result.message)
        elif result.status == WindowMonitorStatus.BACKEND_EXITED:
            self.phase_warning(
                ConsolePhase.MONITOR,
                "Backend exited before monitored window closed",
            )
        else:
            self.phase(ConsolePhase.MONITOR, result.message)

    def render_shutdown_hook_result(self, result: ShutdownHookResult) -> None:
        """Render one developer-defined shutdown hook result."""

        message = result.message or result.label
        if result.ok:
            if (
                not result.render
                or (self.mode == ConsoleMode.QUIET and not result.show_in_quiet)
                or (
                    result.console_visibility == HookConsoleVisibility.VERBOSE
                    and self.mode != ConsoleMode.VERBOSE
                    and not (self.mode == ConsoleMode.QUIET and result.show_in_quiet)
                )
            ):
                return
            self._emit_hook_status("ok", self.theme.success, message)
            return

        self._emit_hook_status("error", self.theme.error, message)
        if self.mode == ConsoleMode.QUIET:
            return
        self._guidance_line("Likely cause", "The shutdown hook raised an exception.")
        if self.mode == ConsoleMode.NORMAL:
            self._guidance_line("Next", "Use verbose mode for more runtime details.")
            return
        self._guidance_line("Next", "Inspect the hook implementation.")
        if result.error:
            self.detail(f"Failure detail: {result.error}")

    def success(self, message: str) -> None:
        """Render a success message."""

        if self.mode == ConsoleMode.QUIET:
            return
        self._emit_status("ok", self.theme.success, message)

    def warning(self, message: str) -> None:
        """Render a warning message."""

        self._emit_status("warn", self.theme.warning, message)

    def error(self, message: str) -> None:
        """Render an error message."""

        self._emit_status("error", self.theme.error, message)

    def info(self, message: str) -> None:
        """Render an informational message."""

        if self.mode == ConsoleMode.QUIET:
            return
        self._emit(message)

    def info_status(self, message: str) -> None:
        """Render a neutral informational status line."""

        if self.mode == ConsoleMode.QUIET:
            return
        self._emit_status("info", self.theme.warning, message)

    def next_step(self, message: str) -> None:
        """Render one concise follow-up action line."""

        if self.mode == ConsoleMode.QUIET:
            return
        self._guidance_line("Next", message)

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

    def _emit(self, text: str) -> None:
        safe_text = self._redact(str(text))
        self.stream.write(f"{safe_text}\n")
        flush = getattr(self.stream, "flush", None)
        if callable(flush):
            flush()

    def _style(self, text: str, color_name: str) -> str:
        return style_text(text, color_name, use_color=self.use_color)

    def _status_prefix(self, status: str, color_name: str) -> str:
        return status_prefix(status, color_name, use_color=self.use_color)

    def _emit_status(self, status: str, color_name: str, message: str) -> None:
        message = self._style_category_label(message)
        self._emit(
            f"{self._status_prefix(status, color_name)} "
            f"{_ensure_terminal_punctuation(message)}"
        )

    def _emit_hook_status(
        self,
        status: str,
        color_name: str,
        message: str,
    ) -> None:
        hook_message = self._format_category_message(
            "Hook",
            message,
            category_color=hook_orange,
        )
        self._emit(f"{self._status_prefix(status, color_name)} {hook_message}")

    def _with_optional_label_color(self, message: str, color: str | None) -> str:
        if color is None:
            return message
        label, separator, rest = message.partition(":")
        if not separator:
            return self._style(message, color)
        return f"{self._style(label + separator, color)}{rest}"

    def _style_category_label(self, message: str) -> str:
        if ANSI_PATTERN.search(message):
            return message
        label, separator, rest = message.partition(":")
        if not separator or label not in CONSOLE_CATEGORY_LABELS:
            return message
        color = hook_orange if label == "Hook" else self.theme.label
        label_text = _format_category_label(label)
        message_text = _capitalize_sentence_start(rest.strip())
        return f"{self._style(label_text, color)}{message_text}"

    def _format_category_message(
        self,
        category: str,
        message: str,
        *,
        category_color: str | None = None,
        message_color: str | None = None,
    ) -> str:
        category_text = self._style(
            _format_category_label(category),
            category_color or self.theme.label,
        )
        message_text = _ensure_terminal_punctuation(message)
        if message_color is not None:
            message_text = self._style(message_text, message_color)
        return f"{category_text}{message_text}"

    def _redact(self, text: str) -> str:
        redacted = text
        for value in self._redacted_values:
            redacted = redacted.replace(value, "[redacted]")
        return redacted

    def _guidance_line(self, label: str, message: str) -> None:
        display_label = "cause" if label == "Likely cause" else label.lower()
        self._emit_status(display_label, self.theme.label, message)

    def _render_window_monitor_timeout(self, result: WindowMonitorResult) -> None:
        self.error("Monitor: timed out before app window was observed.")
        if self.mode == ConsoleMode.QUIET:
            return
        candidate = _first_titled_candidate(result)
        if result.expected_title and candidate is not None:
            self._guidance_line(
                "Likely cause",
                (f'Expected title "{result.expected_title}"; saw "{candidate.title}".'),
            )
        else:
            self._guidance_line("Likely cause", result.message)

        if result.candidates:
            self._guidance_line(
                "Next",
                "Match the profile title to the app page title, or run with --title.",
            )
        else:
            self._guidance_line(
                "Next",
                "Confirm the app-mode browser window opened and the title matches.",
            )
        if self.mode == ConsoleMode.NORMAL:
            return

        if result.expected_title:
            self.detail(f"Expected window title: {result.expected_title}")
        if result.candidates:
            self.detail("Observed window candidates:")
            for window in result.candidates[:5]:
                self.detail(_format_window_candidate(window))
        self._guidance_line(
            "Next",
            'For Streamlit, set st.set_page_config(page_title="...").',
        )


def format_elapsed(seconds: float) -> str:
    """Format elapsed seconds for concise console output."""

    return f"{max(0.0, seconds):.1f}s"


def _normalize_mode(mode: ConsoleMode | str) -> ConsoleMode:
    if isinstance(mode, ConsoleMode):
        return mode
    return ConsoleMode(str(mode).strip().lower())


def _is_verbose_hint(message: str) -> bool:
    normalized = message.lower()
    return "use verbose mode" in normalized or "verbose mode" in normalized


def _strip_sentence_punctuation(message: str) -> str:
    return message.strip().rstrip(".;:")


def _ensure_terminal_punctuation(message: str) -> str:
    visible = strip_ansi(message).rstrip()
    if not visible or visible.endswith((".", "!", "?")):
        return message
    return f"{message}."


def _ensure_ellipsis(message: str) -> str:
    stripped = _capitalize_sentence_start(_strip_sentence_punctuation(message))
    return f"{stripped}..."


def _first_titled_candidate(result: WindowMonitorResult) -> WindowInfo | None:
    for window in result.candidates:
        if window.title.strip():
            return window
    return result.candidates[0] if result.candidates else None


def _format_window_candidate(window: WindowInfo) -> str:
    title = window.title or "<untitled>"
    process_name = window.process_name or "unknown process"
    class_name = window.class_name or "unknown class"
    return (
        f'Candidate window: handle={window.handle} title="{title}" '
        f"process={process_name} class={class_name}"
    )


def _punctuate_phase_message(message: str) -> str:
    stripped = message.strip()
    visible = strip_ansi(stripped)
    if visible.endswith((".", "!", "?")):
        return _capitalize_sentence_start(stripped)
    normalized = visible.lower()
    if normalized.startswith(
        (
            "opening ",
            "requesting ",
            "starting ",
            "waiting ",
            "watching ",
            "closing ",
            "saving ",
        )
    ):
        return f"{_capitalize_sentence_start(_strip_sentence_punctuation(stripped))}..."
    return f"{_capitalize_sentence_start(_strip_sentence_punctuation(stripped))}."


def _capitalize_sentence_start(message: str) -> str:
    """Capitalize visible sentence starts without rewriting existing acronyms."""

    result: list[str] = []
    capitalize_next = True
    for index, char in enumerate(message):
        if char.isalpha():
            result.append(char.upper() if capitalize_next else char)
            capitalize_next = False
            continue
        result.append(char)
        next_char = message[index + 1] if index + 1 < len(message) else ""
        previous_char = message[index - 1] if index > 0 else ""
        if char in ".!?" and not (previous_char.isdigit() and next_char.isdigit()):
            capitalize_next = True
            continue
        if char.isspace():
            continue
        if index == 0:
            capitalize_next = False
    return "".join(result)
