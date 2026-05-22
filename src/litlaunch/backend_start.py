"""Backend startup orchestration for LitLaunch."""

from __future__ import annotations

import os
import secrets
from typing import NamedTuple

from litlaunch._protocols import ClockProvider
from litlaunch.backend import BackendCommandProvider
from litlaunch.config import LauncherConfig
from litlaunch.console import ConsolePhase, ConsoleRenderer
from litlaunch.health import HealthChecker
from litlaunch.lifecycle import LaunchEvent, LaunchResult, LaunchState
from litlaunch.planning import build_backend_command, build_backend_command_context
from litlaunch.ports import PortManager
from litlaunch.process import ManagedProcess, ProcessManager
from litlaunch.redaction import format_command_preview
from litlaunch.runtime_console import (
    backend_start_message,
    render_backend_start_failure_guidance,
    render_detail,
    render_health_failure_guidance,
    render_phase_start,
    render_phase_success,
)
from litlaunch.shutdown import DEFAULT_SHUTDOWN_HOST, ShutdownClient, ShutdownConfig
from litlaunch.streamlit import StreamlitCommandBuilder


class BackendStartResult(NamedTuple):
    """Result from starting the backend process."""

    result: LaunchResult
    process: ManagedProcess | None
    shutdown_client: ShutdownClient | None


