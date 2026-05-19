"""Public launcher facade."""

from __future__ import annotations

import time
from dataclasses import replace

from litlaunch.browsers import BrowserRegistry, BrowserResolution
from litlaunch.browsers.registry import create_default_browser_registry
from litlaunch.config import LauncherConfig
from litlaunch.health import (
    HealthChecker,
    build_streamlit_app_url,
    build_streamlit_health_url,
)
from litlaunch.lifecycle import LaunchEvent, LaunchResult, LaunchState
from litlaunch.ports import PortManager
from litlaunch.process import ProcessManager
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
        clock: object = time,
    ) -> None:
        self.config = config
        self.command_builder = StreamlitCommandBuilder(config)
        self.port_manager = port_manager or PortManager(config.host)
        self.process_manager = process_manager or ProcessManager()
        self.health_checker = health_checker or HealthChecker()
        self.browser_registry = browser_registry or create_default_browser_registry()
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
    ) -> LaunchResult:
        """Start the Streamlit backend without launching a browser."""

        events: list[LaunchEvent] = []
        self._record(events, LaunchState.CREATED, "Launcher backend start requested.")
        self._record(events, LaunchState.CONFIGURED, "Launcher configuration accepted.")

        command: tuple[str, ...] | None = None
        pid: int | None = None
        app_url: str | None = None

        try:
            port = self.resolve_port()
            self._record(
                events, LaunchState.PORT_READY, f"Resolved backend port {port}."
            )
            command = self.command_builder.build(port=port)
            self._record(events, LaunchState.COMMAND_BUILT, "Streamlit command built.")
            self._record(
                events, LaunchState.PROCESS_STARTING, "Starting Streamlit backend."
            )
            managed_process = self.process_manager.start(command)
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
                    return LaunchResult(
                        ok=False,
                        state=LaunchState.FAILED,
                        command=command,
                        pid=pid,
                        url=app_url,
                        message="Streamlit health check timed out.",
                        events=tuple(events),
                    )

                self._record(
                    events, LaunchState.HEALTHY, "Streamlit backend is healthy."
                )
                return LaunchResult(
                    ok=True,
                    state=LaunchState.HEALTHY,
                    command=command,
                    pid=pid,
                    url=app_url,
                    message="Streamlit backend started and passed health check.",
                    events=tuple(events),
                )

            self._record(
                events,
                LaunchState.PROCESS_RUNNING,
                "Health check skipped; backend process is running.",
            )
            return LaunchResult(
                ok=True,
                state=LaunchState.PROCESS_RUNNING,
                command=command,
                pid=pid,
                url=app_url,
                message="Streamlit backend started; health check skipped.",
                events=tuple(events),
            )
        except Exception as exc:
            self._record(events, LaunchState.FAILED, str(exc))
            return LaunchResult(
                ok=False,
                state=LaunchState.FAILED,
                command=command,
                pid=pid,
                url=app_url,
                message=str(exc),
                events=tuple(events),
            )

    def run(self) -> None:
        """Run the configured Streamlit app.

        Browser launch, shutdown hooks, and window monitoring are intentionally
        deferred. Use start_backend() for the current runtime-management spine.
        """

        raise NotImplementedError(
            "StreamlitLauncher.run() is not implemented yet. "
            "Use start_backend() for backend-only lifecycle work."
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
        events.append(
            LaunchEvent(
                state=state,
                message=message,
                timestamp=self.clock.monotonic(),
            )
        )
