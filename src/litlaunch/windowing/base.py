"""Window monitoring contracts for optional app-mode lifecycle observation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from litlaunch.browsers import BrowserKind


class WindowMonitorStatus(str, Enum):
    """Window monitoring result and event status values."""

    UNSUPPORTED = "unsupported"
    WAITING_FOR_WINDOW = "waiting_for_window"
    WINDOW_OBSERVED = "window_observed"
    WINDOW_CLOSED = "window_closed"
    BACKEND_EXITED = "backend_exited"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


@dataclass(frozen=True)
class WindowInfo:
    """One observed desktop window candidate."""

    handle: str
    title: str = ""
    class_name: str = ""
    pid: int | None = None
    process_name: str | None = None

    def __post_init__(self) -> None:
        handle = str(self.handle).strip()
        if not handle:
            raise ValueError("window handle cannot be empty.")
        object.__setattr__(self, "handle", handle)
        object.__setattr__(self, "title", str(self.title).strip())
        object.__setattr__(self, "class_name", str(self.class_name).strip())
        if self.process_name is not None:
            object.__setattr__(self, "process_name", str(self.process_name).strip())


@dataclass(frozen=True)
class WindowTarget:
    """Expected browser app-mode window target."""

    title: str
    url: str | None = None
    browser_kind: BrowserKind | None = None
    app_mode: bool = True
    baseline_handles: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        title = str(self.title).strip()
        baseline_handles = tuple(
            str(handle).strip() for handle in self.baseline_handles
        )
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "baseline_handles", baseline_handles)
        object.__setattr__(self, "app_mode", bool(self.app_mode))
        if self.app_mode and not title:
            raise ValueError("window target title cannot be empty for app-mode.")


@dataclass(frozen=True)
class WindowMonitorConfig:
    """Polling configuration for optional window monitoring."""

    appear_timeout_seconds: float = 60.0
    poll_interval_seconds: float = 1.0
    stable_poll_count: int = 2
    require_app_mode: bool = True

    def __post_init__(self) -> None:
        if self.appear_timeout_seconds <= 0:
            raise ValueError("appear_timeout_seconds must be positive.")
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive.")
        if self.stable_poll_count < 1:
            raise ValueError("stable_poll_count must be at least 1.")
        object.__setattr__(self, "require_app_mode", bool(self.require_app_mode))


@dataclass(frozen=True)
class WindowMonitorEvent:
    """One timestamped window monitoring event."""

    status: WindowMonitorStatus
    message: str
    timestamp: float
    window: WindowInfo | None = None

    def __post_init__(self) -> None:
        message = str(self.message).strip()
        if not message:
            raise ValueError("window monitor event message cannot be empty.")
        object.__setattr__(self, "message", message)


@dataclass(frozen=True)
class WindowMonitorResult:
    """Result from waiting for an app-mode window lifecycle signal."""

    supported: bool
    observed: bool
    closed: bool
    status: WindowMonitorStatus
    message: str
    target: WindowInfo | None = None
    expected_title: str | None = None
    candidates: tuple[WindowInfo, ...] = field(default_factory=tuple)
    events: tuple[WindowMonitorEvent, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        message = str(self.message).strip()
        if not message:
            raise ValueError("window monitor result message cannot be empty.")
        object.__setattr__(self, "message", message)
        if self.expected_title is not None:
            expected_title = str(self.expected_title).strip()
            object.__setattr__(
                self,
                "expected_title",
                expected_title or None,
            )
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(self, "events", tuple(self.events))


class WindowMonitor(Protocol):
    """Observation-only window monitor boundary."""

    def capture(self, target: WindowTarget) -> tuple[WindowInfo, ...]:
        """Capture current matching or candidate windows."""

    def wait_for_close(
        self,
        target: WindowTarget,
        *,
        backend_is_running: Callable[[], bool],
        config: WindowMonitorConfig,
    ) -> WindowMonitorResult:
        """Wait until the target app-mode window closes."""