def start_backend_process(
    *,
    config: LauncherConfig,
    port_manager: PortManager,
    process_manager: ProcessManager,
    health_checker: HealthChecker,
    command_builder: StreamlitCommandBuilder,
    backend_command_provider: BackendCommandProvider,
    console_renderer: ConsoleRenderer | None,
    clock: ClockProvider,
    wait_for_health: bool,
    health_timeout_seconds: float,
    health_interval_seconds: float,
) -> BackendStartResult:
    """Start the backend process and optionally wait for health."""

    events: list[LaunchEvent] = []
    _record(
        events,
        LaunchState.CREATED,
        "Launcher backend start requested.",
        clock=clock,
        console_renderer=console_renderer,
        render=False,
    )
    _record(
        events,
        LaunchState.CONFIGURED,
        "Launcher configuration accepted.",
        clock=clock,
        console_renderer=console_renderer,
        render=False,
    )

    command: tuple[str, ...] | None = None
    pid: int | None = None
    app_url: str | None = None
    shutdown_client: ShutdownClient | None = None

    try:
        port = port_manager.resolve_port(config)
        _record(
            events,
            LaunchState.PORT_READY,
            f"Resolved backend port {port}.",
            clock=clock,
            console_renderer=console_renderer,
            render=False,
        )
        render_detail(console_renderer, f"Backend port: {port}")
        context = build_backend_command_context(
            config=config,
            command_builder=command_builder,
            port=port,
        )
        backend_command = build_backend_command(backend_command_provider, context)
        command = backend_command.command
        _record(
            events,
            LaunchState.COMMAND_BUILT,
            f"{backend_command.description} command built.",
            clock=clock,
            console_renderer=console_renderer,
            render=False,
        )
        render_detail(console_renderer, f"Command: {format_command_preview(command)}")
        shutdown_config = _build_shutdown_config(
            app_port=port,
            port_manager=port_manager,
            console_renderer=console_renderer,
        )
        shutdown_client = ShutdownClient(
            host=shutdown_config.host,
            port=shutdown_config.port,
            token=shutdown_config.token,
        )
        env = _build_backend_env(config, shutdown_config)
        _record(
            events,
            LaunchState.PROCESS_STARTING,
            "Starting Streamlit backend.",
            clock=clock,
            console_renderer=console_renderer,
            render=False,
        )
        render_phase_start(
            console_renderer,
            ConsolePhase.BACKEND,
            backend_start_message(backend_command.description),
            verbose_only=True,
        )
        backend_start_time = clock.monotonic()
        managed_process = process_manager.start(
            command,
            cwd=config.cwd,
            env=env,
        )
        backend_elapsed = clock.monotonic() - backend_start_time
        pid = getattr(managed_process.popen, "pid", None)
        app_url = context.app_url
        health_url = context.health_url
        _record(
            events,
            LaunchState.PROCESS_RUNNING,
            f"Streamlit backend started with PID {pid}.",
            clock=clock,
            console_renderer=console_renderer,
            render=False,
        )
        render_phase_success(
            console_renderer,
            ConsolePhase.BACKEND,
            "started Streamlit",
            elapsed_seconds=backend_elapsed,
        )
        render_detail(console_renderer, f"Backend PID: {pid}")

        if wait_for_health:
            return _wait_for_backend_health(
                events=events,
                managed_process=managed_process,
                process_manager=process_manager,
                health_checker=health_checker,
                console_renderer=console_renderer,
                clock=clock,
                command=command,
                pid=pid,
                app_url=app_url,
                health_url=health_url,
                shutdown_client=shutdown_client,
                health_timeout_seconds=health_timeout_seconds,
                health_interval_seconds=health_interval_seconds,
            )

        _record(
            events,
            LaunchState.PROCESS_RUNNING,
            "Health check skipped; backend process is running.",
            clock=clock,
            console_renderer=console_renderer,
            render=False,
        )
        render_phase_success(console_renderer, ConsolePhase.BACKEND, "running")
        return BackendStartResult(
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
        _record(
            events,
            LaunchState.FAILED,
            str(exc),
            clock=clock,
            console_renderer=console_renderer,
            render=False,
        )
        render_backend_start_failure_guidance(console_renderer, str(exc))
        return BackendStartResult(
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


def _wait_for_backend_health(
    *,
    events: list[LaunchEvent],
    managed_process: ManagedProcess,
    process_manager: ProcessManager,
    health_checker: HealthChecker,
    console_renderer: ConsoleRenderer | None,
    clock: ClockProvider,
    command: tuple[str, ...],
    pid: int | None,
    app_url: str,
    health_url: str,
    shutdown_client: ShutdownClient,
    health_timeout_seconds: float,
    health_interval_seconds: float,
) -> BackendStartResult:
    _record(
        events,
        LaunchState.HEALTH_CHECKING,
        "Waiting for Streamlit health endpoint.",
        clock=clock,
        console_renderer=console_renderer,
        render=False,
    )
    render_phase_start(console_renderer, ConsolePhase.HEALTH, "waiting for Streamlit")
    health_start_time = clock.monotonic()
    healthy = health_checker.wait_until_healthy(
        health_url,
        timeout_seconds=health_timeout_seconds,
        interval_seconds=health_interval_seconds,
    )
    health_elapsed = clock.monotonic() - health_start_time
    if not healthy:
        failure_message = _health_failure_message(
            process_manager,
            managed_process,
            health_url,
        )
        _record(
            events,
            LaunchState.TERMINATING,
            "Health check failed; stopping owned backend.",
            clock=clock,
            console_renderer=console_renderer,
            render=False,
        )
        render_health_failure_guidance(
            console_renderer,
            process_manager,
            managed_process,
            failure_message,
        )
        process_manager.stop(managed_process)
        _record(
            events,
            LaunchState.FAILED,
            failure_message,
            clock=clock,
            console_renderer=console_renderer,
            render=False,
        )
        return BackendStartResult(
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

    _record(
        events,
        LaunchState.HEALTHY,
        "Streamlit backend is healthy.",
        clock=clock,
        console_renderer=console_renderer,
        render=False,
    )
    render_phase_success(
        console_renderer,
        ConsolePhase.HEALTH,
        "ready",
        elapsed_seconds=health_elapsed,
    )
    return BackendStartResult(
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


def _record(
    events: list[LaunchEvent],
    state: LaunchState,
    message: str,
    *,
    clock: ClockProvider,
    console_renderer: ConsoleRenderer | None,
    render: bool = True,
) -> None:
    event = LaunchEvent(
        state=state,
        message=message,
        timestamp=clock.monotonic(),
    )
    events.append(event)
    if render and console_renderer is not None:
        console_renderer.render_launch_event(event)


def _build_shutdown_config(
    *,
    app_port: int,
    port_manager: PortManager,
    console_renderer: ConsoleRenderer | None,
) -> ShutdownConfig:
    start_port = app_port + 1 if app_port < 65535 else 1
    shutdown_port = port_manager.find_available_port(
        DEFAULT_SHUTDOWN_HOST,
        start_port=start_port,
    )
    shutdown_config = ShutdownConfig(
        host=DEFAULT_SHUTDOWN_HOST,
        port=shutdown_port,
        token=secrets.token_urlsafe(32),
    )
    if console_renderer is not None:
        console_renderer.add_redaction(shutdown_config.token)
    return shutdown_config


def _build_backend_env(
    config: LauncherConfig,
    shutdown_config: ShutdownConfig,
) -> dict[str, str]:
    return {
        **os.environ,
        **config.extra_env,
        **shutdown_config.as_env(),
    }


def _health_failure_message(
    process_manager: ProcessManager,
    process: ManagedProcess,
    health_url: str,
) -> str:
    if not process_manager.is_running(process):
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
