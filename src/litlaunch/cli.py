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
from litlaunch.launcher import StreamlitLauncher
from litlaunch.platforms import PlatformDetector
from litlaunch.version import __version__


@dataclass(frozen=True)
class _CliContext:
    stream: TextIO
    env: Mapping[str, str]
    platform_detector_factory: Any
    browser_registry_factory: Any
    launcher_factory: Any


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

    run_parser = subparsers.add_parser(
        "run",
        parents=[parent],
        help="Run a Streamlit app with LitLaunch.",
    )
    run_parser.add_argument("app_path")
    run_parser.add_argument("--mode", choices=[item.value for item in LaunchMode])
    run_parser.add_argument("--browser", choices=[item.value for item in BrowserChoice])
    run_parser.add_argument("--port", type=int)
    run_parser.add_argument("--host", default="127.0.0.1")
    run_parser.add_argument(
        "--no-browser-fallback",
        action="store_true",
        help="Disable browser fallback when the requested browser is unavailable.",
    )
    run_parser.add_argument(
        "--streamlit-flag",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        type=_parse_streamlit_flag,
        help="Add a Streamlit flag. Repeatable.",
    )
    run_parser.add_argument(
        "--app-arg",
        action="append",
        default=[],
        help="Add an app argument after Streamlit's -- separator. Repeatable.",
    )
    run_parser.set_defaults(handler=_cmd_run)

    example_parser = subparsers.add_parser(
        "example",
        parents=[parent],
        help="Show the bundled minimal example app path.",
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
) -> int:
    """Run the LitLaunch CLI."""

    output = stream if stream is not None else sys.stdout
    resolved_env = env if env is not None else os.environ
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help(file=output)
        return 0

    context = _CliContext(
        stream=output,
        env=resolved_env,
        platform_detector_factory=platform_detector_factory,
        browser_registry_factory=browser_registry_factory,
        launcher_factory=launcher_factory,
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


def _cmd_run(args: argparse.Namespace, context: _CliContext) -> int:
    renderer = _renderer(args, context)
    app_path = Path(args.app_path)
    if not app_path.is_file():
        renderer.error(f"Streamlit app path does not exist: {app_path}")
        return 2

    config = LauncherConfig(
        app_path=app_path,
        mode=args.mode or LaunchMode.BROWSER,
        browser=args.browser or BrowserChoice.AUTO,
        host=args.host,
        port=args.port,
        allow_browser_fallback=not args.no_browser_fallback,
        streamlit_flags=_streamlit_flags_mapping(args.streamlit_flag),
        app_args=tuple(args.app_arg),
    )
    launcher = context.launcher_factory(config, console_renderer=renderer)
    session = launcher.run()
    if not session.ok:
        renderer.error(session.result.message)
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


def _write(stream: TextIO, message: str) -> None:
    stream.write(f"{message}\n")
    flush = getattr(stream, "flush", None)
    if callable(flush):
        flush()


def _source_checkout_example_path(module_path: Path) -> Path:
    return module_path.resolve().parents[2] / "examples" / "minimal_app" / "app.py"


if __name__ == "__main__":
    raise SystemExit(main())
