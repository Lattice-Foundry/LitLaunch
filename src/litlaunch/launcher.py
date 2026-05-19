"""Public launcher facade."""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import replace
from typing import NamedTuple

from litlaunch.browsers import BrowserLauncher, BrowserRegistry, BrowserResolution
from litlaunch.browsers.registry import create_default_browser_registry
from litlaunch.config import LauncherConfig, LaunchMode
from litlaunch.console import ConsoleRenderer
from litlaunch.health import (
    HealthChecker,
    build_streamlit_app_url,
    build_streamlit_health_url,
)
from litlaunch.lifecycle import LaunchEvent, LaunchResult, LaunchState
from litlaunch.ports import PortManager
from litlaunch.process import ManagedProcess, ProcessManager
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
        clock: object = time,
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

        resolved_preference = self.config.mode.value == "webapp"
        return self.browser_registry.resolve(
            self.config.browser,
            prefer_app_mode=(
                resolved_preference if prefer_app_mode is None else prefer_app_mode
            ),
            allow_fallback=self.config.allow_browser_fallback,
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
        self._record(events, LaunchState.BROWSER_RESOLVING, "Resolving browser.")
        resolution = self.resolve_browser(
            prefer_app_mode=self.config.mode == LaunchMode.WEBAPP
        )
        self._record(events, LaunchState.BROWSER_LAUNCHING, resolution.message)
        browser_result = self.browser_launcher.launch(
            resolution,
            url=backend_result.url,
            mode=self.config.mode,
            title=self.config.title,
            extra_args=self.config.extra_browser_args,
        )

        if not browser_result.ok:
            self._record(
                events,
                LaunchState.TERMINATING,
                "Browser launch failed; stopping owned backend.",
            )
            self.process_manager.stop(managed_process)
            self._record(events, LaunchState.FAILED, browser_result.message)
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

        self._record(events, LaunchState.RUNNING, browser_result.message)
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
        self._record(events, LaunchState.CREATED, "Launcher backend start requested.")
        self._record(events, LaunchState.CONFIGURED, "Launcher configuration accepted.")

        command: tuple[str, ...] | None = None
        pid: int | None = None
        app_url: str | None = None
        shutdown_client: ShutdownClient | None = None

        try:
            port = self.resolve_port()
            self._record(
                events, LaunchState.PORT_READY, f"Resolved backend port {port}."
            )
            command = self.command_builder.build(port=port)
            self._record(events, LaunchState.COMMAND_BUILT, "Streamlit command built.")
            self._render_detail(f"Command: {' '.join(command)}")
            shutdown_config = self._build_shutdown_config(app_port=port)
            shutdown_client = ShutdownClient(
                host=shutdown_config.host,
                port=shutdown_config.port,
                token=shutdown_config.token,
            )
            env = self._build_backend_env(shutdown_config)
            self._record(
                events, LaunchState.PROCESS_STARTING, "Starting Streamlit backend."
            )
            managed_process = self.process_manager.start(command, env=env)
            pid = getattr(managed_process.popen, "pid", None)
            app_url = build_streamlit_app_url(self.config.host, port)
            health_url = build_streamlit_health_url(self.config.host, port)
            self._record(
                events,
                LaunchState.PROCESS_RUNNING,
                f"Streamlit backend started with PID {pid}.",
            )

            if wait_for_health:
                self._record(
                    events,
                    LaunchState.HEALTH_CHECKING,
                    "Waiting for Streamlit health endpoint.",
                )
                healthy = self.health_checker.wait_until_healthy(
                    health_url,
                    timeout_seconds=health_timeout_seconds,
                    interval_seconds=health_interval_seconds,
                )
                if not healthy:
                    self._record(
                        events,
                        LaunchState.TERMINATING,
                        "Health check failed; stopping owned backend.",
                    )
                    self.process_manager.stop(managed_process)
                    self._record(
                        events,
                        LaunchState.FAILED,
                        "Streamlit health check timed out.",
                    )
                    return _BackendStart(
                        LaunchResult(
                            ok=False,
                            state=LaunchState.FAILED,
                            command=command,
                            pid=pid,
                            url=app_url,
                            message="Streamlit health check timed out.",
                            events=tuple(events),
                        ),
                        None,
                        None,
                    )

                self._record(
                    events, LaunchState.HEALTHY, "Streamlit backend is healthy."
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
            )
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
            self._record(events, LaunchState.FAILED, str(exc))
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

        return StreamlitLauncher(replace(self.config, port=port, auto_port=False))

    def _record(
        self,
        events: list[LaunchEvent],
        state: LaunchState,
        message: str,
    ) -> None:
        event = LaunchEvent(
            state=state,
            message=message,
            timestamp=self.clock.monotonic(),
        )
        events.append(event)
        if self.console_renderer is not None:
            self.console_renderer.render_launch_event(event)

    def _build_shutdown_config(self, *, app_port: int) -> ShutdownConfig:
        start_port = app_port + 1 if app_port < 65535 else 1
        shutdown_port = self.port_manager.find_available_port(
            DEFAULT_SHUTDOWN_HOST,
            start_port=start_port,
        )
        if shutdown_port == app_port:
            shutdown_port = self.port_manager.find_available_port(
                DEFAULT_SHUTDOWN_HOST,
                start_port=app_port + 1 if app_port < 65535 else 1,
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
        return {**os.environ, **shutdown_config.as_env()}

    def _render_header(self) -> None:
        if self.console_renderer is None:
            return
        self.console_renderer.header(
            "LitLaunch",
            f"{self.config.title} / {self.config.mode.value}",
        )

    def _render_detail(self, message: str) -> None:
        if self.console_renderer is not None:
            self.console_renderer.detail(message)
