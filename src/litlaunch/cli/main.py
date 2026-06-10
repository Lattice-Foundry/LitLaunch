"""Command-line interface for LitLaunch."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, TextIO

from litlaunch.cli.commands import (
    cmd_browsers,
    cmd_command,
    cmd_platform,
    cmd_run,
    cmd_version,
)
from litlaunch.cli.common import (
    CliContext,
    build_context,
    renderer,
    source_checkout_example_path,
    write,
)
from litlaunch.cli.config import add_runtime_flags
from litlaunch.cli.create import add_create_flags, cmd_create
from litlaunch.cli.help import add_workflow_help_flags, cmd_workflow_help
from litlaunch.cli.inspect import (
    add_inspect_flags,
    add_report_flags,
    cmd_inspect,
    cmd_report,
)
from litlaunch.cli.preview import add_console_preview_flags, cmd_console_preview
from litlaunch.console_style import (
    apply_argparse_help_formatter_colors,
    configure_argparse_help_colors,
)
from litlaunch.exceptions import LitLaunchError

_COMMAND_NAMES = frozenset(
    {
        "version",
        "platform",
        "browsers",
        "help",
        "inspect",
        "report",
        "command",
        "run",
        "create",
        "example",
        "console-preview",
    }
)
_LAUNCH_OPTION_NAMES = frozenset(
    {
        "--profile",
        "--config",
        "--title",
        "--mode",
        "--browser",
        "--trust-mode",
        "--port",
        "--host",
        "--show-streamlit-chrome",
        "--no-auto-port",
        "--dry-run",
        "--monitor-window",
        "--no-monitor-window",
        "--graceful-timeout",
        "--monitor-appear-timeout",
        "--monitor-poll-interval",
        "--monitor-stable-polls",
        "--monitor-browser-window",
        "--no-monitor-browser-window",
        "--no-browser-fallback",
        "--allow-network-exposure",
        "--streamlit-flag",
        "--app-arg",
        "--browser-arg",
        "--event-log",
    }
)
_GLOBAL_FLAG_NAMES = frozenset({"--no-color", "--quiet", "--verbose", "-h", "--help"})


class LitLaunchHelpFormatter(argparse.HelpFormatter):
    """Argparse help formatter with LitLaunch's green metavar accent."""

    def add_arguments(self, actions: Iterable[argparse.Action]) -> None:
        visible_actions = [
            action for action in actions if action.help != argparse.SUPPRESS
        ]
        super().add_arguments(visible_actions)

    def _set_color(self, color: Any) -> None:
        set_color = getattr(super(), "_set_color", None)
        if set_color is not None:
            set_color(color)
        apply_argparse_help_formatter_colors(self)


def build_parser() -> argparse.ArgumentParser:
    """Build the LitLaunch argparse parser."""

    configure_argparse_help_colors()
    parent = argparse.ArgumentParser(
        add_help=False,
        formatter_class=LitLaunchHelpFormatter,
    )
    _add_global_flags(parent)

    parser = argparse.ArgumentParser(
        prog="litlaunch",
        description="Lightweight Streamlit launcher/runtime tooling.",
        epilog=(
            "Common workflows: litlaunch app.py --mode webapp | "
            "litlaunch --profile my-webapp | litlaunch report --profile my-webapp"
        ),
        parents=[parent],
        formatter_class=LitLaunchHelpFormatter,
    )
    subparsers = parser.add_subparsers(
        dest="command",
        metavar=(
            "{version,platform,browsers,help,inspect,report,command,run,create,example}"
        ),
    )

    version_parser = subparsers.add_parser(
        "version",
        parents=[parent],
        help="Show the LitLaunch version.",
        formatter_class=LitLaunchHelpFormatter,
    )
    version_parser.set_defaults(handler=cmd_version)

    platform_parser = subparsers.add_parser(
        "platform",
        parents=[parent],
        help="Show normalized platform capability information.",
        formatter_class=LitLaunchHelpFormatter,
    )
    platform_parser.set_defaults(handler=cmd_platform)

    browsers_parser = subparsers.add_parser(
        "browsers",
        parents=[parent],
        help="Show detected browser launch capabilities.",
        formatter_class=LitLaunchHelpFormatter,
    )
    browsers_parser.set_defaults(handler=cmd_browsers)

    help_parser = subparsers.add_parser(
        "help",
        parents=[parent],
        help="Show workflow-oriented guidance.",
        formatter_class=LitLaunchHelpFormatter,
    )
    add_workflow_help_flags(help_parser)
    help_parser.set_defaults(handler=cmd_workflow_help)

    inspect_parser = subparsers.add_parser(
        "inspect",
        parents=[parent],
        help="Inspect local LitLaunch and Streamlit runtime readiness.",
        formatter_class=LitLaunchHelpFormatter,
    )
    add_inspect_flags(inspect_parser)
    inspect_parser.set_defaults(handler=cmd_inspect)

    report_parser = subparsers.add_parser(
        "report",
        parents=[parent],
        help="Generate a standalone HTML diagnostics report.",
        formatter_class=LitLaunchHelpFormatter,
    )
    add_report_flags(report_parser)
    report_parser.set_defaults(handler=cmd_report)

    command_parser = subparsers.add_parser(
        "command",
        parents=[parent],
        help="Print the Streamlit backend command without launching it.",
        formatter_class=LitLaunchHelpFormatter,
    )
    add_runtime_flags(command_parser, include_dry_run=False)
    command_parser.set_defaults(handler=cmd_command)

    run_parser = subparsers.add_parser(
        "run",
        parents=[parent],
        help="Run a Streamlit app with LitLaunch.",
        formatter_class=LitLaunchHelpFormatter,
    )
    add_runtime_flags(run_parser, include_dry_run=True)
    run_parser.set_defaults(handler=cmd_run)

    create_parser = subparsers.add_parser(
        "create",
        parents=[parent],
        help="Create LitLaunch project assets.",
        formatter_class=LitLaunchHelpFormatter,
    )
    add_create_flags(create_parser)
    create_parser.set_defaults(handler=cmd_create)

    example_parser = subparsers.add_parser(
        "example",
        parents=[parent],
        help="Show the source-checkout minimal example app path.",
        formatter_class=LitLaunchHelpFormatter,
    )
    example_parser.set_defaults(handler=_cmd_example)

    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stream: TextIO | None = None,
    env: Mapping[str, str] | None = None,
    platform_detector_factory: Any = None,
    browser_registry_factory: Any = None,
    launcher_factory: Any = None,
    diagnostic_collector_factory: Any = None,
    window_monitor_factory: Any = None,
) -> int:
    """Run the LitLaunch CLI."""

    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = (
        build_console_preview_parser()
        if _is_console_preview_invocation(raw_argv)
        else build_parser()
    )
    normalized_argv = _normalize_launch_shorthand(raw_argv)
    args, extra_args = parser.parse_known_args(normalized_argv)
    if not hasattr(args, "handler"):
        if extra_args:
            parser.error(f"unrecognized arguments: {' '.join(extra_args)}")
        context = build_context(stream=stream, env=env)
        parser.print_help(file=context.stream)
        return 0
    if extra_args and args.command not in {"run", "command"}:
        parser.error(f"unrecognized arguments: {' '.join(extra_args)}")
    args.passthrough_args = tuple(extra_args)

    context = build_context(
        stream=stream,
        env=env,
        **_factory_overrides(
            platform_detector_factory=platform_detector_factory,
            browser_registry_factory=browser_registry_factory,
            launcher_factory=launcher_factory,
            diagnostic_collector_factory=diagnostic_collector_factory,
            window_monitor_factory=window_monitor_factory,
        ),
    )
    try:
        return int(args.handler(args, context))
    except LitLaunchError as exc:
        renderer(args, context).error(str(exc))
        return 2
    except Exception as exc:
        renderer(args, context).error(str(exc))
        return 1


