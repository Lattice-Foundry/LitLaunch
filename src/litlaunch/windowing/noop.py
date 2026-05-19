"""No-op window monitor for unsupported platforms or disabled monitoring."""

from __future__ import annotations

from collections.abc import Callable

from litlaunch.windowing.base import (
    WindowInfo,
    WindowMonitorConfig,
    WindowMonitorResult,
    WindowMonitorStatus,
    WindowTarget,
)


class NoopWindowMonitor:
    """Observation-only monitor that reports window monitoring as unsupported."""

    def capture(self, target: WindowTarget) -> tuple[WindowInfo, ...]:
        """Return no windows."""

        return ()

    def wait_for_close(
        self,
        target: WindowTarget,
        *,
        backend_is_running: Callable[[], bool],
        config: WindowMonitorConfig,
    ) -> WindowMonitorResult:
        """Return a clean unsupported result."""

        return WindowMonitorResult(
            supported=False,
            observed=False,
            closed=False,
            status=WindowMonitorStatus.UNSUPPORTED,
            message=(
                "Window monitoring is not supported on this platform or monitor "
                "implementation."
            ),
        )
