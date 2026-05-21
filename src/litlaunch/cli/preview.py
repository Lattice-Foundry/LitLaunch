"""Internal console-preview tooling for LitLaunch developers.

The preview command renders representative runtime console scenarios without
starting a backend, opening a browser, touching ports, or collecting real
diagnostics. It exists so LitLaunch contributors can review terminal alignment,
colors, category labels, verbosity separation, and future screenshot candidates.

This is intentionally internal developer tooling, not a stable public API. The
preview scenarios and exact output may evolve as console wording and diagnostics
rendering mature.
"""

from __future__ import annotations

import argparse

from litlaunch.browsers import BrowserCapability, BrowserKind, BrowserResolution
from litlaunch.cli.common import CliContext
from litlaunch.colors import streamlit_blue, success_green
from litlaunch.config import BrowserChoice
from litlaunch.console import ConsoleMode, ConsolePhase, ConsoleRenderer, ConsoleTheme
from litlaunch.lifecycle import LaunchEvent, LaunchState
from litlaunch.shutdown import ShutdownHookResult
from litlaunch.windowing import WindowMonitorResult, WindowMonitorStatus

EXAMPLE_URL = "http://127.0.0.1:8501"
EXAMPLE_HEALTH_URL = "http://127.0.0.1:8501/_stcore/health"


def add_console_preview_flags(parser: argparse.ArgumentParser) -> None:
    """Add internal console-preview mode flags."""

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--all",
        dest="preview_mode",
        action="store_const",
        const="all",
        default="all",
        help="Preview normal and verbose console output.",
    )
    group.add_argument(
        "--normal",
        dest="preview_mode",
        action="store_const",
        const="normal",
        help="Preview normal-mode console output.",
    )
    group.add_argument(
        "--verbose",
        dest="preview_mode",
        action="store_const",
        const="verbose",
        help="Preview verbose-mode console output.",
    )


def cmd_console_preview(args: argparse.Namespace, context: CliContext) -> int:
    """Render representative runtime console output without launching anything."""

    preview_mode = str(getattr(args, "preview_mode", "all"))
    if preview_mode == "normal":
        render_console_preview(_preview_renderer(args, context, ConsoleMode.NORMAL))
        return 0
    if preview_mode == "verbose":
        render_console_preview(_preview_renderer(args, context, ConsoleMode.VERBOSE))
        return 0

    render_console_preview(_preview_renderer(args, context, ConsoleMode.NORMAL))
    render_console_preview(_preview_renderer(args, context, ConsoleMode.VERBOSE))
    return 0


def _preview_renderer(
    args: argparse.Namespace,
    context: CliContext,
    mode: ConsoleMode,
) -> ConsoleRenderer:
    use_color = "NO_COLOR" not in context.env
    return ConsoleRenderer(
        mode=mode,
        theme=ConsoleTheme(use_color=use_color),
        stream=context.stream,
        env=context.env,
    )


def render_console_preview(console: ConsoleRenderer) -> None:
    """Render every runtime console message style for visual review."""

    mode_label = (
        "Verbose mode" if console.mode == ConsoleMode.VERBOSE else "Normal mode"
    )
    _section(console, mode_label)

    _section(console, "Startup")
    console.runtime_start("Starting runtime")
    console.detail("App: Example App")
    console.detail("Mode: webapp")

    _section(console, "Status Labels")
    console.success("Runtime: active at http://127.0.0.1:8501")
    console.warning("Runtime: interrupt received; stopping runtime.")
    console.error("Runtime: launch failed.")
    console.success("Runtime: dry run; backend and browser were not started.")

    _section(console, "Backend")
    console.phase_start(ConsolePhase.BACKEND, "starting Streamlit")
    console.phase_success(
        ConsolePhase.BACKEND,
        "started Streamlit",
        elapsed_seconds=0.3,
    )
    console.detail("Backend PID: 12345")
    console.failure_guidance(
        "Backend: startup failed.",
        likely_cause=(
            "Streamlit may be missing or the app may have crashed during startup."
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
        "Health: backend did not become healthy before timeout.",
        likely_cause="The app started but did not report ready in time.",
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
    console.failure_guidance(
        "Browser: launch failed; stopping backend.",
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
        LaunchEvent(LaunchState.TERMINATED, "Backend: exited cleanly", 0.0)
    )
    console.failure_guidance(
        "Backend: exited with code 1.",
        likely_cause="The backend stopped with an error status.",
        next_steps=("Run Streamlit directly to inspect the traceback.",),
        suggest_inspect=False,
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
    console.phase_start(ConsolePhase.HOOK, "closing database connections")
    console.render_shutdown_hook_result(
        ShutdownHookResult(
            label="Closing database connections",
            ok=True,
            message="Closed database connections",
            color=success_green,
        )
    )
    console.phase_start(ConsolePhase.HOOK, "saving app state")
    console.render_shutdown_hook_result(
        ShutdownHookResult(
            label="Saving app state",
            ok=False,
            message="Saving app state failed",
            error="disk write failed",
            color=streamlit_blue,
        )
    )
    console.phase_success(ConsolePhase.SHUTDOWN, "app cleanup request accepted")
    if console.mode == ConsoleMode.VERBOSE:
        console.phase_warning(
            ConsolePhase.BACKEND,
            "graceful shutdown failed; using termination fallback",
        )
    console.failure_guidance(
        "Shutdown: graceful request failed.",
        likely_cause="The app did not accept the cleanup request.",
        next_steps=(
            "Confirm the app calls LauncherRuntime.enable_shutdown_endpoint().",
            "Use verbose mode for more runtime details.",
        ),
    )
    if console.mode == ConsoleMode.VERBOSE:
        console.phase_warning(
            ConsolePhase.BACKEND,
            "terminating owned process",
        )
    console.failure_guidance(
        "Shutdown: using backend termination fallback.",
        likely_cause="The backend did not stop through graceful shutdown.",
        next_steps=("LitLaunch will stop only the backend process it started.",),
        suggest_inspect=False,
        level="warning",
    )
    console.phase_success(
        ConsolePhase.SHUTDOWN,
        "complete; backend stopped cleanly",
        elapsed_seconds=0.2,
    )
    console.success("Backend: port 8501 released")
    console.phase_success(
        ConsolePhase.SHUTDOWN,
        "complete; backend stopped through termination fallback",
        elapsed_seconds=0.5,
    )


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
