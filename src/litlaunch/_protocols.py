"""Internal structural protocols for injectable runtime dependencies."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ClockProvider(Protocol):
    """Clock surface used for deterministic lifecycle event timestamps."""

    def monotonic(self) -> float:
        """Return a monotonic timestamp."""

    def time(self) -> float:
        """Return a wall-clock timestamp."""


@runtime_checkable
class ManagedPopen(Protocol):
    """Subprocess surface required by LitLaunch process ownership."""

    pid: int

    def poll(self) -> int | None:
        """Return the process return code, or None while running."""

    def wait(self, timeout: float | None = None) -> int | None:
        """Wait for process exit and return the return code."""

    def terminate(self) -> None:
        """Request graceful process termination."""

    def kill(self) -> None:
        """Force process termination."""
