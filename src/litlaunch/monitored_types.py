"""Shared monitored-runtime result models."""

from __future__ import annotations

from dataclasses import dataclass

from litlaunch.session import RuntimeSession
from litlaunch.windowing import WindowMonitorResult


@dataclass(frozen=True)
class MonitoredRunResult:
    """Structured result for a monitored runtime run."""

    exit_code: int
    session: RuntimeSession | None
    monitor_result: WindowMonitorResult | None
    message: str
    launched: bool
    stopped_cleanly: bool
