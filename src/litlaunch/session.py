"""Live runtime session ownership for LitLaunch."""

from __future__ import annotations

import time

from litlaunch.lifecycle import LaunchEvent, LaunchResult, LaunchState
from litlaunch.process import ManagedProcess, ProcessManager


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
        clock: object = time,
    ) -> None:
        self.result = result
        self.process = process
        self.process_manager = process_manager
        self.clock = clock
        self._events = list(result.events)
        self._state = result.state
        self._stopped = process is None

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

    def stop(self, timeout_seconds: float = 5.0) -> None:
        """Stop the owned backend process exactly once."""

        if self.process is None or self._stopped:
            return

        self.add_event(LaunchState.TERMINATING, "Stopping owned backend process.")
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

    def add_event(self, state: LaunchState, message: str) -> None:
        """Record a lifecycle event for this live session."""

        self._events.append(
            LaunchEvent(
                state=state,
                message=message,
                timestamp=self.clock.monotonic(),
            )
        )

    def __enter__(self) -> RuntimeSession:
        """Return this session for context manager ownership."""

        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        """Stop the owned backend process on context exit."""

        self.stop()
