"""Public launcher facade."""

from __future__ import annotations

import time
from dataclasses import replace
from urllib.parse import urlparse

from litlaunch._protocols import ClockProvider
from litlaunch.backend import (
    BackendCommandProvider,
    StreamlitBackendCommandProvider,
)
from litlaunch.backend_start import start_backend_process
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
from litlaunch.planning import build_launch_plan
from litlaunch.ports import PortManager
from litlaunch.process import ProcessManager
from litlaunch.runtime_console import (
    render_browser_resolution,
    render_failure_guidance,
    render_phase_error,
    render_phase_start,
    render_phase_success,
    render_runtime_header,
    render_runtime_ready,
)
from litlaunch.session import RuntimeSession
from litlaunch.streamlit import StreamlitCommandBuilder


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
        backend_command_provider: BackendCommandProvider | None = None,
        console_renderer: ConsoleRenderer | None = None,
        clock: ClockProvider = time,
    ) -> None:
        self.config = config
        self.command_builder = StreamlitCommandBuilder(config)
        self.backend_command_provider = (
            backend_command_provider or StreamlitBackendCommandProvider()
        )
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
        """Build the backend command without starting a process.

        This is a compatibility wrapper over :meth:`build_launch_plan` so
        custom backend command providers see the same resolved launch context
        used by planning and process start.
        """

        return self.build_launch_plan(include_browser_resolution=False).command

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

        return build_launch_plan(
            config=self.config,
            port_manager=self.port_manager,
            command_builder=self.command_builder,
            backend_command_provider=self.backend_command_provider,
            browser_resolver=self.resolve_browser,
            include_browser_resolution=include_browser_resolution,
        )

    def start_backend(
        self,
        *,
        wait_for_health: bool = True,
        health_timeout_seconds: float = 15.0,
        health_interval_seconds: float = 0.25,
    ) -> RuntimeSession:
        """Start the Streamlit backend without launching a browser."""

        render_runtime_header(self.console_renderer, self.config)
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
            port_release_checker=self.port_manager.is_port_available,
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

        render_runtime_header(self.console_renderer, self.config)
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
                port_release_checker=self.port_manager.is_port_available,
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
        render_browser_resolution(
            self.console_renderer,
            resolution,
            prefer_app_mode=self.config.mode == LaunchMode.WEBAPP,
        )
        browser_name = (
            resolution.selected.name if resolution.selected is not None else "browser"
        )
        browser_mode = "app window" if self.config.mode == LaunchMode.WEBAPP else "tab"
        render_phase_start(
            self.console_renderer,
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
            allow_fallback=self.config.allow_browser_fallback,
        )
        browser_elapsed = self.clock.monotonic() - browser_start_time

        if not browser_result.ok:
            self._record(
                events,
                LaunchState.TERMINATING,
                "Browser launch failed; stopping owned backend.",
                render=False,
            )
            render_phase_error(
                self.console_renderer,
                ConsolePhase.BROWSER,
                browser_result.message,
            )
            render_failure_guidance(
                self.console_renderer,
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
            self._render_port_release_if_verified(backend_result.url)
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
                port_release_checker=self.port_manager.is_port_available,
                clock=self.clock,
            )

        self._record(events, LaunchState.RUNNING, browser_result.message, render=False)
        render_phase_success(
            self.console_renderer,
            ConsolePhase.BROWSER,
            browser_result.message,
            elapsed_seconds=browser_elapsed,
        )
        render_runtime_ready(self.console_renderer, backend_result.url)
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
            port_release_checker=self.port_manager.is_port_available,
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
    ):
        """Start the Streamlit backend and return the managed process."""

        return start_backend_process(
            config=self.config,
            port_manager=self.port_manager,
            process_manager=self.process_manager,
            health_checker=self.health_checker,
            command_builder=self.command_builder,
            backend_command_provider=self.backend_command_provider,
            console_renderer=self.console_renderer,
            clock=self.clock,
            wait_for_health=wait_for_health,
            health_timeout_seconds=health_timeout_seconds,
            health_interval_seconds=health_interval_seconds,
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
            backend_command_provider=self.backend_command_provider,
            console_renderer=self.console_renderer,
            clock=self.clock,
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

    def _render_port_release_if_verified(self, url: str | None) -> None:
        if self.console_renderer is None:
            return
        host_port = _parse_url_host_port(url)
        if host_port is None:
            return
        host, port = host_port
        try:
            released = self.port_manager.is_port_available(host, port)
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
