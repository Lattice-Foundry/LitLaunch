"""Temporary developer console-preview command for LitLaunch beta polish."""

from __future__ import annotations

import argparse

from litlaunch.browsers import BrowserCapability, BrowserKind, BrowserResolution
from litlaunch.cli.common import CliContext, renderer
from litlaunch.config import BrowserChoice
from litlaunch.console import ConsolePhase, ConsoleRenderer
from litlaunch.lifecycle import LaunchEvent, LaunchState
from litlaunch.windowing import WindowMonitorResult, WindowMonitorStatus

EXAMPLE_URL = "http://127.0.0.1:8501"
EXAMPLE_HEALTH_URL = "http://127.0.0.1:8501/_stcore/health"


def cmd_console_preview(args: argparse.Namespace, context: CliContext) -> int:
    """Render representative runtime console output without launching anything."""

    render_console_preview(renderer(args, context))
    return 0


def render_console_preview(console: ConsoleRenderer) -> None:
    """Render every runtime console message style for visual review."""

    _section(console, "Startup")
    console.runtime_start("Starting runtime")
    console.detail("App: Example App")
    console.detail("Mode: webapp")

    _section(console, "Status Labels")
    console.success("Runtime active at http://127.0.0.1:8501")
    console.warning("Interrupt received; stopping runtime.")
    console.error("Runtime launch failed.")
    console.success("Dry run: backend and browser were not started.")

    _section(console, "Backend")
    console.phase_start(ConsolePhase.BACKEND, "starting Streamlit")
    console.phase_success(
        ConsolePhase.BACKEND,
        "started Streamlit with PID 12345",
        elapsed_seconds=0.3,
    )
    console.failure_guidance(
        "Backend startup failed.",
        likely_cause=(
            "Streamlit may be missing, the app may have crashed during import, "
            "or Streamlit CLI arguments may be invalid."
        ),
        next_steps=(
            "Check the app path and Python environment.",
            "Run the app directly with streamlit run to see the traceback.",
        ),
        suggest_inspect=True,
        detail=("Example command: python -m streamlit run app.py --server.port 8501"),
    )

    _section(console, "Health")
    console.phase_start(ConsolePhase.HEALTH, "waiting for Streamlit")
    console.phase_success(ConsolePhase.HEALTH, "ready", elapsed_seconds=1.2)
    console.failure_guidance(
        "Streamlit backend did not become healthy before timeout.",
        likely_cause=(
            f"The backend did not report ready at {EXAMPLE_HEALTH_URL} "
            "before the timeout."
        ),
        next_steps=(
            "Increase the health timeout if startup is expected to be slow.",
            "Run Streamlit directly to see any app traceback.",
        ),
        suggest_inspect=True,
    )

    _section(console, "Browser")
    console.phase_start(ConsolePhase.BROWSER, "opening Microsoft Edge app window")
    console.phase_success(
        ConsolePhase.BROWSER,
        "browser launched",
        elapsed_seconds=0.4,
    )
    console.render_browser_resolution(
        _browser_fallback_resolution(),
        prefer_app_mode=True,
    )
    console.phase_error(ConsolePhase.BROWSER, "browser launch failed")
    console.failure_guidance(
        "Browser launch failed; stopping the owned backend.",
        likely_cause="Microsoft Edge could not be started in app-mode.",
        next_steps=(
            "Check that the requested browser is installed and launchable.",
            "Use --browser default or enable fallback if app-mode is not required.",
        ),
        suggest_inspect=True,
    )

    _section(console, "Runtime")
    console.runtime_ready(EXAMPLE_URL)
    console.render_launch_event(
        LaunchEvent(LaunchState.TERMINATED, "Owned backend process stopped.", 0.0)
    )

    _section(console, "Monitor")
    console.phase_start(ConsolePhase.MONITOR, "watching app window")
    console.render_window_monitor_result(
        WindowMonitorResult(
            supported=True,
            observed=True,
            closed=False,
            status=WindowMonitorStatus.WINDOW_OBSERVED,
            message="Observed app window: Example App.",
        )
    )
    console.render_window_monitor_result(
        WindowMonitorResult(
            supported=True,
            observed=True,
            closed=True,
            status=WindowMonitorStatus.WINDOW_CLOSED,
            message="Window closed.",
        )
    )
    console.render_window_monitor_result(
        WindowMonitorResult(
            supported=True,
            observed=False,
            closed=False,
            status=WindowMonitorStatus.TIMEOUT,
            message="No stable app window appeared before timeout.",
        )
    )
    console.render_window_monitor_result(
        WindowMonitorResult(
            supported=False,
            observed=False,
            closed=False,
            status=WindowMonitorStatus.UNSUPPORTED,
            message="This platform has no supported window monitor provider.",
        )
    )
    console.render_window_monitor_result(
        WindowMonitorResult(
            supported=True,
            observed=False,
            closed=False,
            status=WindowMonitorStatus.ERROR,
            message="Window enumeration failed.",
        )
    )
    console.render_window_monitor_result(
        WindowMonitorResult(
            supported=True,
            observed=True,
            closed=False,
            status=WindowMonitorStatus.BACKEND_EXITED,
            message="Backend exited before the monitored window closed.",
        )
    )

    _section(console, "Shutdown")
    console.phase_start(ConsolePhase.SHUTDOWN, "requested")
    console.phase_start(ConsolePhase.SHUTDOWN, "requesting app cleanup")
    console.phase_success(ConsolePhase.SHUTDOWN, "app cleanup request accepted")
    console.phase_warning(
        ConsolePhase.STOPPING_BACKEND,
        "graceful request failed; using termination fallback",
    )
    console.failure_guidance(
        "Graceful shutdown request failed.",
        likely_cause="The app-side shutdown endpoint did not accept the request.",
        next_steps=(
            "Confirm the app calls LauncherRuntime.enable_shutdown_endpoint().",
            "Use verbose mode for more runtime details.",
        ),
    )
    console.phase_warning(
        ConsolePhase.STOPPING_BACKEND,
        "terminating owned backend process",
    )
    console.failure_guidance(
        "Using backend termination fallback.",
        likely_cause="The backend did not stop through graceful shutdown.",
        next_steps=("LitLaunch will stop only the backend process it started.",),
        suggest_inspect=False,
    )
    console.phase_success(
        ConsolePhase.SHUTDOWN,
        "complete; backend already stopped",
        elapsed_seconds=0.2,
    )
    console.phase_success(ConsolePhase.SHUTDOWN, "complete", elapsed_seconds=0.5)


def _section(console: ConsoleRenderer, title: str) -> None:
    console.blank()
    console.info(f"== {title} ==")


def _browser_fallback_resolution() -> BrowserResolution:
    preferred = BrowserCapability(
        kind=BrowserKind.EDGE,
        name="Microsoft Edge",
        executable_path=None,
        available=False,
        supports_app_mode=True,
        supports_full_browser=True,
    )
    selected = BrowserCapability(
        kind=BrowserKind.CHROME,
        name="Chrome",
        executable_path="chrome.exe",
        available=True,
        supports_app_mode=True,
        supports_full_browser=True,
    )
    return BrowserResolution(
        requested=BrowserChoice.EDGE,
        selected=selected,
        fallback_chain=(preferred, selected),
        message="Selected Chrome.",
    )
