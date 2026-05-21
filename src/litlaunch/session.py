"""Live runtime session ownership for LitLaunch."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from urllib.parse import urlparse

from litlaunch._protocols import ClockProvider
from litlaunch.console import ConsolePhase, ConsoleRenderer
from litlaunch.lifecycle import LaunchEvent, LaunchResult, LaunchState
from litlaunch.process import ManagedProcess, ProcessManager
from litlaunch.runtime_console import (
    render_failure_guidance,
    render_phase_start,
    render_phase_success,
    render_phase_warning,
    render_window_monitor_result,
)
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
        port_release_checker: Callable[[str, int], bool] | None = None,
        clock: ClockProvider = time,
    ) -> None:
        self.result = result
        self.process = process
        self.process_manager = process_manager
        self._shutdown_client = shutdown_client
        self.console_renderer = console_renderer
        self._port_release_checker = port_release_checker
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

        stop_start_time = self.clock.monotonic()
        render_phase_start(self.console_renderer, ConsolePhase.SHUTDOWN, "requested")

        if self._shutdown_client is not None and self.is_running():
            self.add_event(
                LaunchState.TERMINATING,
                "Requesting graceful shutdown.",
                render=False,
            )
            render_phase_start(
                self.console_renderer,
                ConsolePhase.SHUTDOWN,
                "requesting app cleanup",
            )
            request_result = self._shutdown_client.request_shutdown()
            if request_result.ok:
                self.add_event(
                    LaunchState.TERMINATING,
                    "Graceful shutdown request accepted.",
                    render=False,
                )
                render_phase_success(
                    self.console_renderer,
                    ConsolePhase.SHUTDOWN,
                    "app cleanup request accepted",
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
                        render=False,
                    )
                    render_phase_warning(
                        self.console_renderer,
                        ConsolePhase.STOPPING_BACKEND,
                        "graceful stop timed out; using termination fallback",
                    )
                    render_failure_guidance(
                        self.console_renderer,
                        "Graceful shutdown timed out.",
                        likely_cause=(
                            "The app accepted the shutdown request but did not exit "
                            "before the graceful timeout."
                        ),
                        next_steps=(
                            "Review shutdown hooks if the app needs cleanup time.",
                            "Use verbose mode for more runtime details.",
                        ),
                    )
                else:
                    self._stopped = True
                    self._state = LaunchState.TERMINATED
                    self._render_backend_exit(
                        returncode,
                        elapsed_seconds=self.clock.monotonic() - stop_start_time,
                        expected_shutdown=True,
                    )
                    self._render_port_release_if_verified()
                    return
            else:
                self.add_event(
                    LaunchState.TERMINATING,
                    "Graceful shutdown request failed; using termination fallback.",
                    render=False,
                )
                render_phase_warning(
                    self.console_renderer,
                    ConsolePhase.STOPPING_BACKEND,
                    "graceful request failed; using termination fallback",
                )
                render_failure_guidance(
                    self.console_renderer,
                    "Graceful shutdown request failed.",
                    likely_cause=(
                        "The app-side shutdown endpoint did not accept the request."
                    ),
                    next_steps=(
                        (
                            "Confirm the app calls "
                            "LauncherRuntime.enable_shutdown_endpoint()."
                        ),
                        "Use verbose mode for more runtime details.",
                    ),
                )

        if not self.is_running():
            self._stopped = True
            self._state = LaunchState.TERMINATED
            self.add_event(
                LaunchState.TERMINATED,
                "Owned backend process stopped.",
                render=False,
            )
            render_phase_success(
                self.console_renderer,
                ConsolePhase.SHUTDOWN,
                "complete; backend already stopped",
                elapsed_seconds=self.clock.monotonic() - stop_start_time,
            )
            self._render_port_release_if_verified()
            return

        self.add_event(
            LaunchState.TERMINATING,
            "Stopping owned backend process with termination fallback.",
            render=False,
        )
        render_phase_warning(
            self.console_renderer,
            ConsolePhase.STOPPING_BACKEND,
            "terminating owned backend process",
        )
        render_failure_guidance(
            self.console_renderer,
            "Using backend termination fallback.",
            likely_cause="The backend did not stop through graceful shutdown.",
            next_steps=("LitLaunch will stop only the backend process it started.",),
            suggest_inspect=False,
        )
        self.process_manager.stop(
            self.process,
            terminate_timeout_seconds=timeout_seconds,
        )
        self._stopped = True
        self._state = LaunchState.TERMINATED
        self.add_event(
            LaunchState.TERMINATED,
            "Owned backend process stopped.",
            render=False,
        )
        render_phase_success(
            self.console_renderer,
            ConsolePhase.SHUTDOWN,
            "complete; backend stopped through termination fallback",
            elapsed_seconds=self.clock.monotonic() - stop_start_time,
        )
        self._render_port_release_if_verified()

    def wait(self, timeout_seconds: float | None = None) -> int | None:
        """Wait for the owned backend process to exit.

        Timed waits are non-throwing. If the timeout expires, the backend is
        left running, the session state is unchanged, and ``None`` is returned.
        """

        if self.process is None:
            return None

        try:
            returncode = self.process_manager.wait(
                self.process,
                timeout_seconds=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            self.add_event(
                self._state,
                "Timed wait expired; owned backend process is still running.",
            )
            return None
        self._stopped = True
        self._state = LaunchState.TERMINATED
        self._render_backend_exit(returncode, expected_shutdown=False)
        self._render_port_release_if_verified()
        return returncode

    def monitor_window(
        self,
        monitor: WindowMonitor,
        target: WindowTarget,
        config: WindowMonitorConfig | None = None,
        *,
        graceful_timeout_seconds: float = 3.0,
    ) -> WindowMonitorResult:
        """Monitor an app-mode window and stop the backend only after close."""

        resolved_config = config or WindowMonitorConfig()
        self.add_event(
            LaunchState.WINDOW_MONITORING,
            "Window monitoring started.",
            render=False,
        )
        render_phase_start(
            self.console_renderer,
            ConsolePhase.MONITOR,
            "watching app window",
        )
        result = monitor.wait_for_close(
            target,
            backend_is_running=self.is_running,
            config=resolved_config,
        )
        if result.closed:
            self.add_event(
                LaunchState.WINDOW_CLOSED,
                result.message or "App-mode window closed.",
                render=False,
            )
            render_window_monitor_result(self.console_renderer, result)
            self.stop(graceful_timeout_seconds=graceful_timeout_seconds)
        elif result.status == WindowMonitorStatus.BACKEND_EXITED:
            self._stopped = True
            self._state = LaunchState.TERMINATED
            self.add_event(LaunchState.TERMINATED, result.message, render=False)
            render_window_monitor_result(self.console_renderer, result)
        else:
            self.add_event(
                LaunchState.WINDOW_MONITORING,
                result.message,
                render=False,
            )
            render_window_monitor_result(self.console_renderer, result)
        return result

    def add_event(
        self,
        state: LaunchState,
        message: str,
        *,
        render: bool = True,
    ) -> None:
        """Record a lifecycle event for this live session."""

        event = LaunchEvent(
            state=state,
            message=message,
            timestamp=self.clock.monotonic(),
        )
        self._events.append(event)
        if render and self.console_renderer is not None:
            self.console_renderer.render_launch_event(event)

    def __enter__(self) -> RuntimeSession:
        """Return this session for context manager ownership."""

        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        """Stop the owned backend process on context exit."""

        self.stop()

    def _render_backend_exit(
        self,
        returncode: int | None,
        *,
        elapsed_seconds: float | None = None,
        expected_shutdown: bool,
    ) -> None:
        code = 0 if returncode is None else int(returncode)
        if code == 0:
            message = (
                "Backend stopped cleanly"
                if expected_shutdown
                else "Backend exited cleanly"
            )
            self.add_event(LaunchState.TERMINATED, message, render=False)
            render_phase_success(
                self.console_renderer,
                ConsolePhase.SHUTDOWN if expected_shutdown else ConsolePhase.BACKEND,
                (
                    "complete; backend stopped cleanly"
                    if expected_shutdown
                    else "backend exited cleanly"
                ),
                elapsed_seconds=elapsed_seconds,
            )
            return

        self.add_event(
            LaunchState.TERMINATED,
            f"Owned backend process exited with code {code}.",
            render=False,
        )
        render_failure_guidance(
            self.console_renderer,
            f"Backend exited with code {code}.",
            likely_cause="The backend stopped but reported a non-zero exit code.",
            next_steps=(
                "Run the app directly with streamlit run to inspect the traceback.",
            ),
        )

    def _render_port_release_if_verified(self) -> None:
        if self.console_renderer is None or self._port_release_checker is None:
            return
        host_port = _parse_url_host_port(self.result.url)
        if host_port is None:
            return
        host, port = host_port
        try:
            released = self._port_release_checker(host, port)
        except Exception:
            return
        if released:
            self.console_renderer.success(f"Port {port} released")


def _parse_url_host_port(url: str | None) -> tuple[str, int] | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.hostname is None or parsed.port is None:
        return None
    return parsed.hostname, parsed.port
