"""Command handlers for the LitLaunch CLI."""

from __future__ import annotations

import argparse
from typing import Any

from litlaunch.cli.common import (
    CliContext,
    mode,
    renderer,
    write,
)
from litlaunch.cli.config import (
    MonitorOptions,
    load_cli_profile,
    monitor_options_from_args,
    runtime_config_from_args,
)
from litlaunch.config import BrowserChoice, LaunchMode
from litlaunch.console import ConsoleMode, ConsoleRenderer
from litlaunch.exceptions import LitLaunchError
from litlaunch.monitored import run_profile
from litlaunch.profiles import LaunchProfile
from litlaunch.redaction import redact_sensitive_text
from litlaunch.version import __version__
from litlaunch.windowing import WindowMonitorResult


def cmd_version(args: argparse.Namespace, context: CliContext) -> int:
    """Run the ``version`` command."""

    write(context.stream, f"LitLaunch {__version__}")
    return 0


def cmd_platform(args: argparse.Namespace, context: CliContext) -> int:
    """Run the ``platform`` command."""

    cli_renderer = renderer(args, context)
    info = context.platform_detector_factory().detect()
    cli_renderer.info(info.summary())
    _render_platform_capability(
        cli_renderer,
        "Chromium app mode",
        info.supports_chromium_app_mode,
    )
    _render_platform_capability(
        cli_renderer,
        "default browser open",
        info.supports_default_browser_open,
    )
    _render_platform_capability(
        cli_renderer,
        "window monitoring",
        info.supports_window_monitoring,
    )
    if mode(args) == ConsoleMode.VERBOSE:
        cli_renderer.info_status(f"OS: {info.os.value}")
        cli_renderer.info_status(f"System: {_display_value(info.system)}")
        cli_renderer.info_status(f"Release: {_display_value(info.release)}")
        cli_renderer.info_status(f"Machine: {_display_value(info.machine)}")
        cli_renderer.info_status(f"Architecture: {info.architecture.value}")
        cli_renderer.info_status(f"Python version: {info.python_version}")
        python_executable = _display_value(
            redact_sensitive_text(info.python_executable)
        )
        cli_renderer.info_status(f"Python executable: {python_executable}")
        for note in info.notes:
            cli_renderer.info_status(f"Note: {note}")
    return 0


def cmd_browsers(args: argparse.Namespace, context: CliContext) -> int:
    """Run the ``browsers`` command."""

    cli_renderer = renderer(args, context)
    platform_info = context.platform_detector_factory().detect()
    registry = context.browser_registry_factory()
    capabilities = registry.detect_all(platform_info)
    cli_renderer.info("Browser capabilities")
    for capability in capabilities:
        _render_browser_capability(cli_renderer, capability)
        if mode(args) == ConsoleMode.VERBOSE:
            cli_renderer.info_status(f"Kind: {capability.kind.value}")
            executable_path = _display_value(
                redact_sensitive_text(capability.executable_path or "")
            )
            cli_renderer.info_status(f"Executable: {executable_path}")
            for note in capability.notes:
                cli_renderer.info_status(f"Note: {note}")

    resolution = registry.resolve(
        BrowserChoice.AUTO,
        platform_info,
        prefer_app_mode=True,
    )
    if resolution.selected is None:
        cli_renderer.warning(f"Browser: {resolution.message}")
    else:
        cli_renderer.success(
            f"Browser: selected {resolution.selected.name} for app-mode"
        )
    return 0


def cmd_command(args: argparse.Namespace, context: CliContext) -> int:
    """Run the ``command`` command."""

    cli_renderer = renderer(args, context)
    profile = load_cli_profile(args)
    config = runtime_config_from_args(args, profile=profile)
    launcher = context.launcher_factory(config, console_renderer=cli_renderer)
    plan = launcher.build_launch_plan(include_browser_resolution=False)
    write(context.stream, plan.command_display)
    return 0


