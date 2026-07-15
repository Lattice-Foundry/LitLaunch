"""Structured runtime event sink primitives for LitLaunch integrations."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType

from litlaunch.console import ConsoleMode, ConsoleRenderer
from litlaunch.redaction import redact_sensitive_text

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
        "host_sizing",
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

_SENSITIVE_DETAIL_MARKERS = (
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "api-key",
    "key",
)


def create_runtime_event_file_sink(path: str | Path) -> RuntimeEventSink:
    """Create a tiny JSONL file sink for local runtime lifecycle events."""

    event_path = Path(path)

    def write_event(event: RuntimeEvent) -> None:
        resolved = event_path.expanduser()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": event.timestamp.isoformat(),
            "level": event.level,
            "category": event.category,
            "name": event.name,
            "message": redact_sensitive_text(event.message),
            "details": _safe_event_details(event.details),
        }
        with resolved.open("a", encoding="utf-8", newline="\n") as file:
            file.write(json.dumps(record, sort_keys=True) + "\n")

    return write_event


def compose_runtime_event_sinks(
    *sinks: RuntimeEventSink | None,
) -> RuntimeEventSink | None:
    """Return one sink that invokes each provided sink in order."""

    active_sinks = tuple(sink for sink in sinks if sink is not None)
    if not active_sinks:
        return None
    if len(active_sinks) == 1:
        return active_sinks[0]

    def write_event(event: RuntimeEvent) -> None:
        first_error: Exception | None = None
        for sink in active_sinks:
            try:
                sink(event)
            except Exception as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error

    return write_event


def _safe_event_details(details: Mapping[str, str]) -> dict[str, str]:
    safe: dict[str, str] = {}
    for key, value in details.items():
        key_text = str(key)
        if _sensitive_detail_key(key_text):
            safe[key_text] = "<redacted>"
        else:
            safe[key_text] = redact_sensitive_text(value)
    return safe


def _sensitive_detail_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(
        marker.replace("-", "_") in normalized for marker in _SENSITIVE_DETAIL_MARKERS
    )


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
            timestamp=datetime.now(timezone.utc),
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
