"""Lifecycle state and result types for LitLaunch."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LaunchState(str, Enum):
    """Coarse lifecycle states for launcher-owned backend runs."""

    CREATED = "created"
    CONFIGURED = "configured"
    PORT_READY = "port_ready"
    COMMAND_BUILT = "command_built"
    PROCESS_STARTING = "process_starting"
    PROCESS_RUNNING = "process_running"
    HEALTH_CHECKING = "health_checking"
    HEALTHY = "healthy"
    FAILED = "failed"
    TERMINATING = "terminating"
    TERMINATED = "terminated"


@dataclass(frozen=True)
class LaunchEvent:
    """One timestamped lifecycle state transition or diagnostic event."""

    state: LaunchState
    message: str
    timestamp: float


@dataclass(frozen=True)
class LaunchResult:
    """Result from a launcher lifecycle operation."""

    ok: bool
    state: LaunchState
    command: tuple[str, ...] | None
    pid: int | None
    url: str | None
    message: str
    events: tuple[LaunchEvent, ...]
