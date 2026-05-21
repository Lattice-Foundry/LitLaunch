"""Command-line interface for LitLaunch."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
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
    build_context,
    renderer,
    source_checkout_example_path,
    write,
)
from litlaunch.cli.config import add_runtime_flags
from litlaunch.cli.inspect import add_inspect_flags, cmd_inspect
from litlaunch.cli.test import cmd_console_preview
from litlaunch.exceptions import LitLaunchError

_source_checkout_example_path = source_checkout_example_path


def build_parser() -> argparse.ArgumentParser:
    """Build the LitLaunch argparse parser."""

    parent = argparse.ArgumentParser(add_help=False)
    _add_global_flags(parent)

    parser = argparse.ArgumentParser(
        prog="litlaunch",
        description="Lightweight Streamlit launcher/runtime tooling.",
        parents=[parent],
    )
    subparsers = parser.add_subparsers(
        dest="command",
        metavar="{version,platform,browsers,inspect,command,run,example}",
    )

    version_parser = subparsers.add_parser(
        "version",
        parents=[parent],
        help="Show the LitLaunch version.",
    )
    version_parser.set_defaults(handler=cmd_version)

    platform_parser = subparsers.add_parser(
        "platform",
        parents=[parent],
        help="Show normalized platform capability information.",
    )
    platform_parser.set_defaults(handler=cmd_platform)

    browsers_parser = subparsers.add_parser(
        "browsers",
        parents=[parent],
        help="Show detected browser launch capabilities.",
    )
    browsers_parser.set_defaults(handler=cmd_browsers)

    inspect_parser = subparsers.add_parser(
        "inspect",
        parents=[parent],
        help="Inspect local LitLaunch and Streamlit runtime readiness.",
    )
    add_inspect_flags(inspect_parser)
    inspect_parser.set_defaults(handler=cmd_inspect)

    command_parser = subparsers.add_parser(
        "command",
        parents=[parent],
        help="Print the Streamlit backend command without launching it.",
    )
    add_runtime_flags(command_parser, include_dry_run=False)
    command_parser.set_defaults(handler=cmd_command)

    run_parser = subparsers.add_parser(
        "run",
        parents=[parent],
        help="Run a Streamlit app with LitLaunch.",
    )
    add_runtime_flags(run_parser, include_dry_run=True)
    run_parser.set_defaults(handler=cmd_run)

    example_parser = subparsers.add_parser(
        "example",
        parents=[parent],
        help="Show the source-checkout minimal example app path.",
    )
    example_parser.set_defaults(handler=_cmd_example)

    # TEMP TEST: beta-only console design preview hook. Delete when the runtime
    # terminal language is stable enough to remove the dev preview command.
    for preview_command in (
        "console-preview",
        "console-preview-norm",
        "console-preview-verb",
    ):
        console_preview_parser = subparsers.add_parser(
            preview_command,
            parents=[parent],
            help=argparse.SUPPRESS,
        )
        console_preview_parser.set_defaults(handler=cmd_console_preview)
    subparsers._choices_actions = [  # type: ignore[attr-defined]  # TEMP TEST
        action
        for action in subparsers._choices_actions  # type: ignore[attr-defined]
        if not action.dest.startswith("console-preview")
    ]

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

    parser = build_parser()
    args, extra_args = parser.parse_known_args(argv)
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


def _factory_overrides(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _cmd_example(args: argparse.Namespace, context) -> int:
    example_path = _source_checkout_example_path(Path(__file__).parent)
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
