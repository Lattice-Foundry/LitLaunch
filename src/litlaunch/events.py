"""Structured runtime event sink primitives for LitLaunch integrations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType

from litlaunch.console import ConsoleMode, ConsoleRenderer

RUNTIME_EVENT_LEVELS = frozenset({"info", "warning", "error"})
RUNTIME_EVENT_CATEGORIES = frozenset(
    {
        "launch",
        "backend",
        "health",
        "browser",
        "monitor",
        "shutdown",
        "hook",
        "port",
    }
)


@dataclass(frozen=True)
class RuntimeEvent:
    """One structured lifecycle event emitted by a LitLaunch runtime."""

    name: str
    category: str
    level: str
    message: str
    timestamp: datetime
    details: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        category = str(self.category).strip().lower()
        level = str(self.level).strip().lower()
        message = str(self.message).strip()
        if not name:
            raise ValueError("RuntimeEvent name cannot be empty.")
        if category not in RUNTIME_EVENT_CATEGORIES:
            raise ValueError(f"Unknown RuntimeEvent category: {self.category!r}.")
        if level not in RUNTIME_EVENT_LEVELS:
            raise ValueError(f"Unknown RuntimeEvent level: {self.level!r}.")
        if not message:
            raise ValueError("RuntimeEvent message cannot be empty.")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "level", level)
        object.__setattr__(self, "message", message)
        object.__setattr__(
            self,
            "details",
            MappingProxyType(
                {str(key): str(value) for key, value in self.details.items()}
            ),
        )


RuntimeEventSink = Callable[[RuntimeEvent], None]


class RuntimeEventEmitter:
    """Small guarded adapter around an optional runtime event sink."""

    def __init__(
        self,
        sink: RuntimeEventSink | None = None,
        *,
        console_renderer: ConsoleRenderer | None = None,
    ) -> None:
        self.sink = sink
        self.console_renderer = console_renderer
        self._sink_warning_rendered = False

    def emit(
        self,
        name: str,
        *,
        category: str,
        message: str,
        level: str = "info",
        details: Mapping[str, object] | None = None,
    ) -> None:
        """Emit one event to the optional sink without affecting runtime flow."""

        if self.sink is None:
            return
        event = RuntimeEvent(
            name=name,
            category=category,
            level=level,
            message=message,
            timestamp=datetime.now(UTC),
            details={str(key): str(value) for key, value in (details or {}).items()},
        )
        try:
            self.sink(event)
        except Exception:
            self._warn_sink_failed_once()

    def _warn_sink_failed_once(self) -> None:
        if self._sink_warning_rendered:
            return
        self._sink_warning_rendered = True
        if (
            self.console_renderer is not None
            and self.console_renderer.mode == ConsoleMode.VERBOSE
        ):
            self.console_renderer.warning(
                "Runtime: event sink failed; continuing runtime."
            )
