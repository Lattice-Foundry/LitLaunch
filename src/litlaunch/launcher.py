"""Public launcher facade."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from litlaunch._protocols import ClockProvider
from litlaunch.artifacts import (
    cleanup_litlaunch_owned_dir,
    project_root_for_config,
    runtime_state_root_for_config,
)
from litlaunch.backend import (
    BackendCommandProvider,
    StreamlitBackendCommandProvider,
)
from litlaunch.backend_start import BackendStartResult, start_backend_process
from litlaunch.browser_profiles import (
    create_managed_browser_profile,
    has_browser_switch,
    with_managed_browser_profile_args,
)
from litlaunch.browsers import BrowserLauncher, BrowserRegistry, BrowserResolution
from litlaunch.browsers.registry import create_default_browser_registry
from litlaunch.config import LauncherConfig, LaunchMode
from litlaunch.console import ConsolePhase, ConsoleRenderer
from litlaunch.events import (
    RuntimeEventEmitter,
    RuntimeEventSink,
    compose_runtime_event_sinks,
    create_runtime_event_file_sink,
)
from litlaunch.exceptions import LitLaunchError
from litlaunch.exposure import classify_host_exposure
from litlaunch.governance import validate_runtime_governance
from litlaunch.health import (
    HealthChecker,
    build_streamlit_app_url,
    build_streamlit_health_url,
    parse_url_host_port,
)
from litlaunch.lifecycle import LaunchEvent, LaunchPlan, LaunchResult, LaunchState
from litlaunch.planning import build_launch_plan
from litlaunch.ports import PortManager
from litlaunch.process import ProcessManager
from litlaunch.runtime_console import (
    render_browser_resolution,
    render_failure_guidance,
    render_network_exposure_warning,
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
        config: LauncherConfig | str | Path,
        *,
        port_manager: PortManager | None = None,
        process_manager: ProcessManager | None = None,
        health_checker: HealthChecker | None = None,
        browser_registry: BrowserRegistry | None = None,
        browser_launcher: BrowserLauncher | None = None,
        backend_command_provider: BackendCommandProvider | None = None,
        console_renderer: ConsoleRenderer | None = None,
        event_sink: RuntimeEventSink | None = None,
        clock: ClockProvider = time,
    ) -> None:
        self.config = (
            config if isinstance(config, LauncherConfig) else LauncherConfig(config)
        )
        self.command_builder = StreamlitCommandBuilder(self.config)
        self.backend_command_provider = (
            backend_command_provider or StreamlitBackendCommandProvider()
        )
        self.port_manager = port_manager or PortManager(self.config.host)
        self.process_manager = process_manager or ProcessManager()
        self.health_checker = health_checker or HealthChecker()
        self.browser_registry = browser_registry or create_default_browser_registry()
        self.browser_launcher = browser_launcher or BrowserLauncher(
            registry=self.browser_registry
        )
        self.console_renderer = console_renderer
        self.event_sink = event_sink
        resolved_event_sink = self._runtime_event_sink(event_sink)
        self.event_emitter = RuntimeEventEmitter(
            resolved_event_sink,
            console_renderer=console_renderer,
        )
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
        self._emit_launch_planned()
        self._enforce_network_exposure_acknowledgement()
        self._emit_backend_starting()
        backend_start = self._start_backend(
            wait_for_health=wait_for_health,
            health_timeout_seconds=health_timeout_seconds,
            health_interval_seconds=health_interval_seconds,
        )
        self._emit_backend_start_result(backend_start.result)
        return RuntimeSession(
            result=backend_start.result,
            process=backend_start.process,
            process_manager=self.process_manager,
            shutdown_client=backend_start.shutdown_client,
            console_renderer=self.console_renderer,
            event_emitter=self.event_emitter,
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
        self._emit_launch_planned()
        self._enforce_network_exposure_acknowledgement()
        self._emit_backend_starting()
        backend_start = self._start_backend(
            wait_for_health=True,
            health_timeout_seconds=health_timeout_seconds,
            health_interval_seconds=health_interval_seconds,
        )
        backend_result = backend_start.result
        self._emit_backend_start_result(backend_result)
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
                event_emitter=self.event_emitter,
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
        browser_mode = _browser_launch_display_mode(
            mode=self.config.mode,
            extra_args=self.config.extra_browser_args,
        )
        render_phase_start(
            self.console_renderer,
            ConsolePhase.BROWSER,
            f"opening {browser_name} {browser_mode}",
            verbose_only=True,
        )
        extra_browser_args, cleanup_callbacks = self._browser_launch_args()
        runtime_state_root = runtime_state_root_for_config(self.config)
        browser_start_time = self.clock.monotonic()
        browser_result = self.browser_launcher.launch(
            resolution,
            url=backend_result.url,
            mode=self.config.mode,
            title=self.config.title,
            extra_args=extra_browser_args,
            allow_fallback=self.config.allow_browser_fallback,
            app_icon=self.config.app_icon,
            artifact_root=runtime_state_root,
        )
        cleanup_callbacks = (*cleanup_callbacks, *browser_result.cleanup_callbacks)
        browser_elapsed = self.clock.monotonic() - browser_start_time

        if not browser_result.ok:
            self._record(
                events,
                LaunchState.TERMINATING,
                "Browser launch failed; stopping owned backend.",
                render=False,
            )
            render_failure_guidance(
                self.console_renderer,
                "Browser: launch failed; stopping backend.",
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
            _run_cleanup_callbacks(cleanup_callbacks)
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
                event_emitter=self.event_emitter,
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
        self.event_emitter.emit(
            "browser_launched",
            category="browser",
            message=browser_result.message,
            details={
                "browser": browser_name,
                "mode": self.config.mode.value,
                "url": backend_result.url,
            },
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
            event_emitter=self.event_emitter,
            port_release_checker=self.port_manager.is_port_available,
            cleanup_callbacks=cleanup_callbacks,
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
    ) -> BackendStartResult:
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
            event_sink=self.event_sink,
            clock=self.clock,
        )

    def _runtime_event_sink(
        self,
        event_sink: RuntimeEventSink | None,
    ) -> RuntimeEventSink | None:
        if self.config.runtime_event_log is None:
            return event_sink
        event_log_path = self.config.runtime_event_log.expanduser()
        if not event_log_path.is_absolute():
            event_log_path = project_root_for_config(self.config) / event_log_path
        return compose_runtime_event_sinks(
            event_sink,
            create_runtime_event_file_sink(event_log_path),
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
        host_port = parse_url_host_port(url)
        if host_port is None:
            return
        host, port = host_port
        try:
            released = self.port_manager.is_port_available(host, port)
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

    def _browser_launch_args(
        self,
    ) -> tuple[tuple[str, ...], tuple[Callable[[], object], ...]]:
        if self.config.mode != LaunchMode.WEBAPP:
            return self.config.extra_browser_args, ()
        if has_browser_switch(self.config.extra_browser_args, "--user-data-dir"):
            return self.config.extra_browser_args, ()

        profile_dir = create_managed_browser_profile(
            runtime_state_root_for_config(self.config)
        )
        extra_args = with_managed_browser_profile_args(
            self.config.extra_browser_args,
            profile_dir=profile_dir,
        )

        def cleanup_profile() -> None:
            cleanup_litlaunch_owned_dir(profile_dir)

        cleanup_callbacks: tuple[Callable[[], object], ...] = (cleanup_profile,)
        return extra_args, cleanup_callbacks

    def _enforce_network_exposure_acknowledgement(self) -> None:
        exposure = classify_host_exposure(self.config.host)
        if not exposure.exposed:
            return
        render_network_exposure_warning(
            self.console_renderer,
            exposure,
            config=self.config,
        )
        try:
            validate_runtime_governance(self.config)
        except ValueError as exc:
            raise LitLaunchError(str(exc)) from exc

    def _emit_launch_planned(self) -> None:
        self.event_emitter.emit(
            "launch_planned",
            category="launch",
            message="Runtime launch planned.",
            details={
                "app_path": self.config.app_path,
                "mode": self.config.mode.value,
                "browser": _display_browser_choice(self.config.browser.value),
                "host": self.config.host,
                "port": self.config.port or "auto",
                "streamlit_chrome": (
                    "visible" if self.config.show_streamlit_chrome else "hidden"
                ),
                "runtime_state_root": runtime_state_root_for_config(self.config),
            },
        )

    def _emit_backend_starting(self) -> None:
        self.event_emitter.emit(
            "backend_starting",
            category="backend",
            message="Backend startup requested.",
            details={"host": self.config.host, "port": self.config.port or "auto"},
        )

    def _emit_backend_start_result(self, result: LaunchResult) -> None:
        host_port = parse_url_host_port(result.url)
        details: dict[str, object] = {}
        if result.pid is not None:
            details["pid"] = result.pid
        if host_port is not None:
            details["host"], details["port"] = host_port
        if result.pid is not None:
            self.event_emitter.emit(
                "backend_started",
                category="backend",
                message="Backend process started.",
                details=details,
            )
        if result.ok and result.state == LaunchState.HEALTHY:
            self.event_emitter.emit(
                "health_ready",
                category="health",
                message="Streamlit health check passed.",
                details=details,
            )
        elif not result.ok:
            self.event_emitter.emit(
                "backend_start_failed",
                category="backend",
                level="error",
                message="Backend startup failed.",
                details=details,
            )


def _run_cleanup_callbacks(callbacks: tuple[Callable[[], object], ...]) -> None:
    for callback in callbacks:
        try:
            callback()
        except Exception:
            continue


def _browser_launch_display_mode(
    *,
    mode: LaunchMode,
    extra_args: tuple[str, ...],
) -> str:
    if mode == LaunchMode.WEBAPP:
        return "app window"
    if any(str(arg).strip().lower() == "--new-window" for arg in extra_args):
        return "window"
    return "tab"


def _display_browser_choice(browser: str) -> str:
    normalized = str(browser).strip()
    if normalized.casefold() == "edge":
        return "Edge"
    return normalized
