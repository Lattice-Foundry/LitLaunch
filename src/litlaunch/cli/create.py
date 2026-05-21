"""Creation-oriented CLI commands."""

from __future__ import annotations

import argparse

from litlaunch.cli.common import CliContext
from litlaunch.profile_wizard import (
    ProfileWizardCancelled,
    ProfileWizardOptions,
    run_profile_wizard,
)


def add_create_flags(parser: argparse.ArgumentParser) -> None:
    """Add the ``create`` command namespace."""

    subparsers = parser.add_subparsers(
        dest="create_command",
        metavar="{profile}",
    )
    profile_parser = subparsers.add_parser(
        "profile",
        help="Create a LitLaunch launch profile interactively.",
        formatter_class=parser.formatter_class,
    )
    profile_parser.add_argument("--name", help="Prefill the profile name.")
    profile_parser.add_argument("--app", dest="app_path", help="Prefill the app path.")
    profile_parser.add_argument(
        "--config",
        dest="config_path",
        help="Write to an explicit litlaunch.toml file.",
    )
    profile_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the generated profile TOML without writing it.",
    )
    profile_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing profile with the same name.",
    )
    profile_parser.set_defaults(create_handler=cmd_create_profile)


def cmd_create(args: argparse.Namespace, context: CliContext) -> int:
    """Dispatch the ``create`` namespace."""

    if not hasattr(args, "create_handler"):
        context.stream.write("Choose what to create. Try: litlaunch create profile\n")
        return 2
    return int(args.create_handler(args, context))


def cmd_create_profile(args: argparse.Namespace, context: CliContext) -> int:
    """Run the interactive profile creation wizard."""

    platform_info = context.platform_detector_factory().detect()
    try:
        run_profile_wizard(
            ProfileWizardOptions(
                name=args.name,
                app_path=args.app_path,
                config_path=args.config_path,
                dry_run=bool(args.dry_run),
                force=bool(args.force),
                use_color=(
                    not bool(getattr(args, "no_color", False))
                    and "NO_COLOR" not in context.env
                ),
            ),
            stream=context.stream,
            platform_is_windows=bool(platform_info.is_windows),
        )
    except ProfileWizardCancelled:
        return 130
    return 0
