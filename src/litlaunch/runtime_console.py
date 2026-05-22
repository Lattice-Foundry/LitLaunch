"""Runtime console presentation helpers.

This module keeps user-facing runtime rendering separate from launcher/session
orchestration. Helpers are intentionally side-effect-light: they render only
when a console renderer is supplied and never influence lifecycle decisions.
"""

from __future__ import annotations

from litlaunch.browsers import BrowserResolution
from litlaunch.config import LauncherConfig
from litlaunch.console import ConsolePhase, ConsoleRenderer
from litlaunch.exposure import HostExposure
from litlaunch.process import ManagedProcess, ProcessManager
from litlaunch.transport import evaluate_transport_posture
from litlaunch.windowing import WindowMonitorResult


def render_runtime_header(
    renderer: ConsoleRenderer | None,
    config: LauncherConfig,
) -> None:
    """Render the runtime startup header."""

    if renderer is None:
        return
    renderer.runtime_start("Starting runtime")
    renderer.detail(f"App: {config.title}")
    renderer.detail(f"Mode: {config.mode.value}")


def render_network_exposure_warning(
    renderer: ConsoleRenderer | None,
    exposure: HostExposure,
    *,
    config: LauncherConfig,
) -> None:
    """Render an honest warning for non-loopback host binding."""

    if renderer is None or exposure.warning is None:
        return
    transport = evaluate_transport_posture(
        host=config.host,
        trust_mode=config.trust_mode,
        allow_network_exposure=config.allow_network_exposure,
        streamlit_flags=config.streamlit_flags,
        streamlit_args=config.streamlit_args,
    )
    cause = exposure.warning
    next_steps = [
        "Use --host 127.0.0.1 for localhost-only development.",
        "Use --allow-network-exposure only when this binding is intentional.",
    ]
    if transport.plaintext_network_risk:
        cause = f"{cause} Traffic appears to use plaintext HTTP."
        next_steps.append(
            "Use Streamlit TLS settings or approved network infrastructure "
            "for internal deployments."
        )
    elif transport.tls_status.value == "configured":
        cause = (
            f"{cause} Streamlit-native TLS appears configured, but LitLaunch "
            "does not add authentication or secure the app itself."
        )
        next_steps.append(
            "Confirm certificate handling, authentication, and network controls "
            "outside LitLaunch."
        )
    elif transport.tls_status.value == "incomplete":
        cause = f"{cause} Streamlit TLS settings appear incomplete."
        next_steps.append(
            "Set both server.sslCertFile and server.sslKeyFile, or remove "
            "partial TLS settings."
        )
    renderer.failure_guidance(
        "Runtime: network exposure requested.",
        likely_cause=cause,
        next_steps=tuple(next_steps),
        level="warning",
    )


def render_detail(renderer: ConsoleRenderer | None, message: str) -> None:
    """Render a verbose runtime detail."""

    if renderer is not None:
        renderer.detail(message)


def render_phase_start(
    renderer: ConsoleRenderer | None,
    phase: ConsolePhase,
    message: str,
    *,
    verbose_only: bool = False,
) -> None:
    """Render the start of a runtime phase."""

    if verbose_only and (renderer is None or renderer.mode.value != "verbose"):
        return
    if renderer is not None:
        renderer.phase_start(phase, message)


def render_phase_success(
    renderer: ConsoleRenderer | None,
    phase: ConsolePhase,
    message: str,
    *,
    elapsed_seconds: float | None = None,
    verbose_only: bool = False,
) -> None:
    """Render successful completion of a runtime phase."""

    if verbose_only and (renderer is None or renderer.mode.value != "verbose"):
        return
    if renderer is not None:
        renderer.phase_success(phase, message, elapsed_seconds=elapsed_seconds)


def render_phase_warning(
    renderer: ConsoleRenderer | None,
    phase: ConsolePhase,
    message: str,
) -> None:
    """Render a non-fatal runtime phase warning."""

    if renderer is not None:
        renderer.phase_warning(phase, message)


def render_phase_error(
    renderer: ConsoleRenderer | None,
    phase: ConsolePhase,
    message: str,
) -> None:
    """Render a runtime phase error."""

    if renderer is not None:
        renderer.phase_error(phase, message)


def render_failure_guidance(
    renderer: ConsoleRenderer | None,
    summary: str,
    *,
    likely_cause: str | None = None,
    next_steps: tuple[str, ...] = (),
    suggest_inspect: bool = True,
    detail: str | None = None,
    level: str = "error",
) -> None:
    """Render actionable failure guidance."""

    if renderer is not None:
        renderer.failure_guidance(
            summary,
            likely_cause=likely_cause,
            next_steps=next_steps,
            suggest_inspect=suggest_inspect,
            detail=detail,
            level=level,
        )


def render_backend_start_failure_guidance(
    renderer: ConsoleRenderer | None,
    detail: str,
) -> None:
    """Render backend-start failure guidance."""

    render_failure_guidance(
        renderer,
        "Backend: startup failed.",
        likely_cause=(
            "Streamlit may be missing or the app may have crashed during startup."
        ),
        next_steps=(
            "Check the app path and Python environment.",
            "Check Streamlit installation and CLI arguments.",
            "If using a fixed port, confirm it is available or choose another port.",
        ),
        detail=detail,
    )


def render_health_failure_guidance(
    renderer: ConsoleRenderer | None,
    process_manager: ProcessManager,
    process: ManagedProcess,
    detail: str,
) -> None:
    """Render health-check failure guidance based on process state."""

    if process_manager.is_running(process):
        render_failure_guidance(
            renderer,
            "Health: backend did not become healthy before timeout.",
            likely_cause="The app started but did not report ready in time.",
            next_steps=(
                "Increase the health timeout if startup is expected to be slow.",
                "Run Streamlit directly to see any app traceback.",
            ),
            detail=detail,
        )
        return

    render_failure_guidance(
        renderer,
        "Backend: exited before becoming healthy.",
        likely_cause=(
            "Streamlit may be missing or the app may have crashed during startup."
        ),
        next_steps=(
            "Verify Streamlit is installed in this Python environment.",
            "Run the app directly with streamlit run to see the traceback.",
            "Check the app path and command arguments.",
        ),
        detail=detail,
    )


def render_browser_resolution(
    renderer: ConsoleRenderer | None,
    resolution: BrowserResolution,
    *,
    prefer_app_mode: bool,
) -> None:
    """Render browser resolution details."""

    if renderer is not None:
        renderer.render_browser_resolution(
            resolution,
            prefer_app_mode=prefer_app_mode,
        )


def render_runtime_ready(renderer: ConsoleRenderer | None, url: str | None) -> None:
    """Render the runtime-ready message."""

    if renderer is not None:
        renderer.runtime_ready(url)


def render_window_monitor_result(
    renderer: ConsoleRenderer | None,
    result: WindowMonitorResult,
) -> None:
    """Render a window-monitor result."""

    if renderer is not None:
        renderer.render_window_monitor_result(result)


def backend_start_message(description: str) -> str:
    """Return the console message for starting a backend command."""

    if description == "Streamlit backend":
        return "starting Streamlit"
    return f"starting {description}"
