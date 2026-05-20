"""Command-line interface for LitLaunch."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from litlaunch.browsers.registry import create_default_browser_registry
from litlaunch.config import BrowserChoice, LauncherConfig, LaunchMode
from litlaunch.console import ConsoleMode, ConsoleRenderer, ConsoleTheme
from litlaunch.exceptions import LitLaunchError
from litlaunch.inspect import (
    DiagnosticCollector,
    HTMLDiagnosticsRenderer,
    JSONDiagnosticsRenderer,
    SanitizedBundleRenderer,
    TextDiagnosticsRenderer,
)
from litlaunch.launcher import StreamlitLauncher
from litlaunch.monitored import run_profile
from litlaunch.platforms import PlatformDetector
from litlaunch.profiles import LaunchProfile, load_profile
from litlaunch.version import __version__
from litlaunch.windowing import (
    WindowMonitorConfig,
    WindowMonitorResult,
    create_window_monitor,
)


@dataclass(frozen=True)
class _CliContext:
    stream: TextIO
    env: Mapping[str, str]
    platform_detector_factory: Any
    browser_registry_factory: Any
    launcher_factory: Any
    diagnostic_collector_factory: Any
    window_monitor_factory: Any


@dataclass(frozen=True)
class _MonitorOptions:
    enabled: bool
    graceful_timeout_seconds: float
    window_monitor_config: WindowMonitorConfig


def build_parser() -> argparse.ArgumentParser:
    """Build the LitLaunch argparse parser."""

    parent = argparse.ArgumentParser(add_help=False)
    _add_global_flags(parent)

    parser = argparse.ArgumentParser(
        prog="litlaunch",
        description="Lightweight Streamlit launcher/runtime tooling.",
        parents=[parent],
    )
    subparsers = parser.add_subparsers(dest="command")

    version_parser = subparsers.add_parser(
        "version",
        parents=[parent],
        help="Show the LitLaunch version.",
    )
    version_parser.set_defaults(handler=_cmd_version)

    platform_parser = subparsers.add_parser(
        "platform",
        parents=[parent],
        help="Show normalized platform capability information.",
    )
    platform_parser.set_defaults(handler=_cmd_platform)

    browsers_parser = subparsers.add_parser(
        "browsers",
        parents=[parent],
        help="Show detected browser launch capabilities.",
    )
    browsers_parser.set_defaults(handler=_cmd_browsers)

    inspect_parser = subparsers.add_parser(
        "inspect",
        parents=[parent],
        help="Inspect local LitLaunch and Streamlit runtime readiness.",
    )
    _add_inspect_flags(inspect_parser)
    inspect_parser.set_defaults(handler=_cmd_inspect)

    command_parser = subparsers.add_parser(
        "command",
        parents=[parent],
        help="Print the Streamlit backend command without launching it.",
    )
    _add_runtime_flags(command_parser, include_dry_run=False)
    command_parser.set_defaults(handler=_cmd_command)

    run_parser = subparsers.add_parser(
        "run",
        parents=[parent],
        help="Run a Streamlit app with LitLaunch.",
    )
    _add_runtime_flags(run_parser, include_dry_run=True)
    run_parser.set_defaults(handler=_cmd_run)

    example_parser = subparsers.add_parser(
        "example",
        parents=[parent],
        help="Show the source-checkout minimal example app path.",
    )
    example_parser.set_defaults(handler=_cmd_example)

    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stream: TextIO | None = None,
    env: Mapping[str, str] | None = None,
    platform_detector_factory: Any = PlatformDetector,
    browser_registry_factory: Any = create_default_browser_registry,
    launcher_factory: Any = StreamlitLauncher,
    diagnostic_collector_factory: Any = DiagnosticCollector,
    window_monitor_factory: Any = create_window_monitor,
) -> int:
    """Run the LitLaunch CLI."""

    output = stream if stream is not None else sys.stdout
    resolved_env = env if env is not None else os.environ
    parser = build_parser()
    args, extra_args = parser.parse_known_args(argv)
    if not hasattr(args, "handler"):
        if extra_args:
            parser.error(f"unrecognized arguments: {' '.join(extra_args)}")
        parser.print_help(file=output)
        return 0
    if extra_args and args.command not in {"run", "command"}:
        parser.error(f"unrecognized arguments: {' '.join(extra_args)}")
    args.passthrough_args = tuple(extra_args)

    context = _CliContext(
        stream=output,
        env=resolved_env,
        platform_detector_factory=platform_detector_factory,
        browser_registry_factory=browser_registry_factory,
        launcher_factory=launcher_factory,
        diagnostic_collector_factory=diagnostic_collector_factory,
        window_monitor_factory=window_monitor_factory,
    )
    try:
        return int(args.handler(args, context))
    except LitLaunchError as exc:
        _renderer(args, context).error(str(exc))
        return 2
    except Exception as exc:
        _renderer(args, context).error(str(exc))
        return 1


def _cmd_version(args: argparse.Namespace, context: _CliContext) -> int:
    _write(context.stream, f"LitLaunch {__version__}")
    return 0


def _cmd_platform(args: argparse.Namespace, context: _CliContext) -> int:
    renderer = _renderer(args, context)
    info = context.platform_detector_factory().detect()
    renderer.info(info.summary())
    if _mode(args) == ConsoleMode.VERBOSE:
        details = info.as_dict()
        for key in sorted(details):
            renderer.detail(f"{key}: {details[key]}")
    return 0


def _cmd_browsers(args: argparse.Namespace, context: _CliContext) -> int:
    renderer = _renderer(args, context)
    platform_info = context.platform_detector_factory().detect()
    registry = context.browser_registry_factory()
    capabilities = registry.detect_all(platform_info)
    renderer.info("Browser capabilities")
    for capability in capabilities:
        availability = "available" if capability.available else "unavailable"
        app_mode = "app-mode" if capability.supports_app_mode else "full-browser-only"
        renderer.step(f"{capability.name}: {availability}, {app_mode}")
        if _mode(args) == ConsoleMode.VERBOSE:
            renderer.detail(f"kind: {capability.kind.value}")
            renderer.detail(f"executable_path: {capability.executable_path or ''}")
            for note in capability.notes:
                renderer.detail(f"note: {note}")

    resolution = registry.resolve(
        BrowserChoice.AUTO,
        platform_info,
        prefer_app_mode=True,
    )
    renderer.info(f"Auto app-mode strategy: {resolution.message}")
    return 0


def _cmd_inspect(args: argparse.Namespace, context: _CliContext) -> int:
    _validate_inspect_output_args(args)
    profile = _load_cli_profile(args)
    profile_config = profile.config if profile is not None else None
    collector = context.diagnostic_collector_factory(
        platform_detector=context.platform_detector_factory(),
        browser_registry=context.browser_registry_factory(),
        launcher_factory=context.launcher_factory,
    )
    report = collector.collect(
        app_path=(
            args.app_path
            if args.app_path is not None
            else profile_config.app_path
            if profile_config is not None
            else None
        ),
        mode=_profile_value(args.mode, profile_config, "mode", LaunchMode.BROWSER),
        browser=_profile_value(
            args.browser,
            profile_config,
            "browser",
            BrowserChoice.AUTO,
        ),
        host=_profile_value(args.host, profile_config, "host", "127.0.0.1"),
        port=_profile_value(args.port, profile_config, "port", None),
        auto_port=_profile_value(args.auto_port, profile_config, "auto_port", True),
        allow_browser_fallback=_profile_value(
            args.allow_browser_fallback,
            profile_config,
            "allow_browser_fallback",
            True,
        ),
        cwd=profile_config.cwd if profile_config is not None else None,
        extra_env=profile_config.extra_env if profile_config is not None else None,
        streamlit_flags=(
            profile_config.streamlit_flags if profile_config is not None else None
        ),
        streamlit_args=(
            profile_config.streamlit_args if profile_config is not None else ()
        ),
        app_args=profile_config.app_args if profile_config is not None else (),
        profile_name=profile.name if profile is not None else None,
        monitor_window=profile.monitor_window if profile is not None else None,
        graceful_timeout_seconds=(
            profile.graceful_timeout_seconds if profile is not None else None
        ),
        window_monitor_config=(
            profile.window_monitor_config if profile is not None else None
        ),
    )
    if args.json:
        rendered = JSONDiagnosticsRenderer().render(report)
    elif args.html:
        rendered = HTMLDiagnosticsRenderer(
            include_details=_mode(args) == ConsoleMode.VERBOSE
        ).render(report)
    elif args.bundle:
        rendered = SanitizedBundleRenderer(
            include_details=_mode(args) == ConsoleMode.VERBOSE
        ).render(report)
    else:
        rendered = TextDiagnosticsRenderer(
            include_details=_mode(args) == ConsoleMode.VERBOSE
        ).render(report)

    if args.output:
        output_path = _write_inspect_output(
            Path(args.output),
            rendered,
            force=args.force,
        )
        _write(context.stream, f"Wrote inspect report to {output_path}")
    else:
        context.stream.write(rendered)
        flush = getattr(context.stream, "flush", None)
        if callable(flush):
            flush()
    return 0 if report.ok else 1


def _cmd_command(args: argparse.Namespace, context: _CliContext) -> int:
    renderer = _renderer(args, context)
    profile = _load_cli_profile(args)
    config = _runtime_config_from_args(args, profile=profile)
    launcher = context.launcher_factory(config, console_renderer=renderer)
    plan = launcher.build_launch_plan(include_browser_resolution=False)
    _write(context.stream, plan.command_display)
    return 0


def _cmd_run(args: argparse.Namespace, context: _CliContext) -> int:
    renderer = _renderer(args, context)
    profile = _load_cli_profile(args)
    config = _runtime_config_from_args(args, profile=profile)
    monitor_options = _monitor_options_from_args(args, profile)
    if monitor_options.enabled and config.mode != LaunchMode.WEBAPP:
        raise LitLaunchError("--monitor-window is only valid with --mode webapp.")
    launcher = context.launcher_factory(config, console_renderer=renderer)
    if args.dry_run:
        plan = launcher.build_launch_plan()
        renderer.info("Dry run: backend and browser were not started.")
        renderer.info(f"App URL: {plan.app_url}")
        renderer.info(f"Mode: {config.mode.value}")
        if plan.browser_resolution is not None:
            renderer.info(f"Browser: {plan.browser_resolution.message}")
        _write(context.stream, plan.command_display)
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
        platform_detector=context.platform_detector_factory(),
        window_monitor_factory=context.window_monitor_factory,
    )

    if monitor_options.enabled:
        if run_result.session is not None and run_result.session.ok:
            renderer.success(f"Runtime active at {run_result.session.url}")
        if run_result.monitor_result is not None:
            _render_monitor_result_if_needed(
                run_result.session,
                renderer,
                run_result.monitor_result,
            )
        if not run_result.launched:
            renderer.failure_guidance(
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
            renderer.failure_guidance(run_result.message)
        return run_result.exit_code

    session = run_result.session
    if session is None:
        renderer.failure_guidance(run_result.message)
        return run_result.exit_code
    if not session.ok:
        renderer.failure_guidance(
            "Runtime launch failed.",
            likely_cause=session.result.message,
            next_steps=(
                "Run the app directly with streamlit run to compare behavior.",
            ),
            suggest_inspect=True,
        )
        return 1

    renderer.success(f"Runtime active at {session.url}")
    if session.process is None:
        return 0

    try:
        returncode = session.wait()
    except KeyboardInterrupt:
        renderer.warning("Interrupt received; stopping runtime.")
        session.stop()
        return 0

    return int(returncode or 0)


def _cmd_example(args: argparse.Namespace, context: _CliContext) -> int:
    example_path = _source_checkout_example_path(Path(__file__))
    if not example_path.is_file():
        _renderer(args, context).error(
            "The minimal example app is available from a LitLaunch source checkout. "
            "Install from source or clone the repository to run it."
        )
        return 1
    _write(context.stream, str(example_path))
    _renderer(args, context).detail(f"Run with: litlaunch run {example_path}")
    return 0


def _add_global_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--quiet", action="store_true", help="Suppress normal output.")
    group.add_argument("--verbose", action="store_true", help="Show detailed output.")


def _add_runtime_flags(
    parser: argparse.ArgumentParser,
    *,
    include_dry_run: bool,
) -> None:
    parser.add_argument("app_path", nargs="?")
    _add_profile_flags(parser)
    parser.add_argument(
        "--title",
        help="Set the runtime title used for browser/app-mode window matching.",
    )
    parser.add_argument("--mode", choices=[item.value for item in LaunchMode])
    parser.add_argument("--browser", choices=[item.value for item in BrowserChoice])
    parser.add_argument("--port", type=int)
    parser.add_argument("--host")
    parser.add_argument(
        "--no-auto-port",
        action="store_false",
        dest="auto_port",
        default=None,
        help="Fail if the requested port is unavailable instead of trying another.",
    )
    if include_dry_run:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the resolved Streamlit command without starting runtime.",
        )
        parser.add_argument(
            "--monitor-window",
            action="store_true",
            default=None,
            help="Monitor the Chromium app-mode window and stop runtime on close.",
        )
        parser.add_argument(
            "--graceful-timeout",
            type=float,
            help=(
                "Seconds to wait for graceful app shutdown after monitored "
                "window close."
            ),
        )
        parser.add_argument(
            "--monitor-appear-timeout",
            type=float,
            help="Seconds to wait for the app-mode window to appear.",
        )
        parser.add_argument(
            "--monitor-poll-interval",
            type=float,
            help="Seconds between window monitor polls.",
        )
        parser.add_argument(
            "--monitor-stable-polls",
            type=int,
            help="Matching polls required before a window is considered stable.",
        )
    parser.add_argument(
        "--no-browser-fallback",
        action="store_false",
        dest="allow_browser_fallback",
        default=None,
        help="Disable browser fallback when the requested browser is unavailable.",
    )
    parser.add_argument(
        "--streamlit-flag",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        type=_parse_streamlit_flag,
        help="Add a Streamlit flag. Repeatable.",
    )
    parser.add_argument(
        "--app-arg",
        action="append",
        default=[],
        help="Add an app argument after Streamlit's -- separator. Repeatable.",
    )


def _add_inspect_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("app_path", nargs="?")
    _add_profile_flags(parser)
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--json",
        action="store_true",
        help="Render diagnostics as machine-readable JSON.",
    )
    output_group.add_argument(
        "--bundle",
        action="store_true",
        help="Render a sanitized copyable support bundle.",
    )
    output_group.add_argument(
        "--html",
        action="store_true",
        help="Render a sanitized standalone HTML diagnostics report.",
    )
    parser.add_argument("--mode", choices=[item.value for item in LaunchMode])
    parser.add_argument("--browser", choices=[item.value for item in BrowserChoice])
    parser.add_argument("--port", type=int)
    parser.add_argument("--host")
    parser.add_argument(
        "--no-auto-port",
        action="store_false",
        dest="auto_port",
        default=None,
        help="Fail if the requested port is unavailable instead of trying another.",
    )
    parser.add_argument(
        "--no-browser-fallback",
        action="store_false",
        dest="allow_browser_fallback",
        default=None,
        help="Disable browser fallback when the requested browser is unavailable.",
    )
    parser.add_argument(
        "--output",
        help="Write JSON or bundle inspect output to a UTF-8 file.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing inspect output file.",
    )


def _add_profile_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", help="Load a named LitLaunch launch profile.")
    parser.add_argument(
        "--config",
        dest="config_path",
        help="Load profiles from an explicit litlaunch.toml or pyproject.toml file.",
    )


def _renderer(args: argparse.Namespace, context: _CliContext) -> ConsoleRenderer:
    use_color = (
        not bool(getattr(args, "no_color", False)) and "NO_COLOR" not in context.env
    )
    return ConsoleRenderer(
        mode=_mode(args),
        theme=ConsoleTheme(use_color=use_color),
        stream=context.stream,
        env=context.env,
    )


def _mode(args: argparse.Namespace) -> ConsoleMode:
    if getattr(args, "quiet", False):
        return ConsoleMode.QUIET
    if getattr(args, "verbose", False):
        return ConsoleMode.VERBOSE
    return ConsoleMode.NORMAL


def _parse_streamlit_flag(value: str) -> tuple[str, str | None]:
    key, separator, flag_value = value.partition("=")
    key = key.strip()
    if not key:
        raise argparse.ArgumentTypeError("streamlit flag key cannot be empty.")
    return key, flag_value if separator else None


def _streamlit_flags_mapping(
    values: Sequence[tuple[str, str | None]],
) -> dict[str, str | None]:
    return {key: value for key, value in values}


def _runtime_config_from_args(
    args: argparse.Namespace,
    *,
    profile: LaunchProfile | None = None,
) -> LauncherConfig:
    profile_config = profile.config if profile is not None else None
    app_path_value = (
        args.app_path
        if args.app_path is not None
        else profile_config.app_path
        if profile_config is not None
        else None
    )
    if app_path_value is None:
        raise LitLaunchError("app_path is required unless --profile supplies one.")

    app_path = Path(app_path_value)
    if not app_path.is_file():
        raise LitLaunchError(f"Streamlit app path does not exist: {app_path}")

    streamlit_args, app_args = _split_passthrough_args(args.passthrough_args)
    config = LauncherConfig(
        app_path=app_path,
        title=_profile_value(args.title, profile_config, "title", "Streamlit App"),
        mode=_profile_value(args.mode, profile_config, "mode", LaunchMode.BROWSER),
        browser=_profile_value(
            args.browser,
            profile_config,
            "browser",
            BrowserChoice.AUTO,
        ),
        host=_profile_value(args.host, profile_config, "host", "127.0.0.1"),
        port=_profile_value(args.port, profile_config, "port", None),
        auto_port=_profile_value(args.auto_port, profile_config, "auto_port", True),
        headless=_profile_value(None, profile_config, "headless", None),
        allow_browser_fallback=_profile_value(
            args.allow_browser_fallback,
            profile_config,
            "allow_browser_fallback",
            True,
        ),
        cwd=profile_config.cwd if profile_config is not None else None,
        extra_env=profile_config.extra_env if profile_config is not None else {},
        streamlit_flags=_merge_streamlit_flags(
            profile_config.streamlit_flags if profile_config is not None else {},
            args.streamlit_flag,
        ),
        streamlit_args=(
            *(profile_config.streamlit_args if profile_config is not None else ()),
            *streamlit_args,
        ),
        app_args=(
            *(profile_config.app_args if profile_config is not None else ()),
            *tuple(args.app_arg),
            *app_args,
        ),
        extra_browser_args=(
            profile_config.extra_browser_args if profile_config is not None else ()
        ),
    )
    return config


def _monitor_options_from_args(
    args: argparse.Namespace,
    profile: LaunchProfile | None,
) -> _MonitorOptions:
    profile_monitor_config = (
        profile.window_monitor_config if profile is not None else WindowMonitorConfig()
    )
    monitor_window = (
        args.monitor_window
        if getattr(args, "monitor_window", None) is not None
        else profile.monitor_window
        if profile is not None
        else False
    )
    graceful_timeout = (
        args.graceful_timeout
        if getattr(args, "graceful_timeout", None) is not None
        else profile.graceful_timeout_seconds
        if profile is not None
        else 3.0
    )
    appear_timeout = (
        args.monitor_appear_timeout
        if getattr(args, "monitor_appear_timeout", None) is not None
        else profile_monitor_config.appear_timeout_seconds
    )
    poll_interval = (
        args.monitor_poll_interval
        if getattr(args, "monitor_poll_interval", None) is not None
        else profile_monitor_config.poll_interval_seconds
    )
    stable_polls = (
        args.monitor_stable_polls
        if getattr(args, "monitor_stable_polls", None) is not None
        else profile_monitor_config.stable_poll_count
    )
    if graceful_timeout <= 0:
        raise LitLaunchError("--graceful-timeout must be positive.")
    if appear_timeout <= 0:
        raise LitLaunchError("--monitor-appear-timeout must be positive.")
    if poll_interval <= 0:
        raise LitLaunchError("--monitor-poll-interval must be positive.")
    if stable_polls < 1:
        raise LitLaunchError("--monitor-stable-polls must be at least 1.")
    return _MonitorOptions(
        enabled=bool(monitor_window),
        graceful_timeout_seconds=float(graceful_timeout),
        window_monitor_config=WindowMonitorConfig(
            appear_timeout_seconds=float(appear_timeout),
            poll_interval_seconds=float(poll_interval),
            stable_poll_count=int(stable_polls),
        ),
    )


def _load_cli_profile(args: argparse.Namespace) -> LaunchProfile | None:
    config_path = getattr(args, "config_path", None)
    profile_name = getattr(args, "profile", None)
    if config_path and not profile_name:
        raise LitLaunchError("--config requires --profile.")
    if not profile_name:
        return None
    return load_profile(profile_name, config_path)


def _profile_value(value, profile_config, field_name: str, default):
    if value is not None:
        return value
    if profile_config is not None:
        return getattr(profile_config, field_name)
    return default


def _merge_streamlit_flags(profile_flags, cli_values):
    cli_flags = _streamlit_flags_mapping(cli_values)
    if not cli_flags:
        return profile_flags
    if isinstance(profile_flags, Mapping):
        return {**dict(profile_flags), **cli_flags}
    formatted: list[str] = [str(item) for item in profile_flags]
    for key, value in cli_flags.items():
        formatted.append(key if str(key).startswith("--") else f"--{key}")
        if value is not None:
            formatted.append(value)
    return tuple(formatted)


def _render_monitor_result_if_needed(
    session: Any | None,
    renderer: ConsoleRenderer,
    result: WindowMonitorResult,
) -> None:
    if session is None or getattr(session, "console_renderer", None) is None:
        renderer.render_window_monitor_result(result)


def _validate_inspect_output_args(args: argparse.Namespace) -> None:
    if args.output and not (args.json or args.bundle or args.html):
        raise LitLaunchError("--output requires --json, --bundle, or --html.")
    if args.force and not args.output:
        raise LitLaunchError("--force requires --output.")


def _write_inspect_output(path: Path, rendered: str, *, force: bool) -> Path:
    output_path = path.expanduser()
    parent = output_path.parent
    if parent and not parent.exists():
        raise LitLaunchError(f"Output parent directory does not exist: {parent}")
    if output_path.exists() and output_path.is_dir():
        raise LitLaunchError(f"Output path is a directory: {output_path}")
    if output_path.exists() and not force:
        raise LitLaunchError(
            f"Output file already exists: {output_path}. Use --force to overwrite."
        )
    try:
        output_path.write_text(rendered, encoding="utf-8")
    except OSError as exc:
        message = f"Could not write output file {output_path}: {exc}"
        raise LitLaunchError(message) from exc
    return output_path


def _split_passthrough_args(
    values: Sequence[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    items = tuple(str(value) for value in values)
    if "--" not in items:
        return items, ()
    separator_index = items.index("--")
    return items[:separator_index], items[separator_index + 1 :]


def _write(stream: TextIO, message: str) -> None:
    stream.write(f"{message}\n")
    flush = getattr(stream, "flush", None)
    if callable(flush):
        flush()


def _source_checkout_example_path(module_path: Path) -> Path:
    return module_path.resolve().parents[2] / "examples" / "minimal_app" / "app.py"


if __name__ == "__main__":
    raise SystemExit(main())
