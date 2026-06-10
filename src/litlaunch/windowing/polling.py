"""Fake-friendly polling monitor foundation for app-mode windows."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from litlaunch._protocols import ClockProvider
from litlaunch.windowing.base import (
    WindowInfo,
    WindowMonitorConfig,
    WindowMonitorEvent,
    WindowMonitorResult,
    WindowMonitorStatus,
    WindowTarget,
)
from litlaunch.windowing.title_match import (
    matches_window_title,
    window_matches_browser_kind,
)


class PollingWindowMonitor:
    """Generic observation-only polling monitor using an injected window capture."""

    def __init__(
        self,
        capture_provider: Callable[[WindowTarget], Sequence[WindowInfo]],
        *,
        clock: ClockProvider = time,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.capture_provider = capture_provider
        self.clock = clock
        self.sleeper = sleeper

    def capture(self, target: WindowTarget) -> tuple[WindowInfo, ...]:
        """Capture current windows through the injected provider."""

        return tuple(self.capture_provider(target))

    def wait_for_close(
        self,
        target: WindowTarget,
        *,
        backend_is_running: Callable[[], bool],
        config: WindowMonitorConfig,
    ) -> WindowMonitorResult:
        """Wait for a stable app-mode window to appear and then close."""

        if config.require_app_mode and not target.app_mode:
            return WindowMonitorResult(
                supported=False,
                observed=False,
                closed=False,
                status=WindowMonitorStatus.UNSUPPORTED,
                message="Window monitoring is supported for app-mode targets only.",
            )

        events: list[WindowMonitorEvent] = []
        self._add_event(
            events,
            WindowMonitorStatus.WAITING_FOR_WINDOW,
            "Waiting for app-mode window.",
        )
        target_window = self._wait_for_stable_target(
            target,
            backend_is_running=backend_is_running,
            config=config,
            events=events,
        )
        if isinstance(target_window, WindowMonitorResult):
            return target_window

        self._add_event(
            events,
            WindowMonitorStatus.WINDOW_OBSERVED,
            "App-mode window observed.",
            target_window,
        )
        return self._wait_for_target_close(
            target,
            target_window,
            backend_is_running=backend_is_running,
            config=config,
            events=events,
        )

    def _wait_for_stable_target(
        self,
        target: WindowTarget,
        *,
        backend_is_running: Callable[[], bool],
        config: WindowMonitorConfig,
        events: list[WindowMonitorEvent],
    ) -> WindowInfo | WindowMonitorResult:
        deadline = self.clock.monotonic() + config.appear_timeout_seconds
        candidate: WindowInfo | None = None
        diagnostic_windows: tuple[WindowInfo, ...] = ()
        stable_count = 0

        while self.clock.monotonic() <= deadline:
            if not backend_is_running():
                return self._result(
                    WindowMonitorStatus.BACKEND_EXITED,
                    "Backend exited before app-mode window was observed.",
                    events,
                    supported=True,
                    observed=False,
                    closed=False,
                )

            try:
                diagnostic_windows = self._diagnostic_windows(target)
                candidates = self._candidate_windows(target, diagnostic_windows)
            except Exception as exc:
                return self._result(
                    WindowMonitorStatus.ERROR,
                    f"Window capture failed: {exc}",
                    events,
                    supported=True,
                    observed=False,
                    closed=False,
                )

            selected = candidates[-1] if candidates else None
            if selected is None:
                if candidate is not None:
                    self._add_event(
                        events,
                        WindowMonitorStatus.WINDOW_CLOSED,
                        "App-mode window closed before stable observation.",
                        candidate,
                    )
                    return self._result(
                        WindowMonitorStatus.WINDOW_CLOSED,
                        "App-mode window closed before stable observation.",
                        events,
                        supported=True,
                        observed=True,
                        closed=True,
                        target=candidate,
                    )
                candidate = None
                stable_count = 0
            elif candidate is not None and selected.handle == candidate.handle:
                stable_count += 1
            else:
                candidate = selected
                stable_count = 1

            if candidate is not None and stable_count >= config.stable_poll_count:
                return candidate

            self.sleeper(config.poll_interval_seconds)

        return self._result(
            WindowMonitorStatus.TIMEOUT,
            "Timed out waiting for app-mode window to appear.",
            events,
            supported=True,
            observed=False,
            closed=False,
            expected_title=target.title,
            candidates=diagnostic_windows,
        )

    def _wait_for_target_close(
        self,
        target: WindowTarget,
        target_window: WindowInfo,
        *,
        backend_is_running: Callable[[], bool],
        config: WindowMonitorConfig,
        events: list[WindowMonitorEvent],
    ) -> WindowMonitorResult:
        while True:
            if not backend_is_running():
                return self._result(
                    WindowMonitorStatus.BACKEND_EXITED,
                    "Backend exited while app-mode window was being monitored.",
                    events,
                    supported=True,
                    observed=True,
                    closed=False,
                    target=target_window,
                )

            try:
                active_handles = {window.handle for window in self.capture(target)}
            except Exception as exc:
                return self._result(
                    WindowMonitorStatus.ERROR,
                    f"Window capture failed: {exc}",
                    events,
                    supported=True,
                    observed=True,
                    closed=False,
                    target=target_window,
                )

            if target_window.handle not in active_handles:
                self._add_event(
                    events,
                    WindowMonitorStatus.WINDOW_CLOSED,
                    "App-mode window closed.",
                    target_window,
                )
                return self._result(
                    WindowMonitorStatus.WINDOW_CLOSED,
                    "App-mode window closed.",
                    events,
                    supported=True,
                    observed=True,
                    closed=True,
                    target=target_window,
                )

            self.sleeper(config.poll_interval_seconds)

    def _diagnostic_windows(self, target: WindowTarget) -> tuple[WindowInfo, ...]:
        baseline = set(target.baseline_handles)
        return tuple(
            window
            for window in self.capture(target)
            if window.handle not in baseline
            and window_matches_browser_kind(window, target.browser_kind)
        )

    def _candidate_windows(
        self,
        target: WindowTarget,
        windows: tuple[WindowInfo, ...] | None = None,
    ) -> tuple[WindowInfo, ...]:
        observed = self._diagnostic_windows(target) if windows is None else windows
        return tuple(window for window in observed if _matches_target(window, target))

    def _add_event(
        self,
        events: list[WindowMonitorEvent],
        status: WindowMonitorStatus,
        message: str,
        window: WindowInfo | None = None,
    ) -> None:
        events.append(
            WindowMonitorEvent(
                status=status,
                message=message,
                timestamp=self.clock.monotonic(),
                window=window,
            )
        )

    def _result(
        self,
        status: WindowMonitorStatus,
        message: str,
        events: list[WindowMonitorEvent],
        *,
        supported: bool,
        observed: bool,
        closed: bool,
        target: WindowInfo | None = None,
        expected_title: str | None = None,
        candidates: tuple[WindowInfo, ...] = (),
    ) -> WindowMonitorResult:
        return WindowMonitorResult(
            supported=supported,
            observed=observed,
            closed=closed,
            status=status,
            message=message,
            target=target,
            expected_title=expected_title,
            candidates=candidates,
            events=tuple(events),
        )


def _matches_target(window: WindowInfo, target: WindowTarget) -> bool:
    if not target.app_mode:
        return False
    if not matches_window_title(window.title, target.title, target.url):
        return False
    return window_matches_browser_kind(window, target.browser_kind)