def _add_global_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--quiet", action="store_true", help="Suppress normal output.")
    group.add_argument("--verbose", action="store_true", help="Show detailed output.")


def build_console_preview_parser() -> argparse.ArgumentParser:
    """Build the hidden internal console-preview parser."""

    configure_argparse_help_colors()
    parent = argparse.ArgumentParser(
        add_help=False,
        formatter_class=LitLaunchHelpFormatter,
    )
    _add_global_flags(parent)
    parser = argparse.ArgumentParser(
        prog="litlaunch",
        parents=[parent],
        formatter_class=LitLaunchHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")
    console_preview_parser = subparsers.add_parser(
        "console-preview",
        formatter_class=LitLaunchHelpFormatter,
    )
    add_console_preview_flags(console_preview_parser)
    console_preview_parser.set_defaults(handler=cmd_console_preview)
    return parser


def _normalize_launch_shorthand(argv: Sequence[str]) -> list[str]:
    """Route root launch shorthand through the explicit ``run`` command."""

    args = list(argv)
    if not args:
        return args
    if args == ["--help"] or args == ["-h"]:
        return args
    first_token = _first_non_option_token(args)
    if first_token in _COMMAND_NAMES:
        return args
    if _has_root_launch_option(args) or _has_root_app_path_launch(args):
        return ["run", *args]
    return args


def _is_console_preview_invocation(args: Sequence[str]) -> bool:
    for token in args:
        if token in _GLOBAL_FLAG_NAMES:
            continue
        if token.startswith("-"):
            return False
        return token == "console-preview"
    return False


def _has_root_launch_option(args: Sequence[str]) -> bool:
    return any(token.partition("=")[0] in _LAUNCH_OPTION_NAMES for token in args)


def _has_root_app_path_launch(args: Sequence[str]) -> bool:
    token = _first_non_option_token(args)
    if token is None or token in _COMMAND_NAMES:
        return False
    return _looks_like_app_path(token)


def _first_non_option_token(args: Sequence[str]) -> str | None:
    for token in args:
        if token == "--":
            return None
        if token.startswith("-"):
            continue
        return token
    return None


def _looks_like_app_path(token: str) -> bool:
    if token.startswith("-"):
        return False
    path = Path(token)
    return (
        path.is_file()
        or path.suffix.lower() == ".py"
        or "/" in token
        or "\\" in token
        or (len(token) > 1 and token[1] == ":")
    )


def _factory_overrides(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _cmd_example(args: argparse.Namespace, context: CliContext) -> int:
    example_path = source_checkout_example_path(Path(__file__).parent)
    if not example_path.is_file():
        renderer(args, context).error(
            "The minimal example app is available from a LitLaunch source checkout. "
            "Install from source or clone the repository to run it."
        )
        return 1
    write(context.stream, str(example_path))
    renderer(args, context).detail(f"Run with: litlaunch run {example_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