def cmd_run(args: argparse.Namespace, context: CliContext) -> int:
    """Run the ``run`` command."""

    cli_renderer = renderer(args, context)
    profile = load_cli_profile(args)
    config = runtime_config_from_args(args, profile=profile)
    monitor_options = monitor_options_from_args(args, profile, config)
    if monitor_options.enabled and config.mode != LaunchMode.WEBAPP:
        raise LitLaunchError("--monitor-window is only valid with --mode webapp.")
    platform_detector = context.platform_detector_factory()
    if (
        monitor_options.enabled
        and not monitor_options.explicit
        and not platform_detector.detect().supports_window_monitoring
    ):
        monitor_options = MonitorOptions(
            enabled=False,
            explicit=False,
            graceful_timeout_seconds=monitor_options.graceful_timeout_seconds,
            window_monitor_config=monitor_options.window_monitor_config,
        )
    launcher = context.launcher_factory(config, console_renderer=cli_renderer)
    if args.dry_run:
        plan = launcher.build_launch_plan()
        cli_renderer.success("Runtime: dry run; backend and browser were not started.")
        cli_renderer.success(f"Runtime: app URL: {plan.app_url}")
        cli_renderer.success(f"Runtime: mode: {config.mode.value}")
        if plan.browser_resolution is not None:
            cli_renderer.success(f"Browser: {plan.browser_resolution.message}")
        write(context.stream, plan.command_display)
        return 0

    runtime_profile = LaunchProfile(
        name=profile.name if profile is not None else "cli",
        config=config,
        monitor_window=monitor_options.enabled,
        graceful_timeout_seconds=monitor_options.graceful_timeout_seconds,
        window_monitor_config=monitor_options.window_monitor_config,
    )
    run_result = run_profile(
        runtime_profile,
        launcher=launcher,
        platform_detector=platform_detector,
        window_monitor_factory=context.window_monitor_factory,
    )

    if monitor_options.enabled:
        if run_result.session is not None and run_result.session.ok:
            cli_renderer.success(f"Runtime active at {run_result.session.url}")
        if run_result.monitor_result is not None:
            render_monitor_result_if_needed(
                run_result.session,
                cli_renderer,
                run_result.monitor_result,
            )
        if not run_result.launched:
            cli_renderer.failure_guidance(
                run_result.message,
                next_steps=(
                    "Omit --monitor-window to launch without close detection.",
                    (
                        "Use Chromium app-mode on Windows for the strongest "
                        "supported path."
                    ),
                ),
            )
        elif run_result.exit_code != 0:
            cli_renderer.failure_guidance(run_result.message)
        return run_result.exit_code

    session = run_result.session
    if session is None:
        cli_renderer.failure_guidance(run_result.message)
        return run_result.exit_code
    if not session.ok:
        cli_renderer.failure_guidance(
            "Runtime: launch failed.",
            likely_cause=session.result.message,
            next_steps=(
                "Run the app directly with streamlit run to compare behavior.",
            ),
            suggest_inspect=True,
        )
        return 1

    cli_renderer.success(f"Runtime active at {session.url}")
    if session.process is None:
        return 0

    try:
        returncode = session.wait()
    except KeyboardInterrupt:
        cli_renderer.warning("Runtime: interrupt received; stopping runtime.")
        session.stop()
        return 0

    return int(returncode or 0)


def render_monitor_result_if_needed(
    session: Any | None,
    cli_renderer: ConsoleRenderer,
    result: WindowMonitorResult,
) -> None:
    """Render monitor results when the session did not already render them."""

    if session is None or getattr(session, "console_renderer", None) is None:
        cli_renderer.render_window_monitor_result(result)


def _render_platform_capability(
    cli_renderer: ConsoleRenderer,
    label: str,
    supported: bool,
) -> None:
    state = "supported" if supported else "not supported"
    message = f"Platform: {label} {state}"
    if supported:
        cli_renderer.success(message)
    else:
        cli_renderer.warning(message)


def _render_browser_capability(cli_renderer: ConsoleRenderer, capability) -> None:
    availability = "available" if capability.available else "unavailable"
    support = (
        "app-mode supported"
        if capability.supports_app_mode
        else "full-browser only"
        if capability.supports_full_browser
        else "no supported launch mode"
    )
    message = f"Browser: {capability.name} {availability}; {support}"
    if capability.available:
        cli_renderer.success(message)
    else:
        cli_renderer.warning(message)


def _display_value(value: object) -> str:
    text = str(value).strip()
    return text or "not reported"
