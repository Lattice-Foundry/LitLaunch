"""Live runtime session ownership for LitLaunch."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable, Sequence
from contextlib import suppress
from types import TracebackType
from typing import Protocol

from litlaunch._browser_authority import BrowserLaunchAuthority
from litlaunch._protocols import ClockProvider
from litlaunch.browsers import BrowserCapability
from litlaunch.console import ConsoleMode, ConsolePhase, ConsoleRenderer
from litlaunch.events import RuntimeEventEmitter
from litlaunch.health import parse_url_host_port
from litlaunch.lifecycle import LaunchEvent, LaunchResult, LaunchState
from litlaunch.process import ManagedProcess, ProcessManager
from litlaunch.runtime_console import (
    render_failure_guidance,
    render_phase_start,
    render_phase_success,
    render_phase_warning,
    render_window_monitor_result,
)
from litlaunch.shutdown import ShutdownClient, ShutdownHookResult
from litlaunch.windowing import (
    WindowMonitor,
    WindowMonitorConfig,
    WindowMonitorResult,
    WindowMonitorStatus,
    WindowTarget,
)


class _PrivateHostSizingRuntimeOwner(Protocol):
    def close(self) -> None:
        """Close private sizing work before backend shutdown."""

    def snapshot(self) -> object:
        """Return credential-free internal lifecycle evidence."""


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
        event_emitter: RuntimeEventEmitter | None = None,
        port_release_checker: Callable[[str, int], bool] | None = None,
        cleanup_callbacks: Sequence[Callable[[], object]] = (),
        browser_authority: BrowserLaunchAuthority | None = None,
        clock: ClockProvider = time,
        _private_host_sizing_runtime: _PrivateHostSizingRuntimeOwner | None = None,
    ) -> None:
        self.result = result
        self.process = process
        self.process_manager = process_manager
        self._shutdown_client = shutdown_client
        self.console_renderer = console_renderer
        self.event_emitter = event_emitter or RuntimeEventEmitter()
        self._port_release_checker = port_release_checker
        self._cleanup_callbacks = tuple(cleanup_callbacks)
        self._cleanup_done = False
        self._browser_authority = browser_authority
        self._private_host_sizing_runtime = _private_host_sizing_runtime
        self._private_host_sizing_snapshot_value: object | None = None
        self._shutdown_started = False
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
    def browser(self) -> BrowserCapability | None:
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

    def _browser_authority_snapshot(self) -> BrowserLaunchAuthority | None:
        """Return launch identity metadata without implying process ownership."""

        return self._browser_authority

    def _host_sizing_snapshot(self) -> object | None:
        """Return credential-free private activation evidence for internal tests."""

        runtime = self._private_host_sizing_runtime
        if runtime is None:
            return self._private_host_sizing_snapshot_value
        try:
            return runtime.snapshot()
        except Exception:
            return self._private_host_sizing_snapshot_value

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

        self._begin_shutdown()
        if self.process is None or self._stopped:
            self._run_cleanup_callbacks()
            return

        stop_start_time = self.clock.monotonic()
        render_phase_start(
            self.console_renderer,
            ConsolePhase.SHUTDOWN,
            "requested",
            verbose_only=True,
        )
        self.event_emitter.emit(
            "shutdown_requested",
            category="shutdown",
            message="Runtime shutdown requested.",
        )

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
                verbose_only=True,
            )
            request_result = self._shutdown_client.request_shutdown()
            if request_result.ok:
                self.add_event(
                    LaunchState.TERMINATING,
                    "Graceful shutdown request accepted.",
                    render=False,
                )
                self._render_shutdown_hook_results(request_result.hook_results)
                render_phase_success(
                    self.console_renderer,
                    ConsolePhase.SHUTDOWN,
                    "app cleanup request accepted",
                    verbose_only=True,
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
                    if self._is_verbose_console():
                        render_phase_warning(
                            self.console_renderer,
                            ConsolePhase.BACKEND,
                            "graceful shutdown timed out; using termination fallback",
                        )
                    render_failure_guidance(
                        self.console_renderer,
                        "Shutdown: graceful request timed out.",
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
                    self._run_cleanup_callbacks()
                    return
            else:
                self.add_event(
                    LaunchState.TERMINATING,
                    "Graceful shutdown request failed; using termination fallback.",
                    render=False,
                )
                self._render_shutdown_hook_results(request_result.hook_results)
                if (
                    request_result.status_code is None
                    and not request_result.hook_results
                ):
                    self._render_cleanup_endpoint_unavailable(request_result.message)
                else:
                    if self._is_verbose_console():
                        render_phase_warning(
                            self.console_renderer,
                            ConsolePhase.BACKEND,
                            "graceful shutdown failed; using termination fallback",
                        )
                    render_failure_guidance(
                        self.console_renderer,
                        "Shutdown: graceful request failed.",
                        likely_cause="The app did not accept the cleanup request.",
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
            self.event_emitter.emit(
                "backend_stopped",
                category="backend",
                message="Backend process was already stopped.",
            )
            render_phase_success(
                self.console_renderer,
                ConsolePhase.SHUTDOWN,
                "complete; backend already stopped",
                elapsed_seconds=self.clock.monotonic() - stop_start_time,
            )
            self._render_port_release_if_verified()
            self._run_cleanup_callbacks()
            return

        self.add_event(
            LaunchState.TERMINATING,
            "Stopping owned backend process with termination fallback.",
            render=False,
        )
        if self._is_verbose_console():
            render_phase_warning(
                self.console_renderer,
                ConsolePhase.BACKEND,
                "terminating owned process",
            )
        render_failure_guidance(
            self.console_renderer,
            "Shutdown: using backend termination fallback.",
            likely_cause="The backend did not stop through graceful shutdown.",
            next_steps=("LitLaunch will stop only the backend process it started.",),
            suggest_inspect=False,
            level="warning",
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
        self.event_emitter.emit(
            "backend_stopped",
            category="backend",
            message="Backend process stopped through termination fallback.",
        )
        render_phase_success(
            self.console_renderer,
            ConsolePhase.SHUTDOWN,
            "complete; backend stopped through termination fallback",
            elapsed_seconds=self.clock.monotonic() - stop_start_time,
        )
        self._render_port_release_if_verified()
        self._run_cleanup_callbacks()

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
        self._run_cleanup_callbacks()
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
        self.event_emitter.emit(
            "monitor_started",
            category="monitor",
            message="App-window monitoring started.",
            details={"target": target.title, "mode": "webapp"},
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
            self._run_cleanup_callbacks()
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

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
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
                else "Backend: exited cleanly"
            )
            self.add_event(LaunchState.TERMINATED, message, render=False)
            self.event_emitter.emit(
                "backend_stopped",
                category="backend",
                message="Backend process stopped cleanly.",
                details={"returncode": code},
            )
            render_phase_success(
                self.console_renderer,
                ConsolePhase.SHUTDOWN if expected_shutdown else ConsolePhase.BACKEND,
                ("Backend stopped cleanly" if expected_shutdown else "exited cleanly"),
                elapsed_seconds=elapsed_seconds,
            )
            return

        self.add_event(
            LaunchState.TERMINATED,
            f"Owned backend process exited with code {code}.",
            render=False,
        )
        self.event_emitter.emit(
            "backend_stopped",
            category="backend",
            level="error",
            message=f"Backend process exited with code {code}.",
            details={"returncode": code},
        )
        render_failure_guidance(
            self.console_renderer,
            f"Backend: exited with code {code}.",
            likely_cause="The backend stopped with an error status.",
            next_steps=(
                "Run the app directly with streamlit run to inspect the traceback.",
            ),
        )

    def _render_port_release_if_verified(self) -> None:
        if self._port_release_checker is None:
            return
        host_port = parse_url_host_port(self.result.url)
        if host_port is None:
            return
        host, port = host_port
        try:
            released = self._port_release_checker(host, port)
        except Exception:
            return
        if released:
            if self.console_renderer is not None:
                self.console_renderer.success(f"Backend: port {port} released")
            self.event_emitter.emit(
                "port_released",
                category="port",
                message=f"Backend port {port} released.",
                details={"host": host, "port": port},
            )

    def _render_shutdown_hook_results(
        self,
        hook_results: tuple[ShutdownHookResult, ...],
    ) -> None:
        for hook_result in hook_results:
            self.event_emitter.emit(
                "hook_succeeded" if hook_result.ok else "hook_failed",
                category="hook",
                level="info" if hook_result.ok else "error",
                message=hook_result.message,
                details={"label": hook_result.label},
            )
            if self.console_renderer is not None:
                self.console_renderer.render_shutdown_hook_result(hook_result)

    def _render_cleanup_endpoint_unavailable(self, detail: str) -> None:
        renderer = self.console_renderer
        render_phase_warning(
            renderer,
            ConsolePhase.SHUTDOWN,
            "app cleanup endpoint unavailable; stopping owned backend",
        )
        if renderer is None or renderer.mode == ConsoleMode.QUIET:
            return
        renderer.guidance_line(
            "Likely cause",
            "The app did not opt into LitLaunch app-side cleanup hooks.",
        )
        renderer.guidance_line(
            "Next",
            "No app setup is required unless the app needs custom cleanup.",
        )
        if renderer.mode == ConsoleMode.VERBOSE and detail:
            renderer.detail(f"Shutdown request detail: {detail}")

    def _is_verbose_console(self) -> bool:
        return (
            self.console_renderer is not None
            and self.console_renderer.mode == ConsoleMode.VERBOSE
        )

    def _run_cleanup_callbacks(self) -> None:
        self._begin_shutdown()
        if self._cleanup_done:
            return
        self._cleanup_done = True
        self._browser_authority = None
        for callback in self._cleanup_callbacks:
            try:
                callback()
            except Exception:
                continue

    def _begin_shutdown(self) -> None:
        if self._shutdown_started:
            return
        self._shutdown_started = True
        self._browser_authority = None
        runtime = self._private_host_sizing_runtime
        self._private_host_sizing_runtime = None
        if runtime is None:
            return
        with suppress(Exception):
            runtime.close()
        try:
            self._private_host_sizing_snapshot_value = runtime.snapshot()
        except Exception:
            self._private_host_sizing_snapshot_value = None
