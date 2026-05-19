"""Live runtime session ownership for LitLaunch."""

from __future__ import annotations

import subprocess
import time

from litlaunch._protocols import ClockProvider
from litlaunch.console import ConsoleRenderer
from litlaunch.lifecycle import LaunchEvent, LaunchResult, LaunchState
from litlaunch.process import ManagedProcess, ProcessManager
from litlaunch.shutdown import ShutdownClient
from litlaunch.windowing import (
    WindowMonitor,
    WindowMonitorConfig,
    WindowMonitorResult,
    WindowMonitorStatus,
    WindowTarget,
)


class RuntimeSession:
    """Own a live Streamlit backend process started by LitLaunch.

    Browser processes are intentionally not owned, monitored, stopped, or killed
    by this session.
    """

    def __init__(
        self,
        *,
        result: LaunchResult,
        process: ManagedProcess | None,
        process_manager: ProcessManager,
        shutdown_client: ShutdownClient | None = None,
        console_renderer: ConsoleRenderer | None = None,
        clock: ClockProvider = time,
    ) -> None:
        self.result = result
        self.process = process
        self.process_manager = process_manager
        self._shutdown_client = shutdown_client
        self.console_renderer = console_renderer
        self.clock = clock
        self._events = list(result.events)
        self._state = result.state
        self._stopped = process is None
        if self.console_renderer is not None and self._shutdown_client is not None:
            self.console_renderer.add_redaction(
                getattr(self._shutdown_client, "token", None)
            )

    @property
    def ok(self) -> bool:
        """Return whether the launch operation succeeded."""

        return self.result.ok

    @property
    def state(self) -> LaunchState:
        """Return the current session lifecycle state."""

        return self._state

    @property
    def pid(self) -> int | None:
        """Return the owned backend PID, when one exists."""

        return self.result.pid

    @property
    def url(self) -> str | None:
        """Return the launched Streamlit app URL."""

        return self.result.url

    @property
    def command(self) -> tuple[str, ...] | None:
        """Return the Streamlit backend command."""

        return self.result.command

    @property
    def browser(self):
        """Return the browser capability used during launch, if any."""

        return self.result.browser

    @property
    def browser_command(self) -> tuple[str, ...] | None:
        """Return the browser command used during launch, if any."""

        return self.result.browser_command

    @property
    def browser_launched(self) -> bool:
        """Return whether browser launch succeeded."""

        return self.result.browser_launched

    @property
    def events(self) -> tuple[LaunchEvent, ...]:
        """Return immutable lifecycle events observed by the session."""

        return tuple(self._events)

    def is_running(self) -> bool:
        """Return whether the owned backend process is still running."""

        return self.process is not None and self.process_manager.is_running(
            self.process
        )

    def stop(
        self,
        timeout_seconds: float = 5.0,
        *,
        graceful_timeout_seconds: float = 3.0,
    ) -> None:
        """Gracefully stop the app, then terminate the owned backend if needed."""

        if self.process is None or self._stopped:
            return

        if self._shutdown_client is not None and self.is_running():
            self.add_event(LaunchState.TERMINATING, "Requesting graceful shutdown.")
            request_result = self._shutdown_client.request_shutdown()
            if request_result.ok:
                self.add_event(
                    LaunchState.TERMINATING,
                    "Graceful shutdown request accepted.",
                )
                try:
                    returncode = self.process_manager.wait(
                        self.process,
                        timeout_seconds=graceful_timeout_seconds,
                    )
                except subprocess.TimeoutExpired:
                    self.add_event(
                        LaunchState.TERMINATING,
                        "Graceful shutdown timed out; using termination fallback.",
                    )
                else:
                    self._stopped = True
                    self._state = LaunchState.TERMINATED
                    self.add_event(
                        LaunchState.TERMINATED,
                        f"Owned backend process exited with code {returncode}.",
                    )
                    return
            else:
                self.add_event(
                    LaunchState.TERMINATING,
                    "Graceful shutdown request failed; using termination fallback.",
                )

        if not self.is_running():
            self._stopped = True
            self._state = LaunchState.TERMINATED
            self.add_event(LaunchState.TERMINATED, "Owned backend process stopped.")
            return

        self.add_event(
            LaunchState.TERMINATING,
            "Stopping owned backend process with termination fallback.",
        )
        self.process_manager.stop(
            self.process,
            terminate_timeout_seconds=timeout_seconds,
        )
        self._stopped = True
        self._state = LaunchState.TERMINATED
        self.add_event(LaunchState.TERMINATED, "Owned backend process stopped.")

    def wait(self, timeout_seconds: float | None = None) -> int | None:
        """Wait for the owned backend process to exit."""

        if self.process is None:
            return None

        returncode = self.process_manager.wait(
            self.process,
            timeout_seconds=timeout_seconds,
        )
        self._stopped = True
        self._state = LaunchState.TERMINATED
        self.add_event(
            LaunchState.TERMINATED,
            f"Owned backend process exited with code {returncode}.",
        )
        return returncode

    def monitor_window(
        self,
        monitor: WindowMonitor,
        target: WindowTarget,
        config: WindowMonitorConfig | None = None,
    ) -> WindowMonitorResult:
        """Monitor an app-mode window and stop the backend only after close."""

        resolved_config = config or WindowMonitorConfig()
        self.add_event(LaunchState.WINDOW_MONITORING, "Window monitoring started.")
        result = monitor.wait_for_close(
            target,
            backend_is_running=self.is_running,
            config=resolved_config,
        )
        if result.closed:
            self.add_event(
                LaunchState.WINDOW_CLOSED,
                result.message or "App-mode window closed.",
            )
            self.stop()
        elif result.status == WindowMonitorStatus.BACKEND_EXITED:
            self._stopped = True
            self._state = LaunchState.TERMINATED
            self.add_event(LaunchState.TERMINATED, result.message)
        else:
            self.add_event(LaunchState.WINDOW_MONITORING, result.message)
        return result

    def add_event(self, state: LaunchState, message: str) -> None:
        """Record a lifecycle event for this live session."""

        event = LaunchEvent(
            state=state,
            message=message,
            timestamp=self.clock.monotonic(),
        )
        self._events.append(event)
        if self.console_renderer is not None:
            self.console_renderer.render_launch_event(event)

    def __enter__(self) -> RuntimeSession:
        """Return this session for context manager ownership."""

        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        """Stop the owned backend process on context exit."""

        self.stop()
