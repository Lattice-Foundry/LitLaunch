"""Creation-oriented CLI commands."""

from __future__ import annotations

import argparse
from pathlib import Path

from litlaunch.cli.common import CliContext
from litlaunch.cli.config import add_profile_flags
from litlaunch.profile_wizard import (
    ProfileWizardCancelled,
    ProfileWizardOptions,
    run_profile_wizard,
)
from litlaunch.profiles import load_profile
from litlaunch.shortcut_writer import (
    ShortcutRequest,
    build_shortcut_plan,
    write_shortcut,
)


def add_create_flags(parser: argparse.ArgumentParser) -> None:
    """Add the ``create`` command namespace."""

    subparsers = parser.add_subparsers(
        dest="create_command",
        metavar="{profile,shortcut}",
    )
    profile_parser = subparsers.add_parser(
        "profile",
        help="Create a LitLaunch launch profile interactively.",
        description=(
            "Create a LitLaunch launch profile interactively. Simple mode covers "
            "guided app-window defaults; Advanced mode exposes runtime profile "
            "fields such as host, port, monitor tuning, args, cwd, and env. "
            "After writing, the wizard can optionally create a launch shortcut."
        ),
        epilog=(
            "Examples: litlaunch create profile | "
            "litlaunch create profile --name my-webapp --app app.py | "
            "litlaunch create profile --dry-run"
        ),
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

    shortcut_parser = subparsers.add_parser(
        "shortcut",
        help="Create a launch shortcut for a LitLaunch profile.",
        description=(
            "Create an OS-appropriate launch shortcut file for a LitLaunch "
            "profile. By default, the shortcut is written under "
            ".litlaunch/shortcuts in the app root."
        ),
        epilog=(
            "Examples: litlaunch create shortcut --profile my-webapp | "
            "litlaunch create shortcut --profile my-webapp --dry-run | "
            "litlaunch create shortcut --profile my-webapp --output Launch.bat --force"
        ),
        formatter_class=parser.formatter_class,
    )
    add_profile_flags(shortcut_parser)
    shortcut_parser.add_argument(
        "--output",
        dest="output_path",
        help="Write the shortcut to an explicit path.",
    )
    shortcut_parser.add_argument(
        "--name",
        help="Override the generated shortcut base filename.",
    )
    shortcut_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing shortcut file.",
    )
    shortcut_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the shortcut path and content without writing it.",
    )
    shortcut_parser.set_defaults(create_handler=cmd_create_shortcut)


def cmd_create(args: argparse.Namespace, context: CliContext) -> int:
    """Dispatch the ``create`` namespace."""

    if not hasattr(args, "create_handler"):
        context.stream.write(
            "Choose what to create. Try: litlaunch create profile "
            "or litlaunch create shortcut --profile NAME\n"
        )
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
            platform_info=platform_info,
        )
    except ProfileWizardCancelled:
        return 130
    return 0


def cmd_create_shortcut(args: argparse.Namespace, context: CliContext) -> int:
    """Create a profile launch shortcut."""

    if not args.profile:
        context.stream.write("Shortcut creation requires --profile NAME.\n")
        return 2
    platform_info = context.platform_detector_factory().detect()
    config_path = Path(args.config_path).resolve() if args.config_path else None
    profile = load_profile(args.profile, config_path)
    plan = build_shortcut_plan(
        ShortcutRequest(
            profile=profile,
            platform=platform_info,
            config_path=config_path,
            output_path=Path(args.output_path) if args.output_path else None,
            name=args.name,
        )
    )
    if args.dry_run:
        context.stream.write("Shortcut dry run\n")
        context.stream.write(f"Platform: {plan.platform.value}\n")
        context.stream.write(f"Profile: {plan.profile_name}\n")
        context.stream.write(f"Output: {plan.output_path}\n")
        context.stream.write(f"Command: {' '.join(plan.command)}\n")
        context.stream.write("\n")
        context.stream.write(plan.content)
        return 0
    write_shortcut(plan, force=bool(args.force))
    context.stream.write(f"Created shortcut: {plan.output_path}\n")
    return 0
