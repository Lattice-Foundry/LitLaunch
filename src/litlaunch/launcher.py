"""Public launcher facade."""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import replace
from typing import NamedTuple

from litlaunch._protocols import ClockProvider
from litlaunch.browsers import BrowserLauncher, BrowserRegistry, BrowserResolution
from litlaunch.browsers.registry import create_default_browser_registry
from litlaunch.config import LauncherConfig, LaunchMode
from litlaunch.console import ConsolePhase, ConsoleRenderer
from litlaunch.health import (
    HealthChecker,
    build_streamlit_app_url,
    build_streamlit_health_url,
)
from litlaunch.lifecycle import LaunchEvent, LaunchPlan, LaunchResult, LaunchState
from litlaunch.ports import PortManager
from litlaunch.process import ManagedProcess, ProcessManager
from litlaunch.redaction import format_command_preview, format_env_preview
from litlaunch.session import RuntimeSession
from litlaunch.shutdown import DEFAULT_SHUTDOWN_HOST, ShutdownClient, ShutdownConfig
from litlaunch.streamlit import StreamlitCommandBuilder


class _BackendStart(NamedTuple):
    result: LaunchResult
    process: ManagedProcess | None
    shutdown_client: ShutdownClient | None


class StreamlitLauncher:
    """High-level Streamlit launcher facade."""

    def __init__(
        self,
        config: LauncherConfig,
        *,
        port_manager: PortManager | None = None,
        process_manager: ProcessManager | None = None,
        health_checker: HealthChecker | None = None,
        browser_registry: BrowserRegistry | None = None,
        browser_launcher: BrowserLauncher | None = None,
        console_renderer: ConsoleRenderer | None = None,
        clock: ClockProvider = time,
    ) -> None:
        self.config = config
        self.command_builder = StreamlitCommandBuilder(config)
        self.port_manager = port_manager or PortManager(config.host)
        self.process_manager = process_manager or ProcessManager()
        self.health_checker = health_checker or HealthChecker()
        self.browser_registry = browser_registry or create_default_browser_registry()
        self.browser_launcher = browser_launcher or BrowserLauncher(
            registry=self.browser_registry
        )
        self.console_renderer = console_renderer
        self.clock = clock

    def build_command(self) -> tuple[str, ...]:
        """Build the Streamlit command without starting a process."""

        return self.command_builder.build()

    def resolve_port(self) -> int:
        """Resolve the concrete backend port for this launcher."""

        return self.port_manager.resolve_port(self.config)

    def build_app_url(self, port: int | None = None) -> str:
        """Build the app URL for the resolved or configured port."""

        resolved_port = self.resolve_port() if port is None else port
        return build_streamlit_app_url(self.config.host, resolved_port)

    def build_health_url(self, port: int | None = None) -> str:
        """Build the Streamlit health URL for the resolved or configured port."""

        resolved_port = self.resolve_port() if port is None else port
        return build_streamlit_health_url(self.config.host, resolved_port)

    def resolve_browser(
        self,
        *,
        prefer_app_mode: bool | None = None,
    ) -> BrowserResolution:
        """Resolve browser capability for this launcher without launching it."""

        resolved_preference = self.config.mode == LaunchMode.WEBAPP
        return self.browser_registry.resolve(
            self.config.browser,
            prefer_app_mode=(
                resolved_preference if prefer_app_mode is None else prefer_app_mode
            ),
            allow_fallback=self.config.allow_browser_fallback,
        )

    def build_launch_plan(
        self,
        *,
        include_browser_resolution: bool = True,
    ) -> LaunchPlan:
        """Build a resolved launch plan without starting backend or browser."""

        resolved_port = self.resolve_port()
        command = self.command_builder.build(port=resolved_port)
        return LaunchPlan(
            command=command,
            command_display=format_command_preview(command),
            cwd=self.config.cwd,
            app_url=build_streamlit_app_url(self.config.host, resolved_port),
            health_url=build_streamlit_health_url(self.config.host, resolved_port),
            host=self.config.host,
            port=self.config.port,
            resolved_port=resolved_port,
            auto_port=self.config.auto_port,
            mode=self.config.mode,
            headless=self.command_builder.resolve_headless(),
            browser_requested=self.config.browser,
            browser_resolution=(
                self.resolve_browser() if include_browser_resolution else None
            ),
            allow_browser_fallback=self.config.allow_browser_fallback,
            app_args=self.config.app_args,
            streamlit_flags=_copy_streamlit_flags(self.config.streamlit_flags),
            streamlit_args=self.config.streamlit_args,
            extra_env_preview=(
                format_env_preview(self.config.extra_env)
                if self.config.extra_env
                else "none"
            ),
        )

    def start_backend(
        self,
        *,
        wait_for_health: bool = True,
        health_timeout_seconds: float = 15.0,
        health_interval_seconds: float = 0.25,
    ) -> RuntimeSession:
        """Start the Streamlit backend without launching a browser."""

        self._render_header()
        backend_start = self._start_backend(
            wait_for_health=wait_for_health,
            health_timeout_seconds=health_timeout_seconds,
            health_interval_seconds=health_interval_seconds,
        )
        return RuntimeSession(
            result=backend_start.result,
            process=backend_start.process,
            process_manager=self.process_manager,
            shutdown_client=backend_start.shutdown_client,
            console_renderer=self.console_renderer,
            clock=self.clock,
        )

    def start(
        self,
        *,
        health_timeout_seconds: float = 15.0,
        health_interval_seconds: float = 0.25,
    ) -> RuntimeSession:
        """Start Streamlit, wait for health, launch a browser, and return a session.

        On success, the Streamlit backend remains running and owned by this
        returned RuntimeSession. Window monitoring and graceful shutdown hooks
        build on this lifecycle boundary.
        """

        self._render_header()
        backend_start = self._start_backend(
            wait_for_health=True,
            health_timeout_seconds=health_timeout_seconds,
            health_interval_seconds=health_interval_seconds,
        )
        backend_result = backend_start.result
        managed_process = backend_start.process
        if (
            not backend_result.ok
            or managed_process is None
            or backend_result.url is None
        ):
            return RuntimeSession(
                result=backend_result,
                process=None,
                process_manager=self.process_manager,
                shutdown_client=None,
                console_renderer=self.console_renderer,
                clock=self.clock,
            )

        events = list(backend_result.events)
        self._record(
            events,
            LaunchState.BROWSER_RESOLVING,
            "Resolving browser.",
            render=False,
        )
        resolution = self.resolve_browser(
            prefer_app_mode=self.config.mode == LaunchMode.WEBAPP
        )
        self._record(
            events,
            LaunchState.BROWSER_LAUNCHING,
            resolution.message,
            render=False,
        )
        self._render_browser_resolution(
            resolution,
            prefer_app_mode=self.config.mode == LaunchMode.WEBAPP,
        )
        browser_name = (
            resolution.selected.name if resolution.selected is not None else "browser"
        )
        browser_mode = "app window" if self.config.mode == LaunchMode.WEBAPP else "tab"
        self._render_phase_start(
            ConsolePhase.BROWSER,
            f"opening {browser_name} {browser_mode}",
        )
        browser_start_time = self.clock.monotonic()
        browser_result = self.browser_launcher.launch(
            resolution,
            url=backend_result.url,
            mode=self.config.mode,
            title=self.config.title,
            extra_args=self.config.extra_browser_args,
        )
        browser_elapsed = self.clock.monotonic() - browser_start_time

        if not browser_result.ok:
            self._record(
                events,
                LaunchState.TERMINATING,
                "Browser launch failed; stopping owned backend.",
                render=False,
            )
            self._render_phase_error(ConsolePhase.BROWSER, browser_result.message)
            self._render_failure_guidance(
                "Browser launch failed; stopping the owned backend.",
                likely_cause=browser_result.message,
                next_steps=(
                    "Check that the requested browser is installed and launchable.",
                    (
                        "Use --browser default or enable fallback if app-mode "
                        "is not required."
                    ),
                ),
                detail=browser_result.message,
            )
            self.process_manager.stop(managed_process)
            self._record(
                events,
                LaunchState.FAILED,
                browser_result.message,
                render=False,
            )
            failure_result = LaunchResult(
                ok=False,
                state=LaunchState.FAILED,
                command=backend_result.command,
                pid=backend_result.pid,
                url=backend_result.url,
                message=browser_result.message,
                events=tuple(events),
                browser=browser_result.browser,
                browser_command=browser_result.command,
                browser_launched=False,
            )
            return RuntimeSession(
                result=failure_result,
                process=None,
                process_manager=self.process_manager,
                shutdown_client=None,
                console_renderer=self.console_renderer,
                clock=self.clock,
            )

        self._record(events, LaunchState.RUNNING, browser_result.message, render=False)
        self._render_phase_success(
            ConsolePhase.BROWSER,
            browser_result.message,
            elapsed_seconds=browser_elapsed,
        )
        self._render_runtime_ready(backend_result.url)
        result = LaunchResult(
            ok=True,
            state=LaunchState.RUNNING,
            command=backend_result.command,
            pid=backend_result.pid,
            url=backend_result.url,
            message="Streamlit backend is running and browser launch succeeded.",
            events=tuple(events),
            browser=browser_result.browser,
            browser_command=browser_result.command,
            browser_launched=True,
        )
        return RuntimeSession(
            result=result,
            process=managed_process,
            process_manager=self.process_manager,
            shutdown_client=backend_start.shutdown_client,
            console_renderer=self.console_renderer,
            clock=self.clock,
        )

    def run(
        self,
        *,
        health_timeout_seconds: float = 15.0,
        health_interval_seconds: float = 0.25,
    ) -> RuntimeSession:
        """Start the runtime and return a live RuntimeSession."""

        return self.start(
            health_timeout_seconds=health_timeout_seconds,
            health_interval_seconds=health_interval_seconds,
        )

    def _start_backend(
        self,
        *,
        wait_for_health: bool,
        health_timeout_seconds: float,
        health_interval_seconds: float,
    ) -> _BackendStart:
        """Start the Streamlit backend and return the managed process."""

        events: list[LaunchEvent] = []
        self._record(
            events,
            LaunchState.CREATED,
            "Launcher backend start requested.",
            render=False,
        )
        self._record(
            events,
            LaunchState.CONFIGURED,
            "Launcher configuration accepted.",
            render=False,
        )

        command: tuple[str, ...] | None = None
        pid: int | None = None
        app_url: str | None = None
        shutdown_client: ShutdownClient | None = None

        try:
            port = self.resolve_port()
            self._record(
                events,
                LaunchState.PORT_READY,
                f"Resolved backend port {port}.",
                render=False,
            )
            self._render_detail(f"Backend port: {port}")
            command = self.command_builder.build(port=port)
            self._record(
                events,
                LaunchState.COMMAND_BUILT,
                "Streamlit command built.",
                render=False,
            )
            self._render_detail(f"Command: {format_command_preview(command)}")
            shutdown_config = self._build_shutdown_config(app_port=port)
            shutdown_client = ShutdownClient(
                host=shutdown_config.host,
                port=shutdown_config.port,
                token=shutdown_config.token,
            )
            env = self._build_backend_env(shutdown_config)
            self._record(
                events,
                LaunchState.PROCESS_STARTING,
                "Starting Streamlit backend.",
                render=False,
            )
            self._render_phase_start(ConsolePhase.BACKEND, "starting Streamlit")
            backend_start_time = self.clock.monotonic()
            managed_process = self.process_manager.start(
                command,
                cwd=self.config.cwd,
                env=env,
            )
            backend_elapsed = self.clock.monotonic() - backend_start_time
            pid = getattr(managed_process.popen, "pid", None)
            app_url = build_streamlit_app_url(self.config.host, port)
            health_url = build_streamlit_health_url(self.config.host, port)
            self._record(
                events,
                LaunchState.PROCESS_RUNNING,
                f"Streamlit backend started with PID {pid}.",
                render=False,
            )
            self._render_phase_success(
                ConsolePhase.BACKEND,
                f"started Streamlit with PID {pid}",
                elapsed_seconds=backend_elapsed,
            )

            if wait_for_health:
                self._record(
                    events,
                    LaunchState.HEALTH_CHECKING,
                    "Waiting for Streamlit health endpoint.",
                    render=False,
                )
                self._render_phase_start(ConsolePhase.HEALTH, "waiting for Streamlit")
                health_start_time = self.clock.monotonic()
                healthy = self.health_checker.wait_until_healthy(
                    health_url,
                    timeout_seconds=health_timeout_seconds,
                    interval_seconds=health_interval_seconds,
                )
                health_elapsed = self.clock.monotonic() - health_start_time
                if not healthy:
                    failure_message = self._health_failure_message(
                        managed_process,
                        health_url,
                    )
                    self._record(
                        events,
                        LaunchState.TERMINATING,
                        "Health check failed; stopping owned backend.",
                        render=False,
                    )
                    self._render_health_failure_guidance(
                        managed_process,
                        failure_message,
                    )
                    self.process_manager.stop(managed_process)
                    self._record(
                        events,
                        LaunchState.FAILED,
                        failure_message,
                        render=False,
                    )
                    return _BackendStart(
                        LaunchResult(
                            ok=False,
                            state=LaunchState.FAILED,
                            command=command,
                            pid=pid,
                            url=app_url,
                            message=failure_message,
                            events=tuple(events),
                        ),
                        None,
                        None,
                    )

                self._record(
                    events,
                    LaunchState.HEALTHY,
                    "Streamlit backend is healthy.",
                    render=False,
                )
                self._render_phase_success(
                    ConsolePhase.HEALTH,
                    "ready",
                    elapsed_seconds=health_elapsed,
                )
                return _BackendStart(
                    LaunchResult(
                        ok=True,
                        state=LaunchState.HEALTHY,
                        command=command,
                        pid=pid,
                        url=app_url,
                        message="Streamlit backend started and passed health check.",
                        events=tuple(events),
                    ),
                    managed_process,
                    shutdown_client,
                )

            self._record(
                events,
                LaunchState.PROCESS_RUNNING,
                "Health check skipped; backend process is running.",
                render=False,
            )
            self._render_phase_success(ConsolePhase.BACKEND, "running")
            return _BackendStart(
                LaunchResult(
                    ok=True,
                    state=LaunchState.PROCESS_RUNNING,
                    command=command,
                    pid=pid,
                    url=app_url,
                    message="Streamlit backend started; health check skipped.",
                    events=tuple(events),
                ),
                managed_process,
                shutdown_client,
            )
        except Exception as exc:
            self._record(events, LaunchState.FAILED, str(exc), render=False)
            self._render_backend_start_failure_guidance(str(exc))
            return _BackendStart(
                LaunchResult(
                    ok=False,
                    state=LaunchState.FAILED,
                    command=command,
                    pid=pid,
                    url=app_url,
                    message=str(exc),
                    events=tuple(events),
                ),
                None,
                None,
            )

    def with_port(self, port: int) -> StreamlitLauncher:
        """Return a launcher with the same config and an explicit port."""

        return StreamlitLauncher(
            replace(self.config, port=port, auto_port=False),
            port_manager=self.port_manager,
            process_manager=self.process_manager,
            health_checker=self.health_checker,
            browser_registry=self.browser_registry,
            browser_launcher=self.browser_launcher,
            console_renderer=self.console_renderer,
            clock=self.clock,
        )

    def _health_failure_message(
        self,
        process: ManagedProcess,
        health_url: str,
    ) -> str:
        if not self.process_manager.is_running(process):
            returncode = process.popen.poll()
            return (
                "Streamlit backend process exited before becoming healthy"
                f" (exit code {returncode}). This can happen when Streamlit is not "
                "installed, the app crashes during startup, or a Streamlit CLI "
                "option is invalid."
            )
        return (
            f"Streamlit health check timed out at {health_url}. The backend process "
            "is still running but did not report ready before the timeout."
        )

    def _record(
        self,
        events: list[LaunchEvent],
        state: LaunchState,
        message: str,
        *,
        render: bool = True,
    ) -> None:
        event = LaunchEvent(
            state=state,
            message=message,
            timestamp=self.clock.monotonic(),
        )
        events.append(event)
        if render and self.console_renderer is not None:
            self.console_renderer.render_launch_event(event)

    def _build_shutdown_config(self, *, app_port: int) -> ShutdownConfig:
        start_port = app_port + 1 if app_port < 65535 else 1
        shutdown_port = self.port_manager.find_available_port(
            DEFAULT_SHUTDOWN_HOST,
            start_port=start_port,
        )
        shutdown_config = ShutdownConfig(
            host=DEFAULT_SHUTDOWN_HOST,
            port=shutdown_port,
            token=secrets.token_urlsafe(32),
        )
        if self.console_renderer is not None:
            self.console_renderer.add_redaction(shutdown_config.token)
        return shutdown_config

    def _build_backend_env(self, shutdown_config: ShutdownConfig) -> dict[str, str]:
        return {
            **os.environ,
            **self.config.extra_env,
            **shutdown_config.as_env(),
        }

    def _render_header(self) -> None:
        if self.console_renderer is None:
            return
        self.console_renderer.runtime_start("Starting runtime")
        self.console_renderer.detail(f"App: {self.config.title}")
        self.console_renderer.detail(f"Mode: {self.config.mode.value}")

    def _render_detail(self, message: str) -> None:
        if self.console_renderer is not None:
            self.console_renderer.detail(message)

    def _render_phase_start(self, phase: ConsolePhase, message: str) -> None:
        if self.console_renderer is not None:
            self.console_renderer.phase_start(phase, message)

    def _render_phase_success(
        self,
        phase: ConsolePhase,
        message: str,
        *,
        elapsed_seconds: float | None = None,
    ) -> None:
        if self.console_renderer is not None:
            self.console_renderer.phase_success(
                phase,
                message,
                elapsed_seconds=elapsed_seconds,
            )

    def _render_phase_error(self, phase: ConsolePhase, message: str) -> None:
        if self.console_renderer is not None:
            self.console_renderer.phase_error(phase, message)

    def _render_failure_guidance(
        self,
        summary: str,
        *,
        likely_cause: str | None = None,
        next_steps: tuple[str, ...] = (),
        suggest_inspect: bool = True,
        detail: str | None = None,
    ) -> None:
        if self.console_renderer is not None:
            self.console_renderer.failure_guidance(
                summary,
                likely_cause=likely_cause,
                next_steps=next_steps,
                suggest_inspect=suggest_inspect,
                detail=detail,
            )

    def _render_backend_start_failure_guidance(self, detail: str) -> None:
        self._render_failure_guidance(
            "Backend startup failed.",
            likely_cause=detail,
            next_steps=(
                "Check the app path and Python environment.",
                "Check Streamlit installation and CLI arguments.",
                (
                    "If using a fixed port, confirm it is available or choose "
                    "another port."
                ),
            ),
            detail=detail,
        )

    def _render_health_failure_guidance(
        self,
        process: ManagedProcess,
        detail: str,
    ) -> None:
        if self.process_manager.is_running(process):
            self._render_failure_guidance(
                "Streamlit backend did not become healthy before timeout.",
                likely_cause=(
                    "The app may still be starting, Streamlit may have failed "
                    "internally, or localhost health checks may be blocked."
                ),
                next_steps=(
                    "Increase the health timeout if startup is expected to be slow.",
                    "Run Streamlit directly to see any app traceback.",
                ),
                detail=detail,
            )
            return

        self._render_failure_guidance(
            "Streamlit backend exited before becoming healthy.",
            likely_cause=(
                "Streamlit may be missing, the app may have crashed during import, "
                "or Streamlit CLI arguments may be invalid."
            ),
            next_steps=(
                "Verify Streamlit is installed in this Python environment.",
                "Run the app directly with streamlit run to see the traceback.",
                "Check the app path and command arguments.",
            ),
            detail=detail,
        )

    def _render_browser_resolution(
        self,
        resolution: BrowserResolution,
        *,
        prefer_app_mode: bool,
    ) -> None:
        if self.console_renderer is not None:
            self.console_renderer.render_browser_resolution(
                resolution,
                prefer_app_mode=prefer_app_mode,
            )

    def _render_runtime_ready(self, url: str | None) -> None:
        if self.console_renderer is not None:
            self.console_renderer.runtime_ready(url)


def _copy_streamlit_flags(flags):
    if isinstance(flags, dict):
        return dict(flags)
    if hasattr(flags, "items"):
        return dict(flags.items())
    return tuple(flags)
