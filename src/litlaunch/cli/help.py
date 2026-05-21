"""Workflow-oriented CLI help for LitLaunch users.

This module intentionally complements argparse reference help. Use
``litlaunch --help`` or ``litlaunch run --help`` for flags and command syntax;
use ``litlaunch help ...`` for short workflow guidance.
"""

from __future__ import annotations

import argparse

from litlaunch.cli.common import CliContext, write
from litlaunch.exceptions import LitLaunchError

HELP_TOPICS = ("launch", "diagnostics", "profiles", "examples", "dev", "all")


def add_workflow_help_flags(parser: argparse.ArgumentParser) -> None:
    """Add flags for the workflow help command."""

    parser.add_argument(
        "topic",
        nargs="?",
        help="Workflow help topic.",
    )


def cmd_workflow_help(args: argparse.Namespace, context: CliContext) -> int:
    """Render workflow-oriented help."""

    topic = args.topic or "menu"
    write(context.stream, render_workflow_help(topic))
    return 0


def render_workflow_help(topic: str) -> str:
    """Return workflow help text for a supported topic."""

    if topic == "menu":
        return _join(
            "LitLaunch workflow help",
            "",
            "Use --help for command reference.",
            "Use litlaunch help <topic> for workflows.",
            "",
            "Topics:",
            "  launch       Run Streamlit apps.",
            "  diagnostics  Generate reports and support diagnostics.",
            "  profiles     Reuse settings from litlaunch.toml or pyproject.toml.",
            "  examples     Copy/paste common commands.",
            "  dev          Internal developer preview tooling.",
            "",
            "Try:",
            "  litlaunch help launch",
            "  litlaunch help diagnostics",
        )
    if topic == "launch":
        return _join(
            "Launch workflows",
            "",
            "Common:",
            "  litlaunch app.py",
            "  litlaunch --profile rolethread-webapp",
            "",
            "Explicit:",
            "  litlaunch run app.py",
            "  litlaunch run --profile rolethread-webapp",
            "",
            "Useful flags:",
            "  --mode browser|webapp",
            "  --browser auto|edge|chrome|default",
            "  --monitor-window",
            "  --verbose",
            "",
            "Bare profile names are not supported. Use --profile NAME.",
        )
    if topic == "diagnostics":
        return _join(
            "Diagnostics workflows",
            "",
            "Human-readable HTML report:",
            "  litlaunch report",
            "  litlaunch report --profile rolethread-webapp",
            "  litlaunch report --profile rolethread-webapp --open",
            "",
            "Advanced inspect outputs:",
            "  litlaunch inspect --json",
            "  litlaunch inspect --bundle",
            "  litlaunch inspect --html --output litlaunch-report.html",
            "",
            "Use report for shareable human diagnostics. Use inspect for JSON, "
            "support bundles, and explicit diagnostics formats.",
        )
    if topic == "profiles":
        return _join(
            "Profile workflows",
            "",
            "Profiles store reusable launch settings.",
            "",
            "Run a profile:",
            "  litlaunch --profile my-webapp",
            "  litlaunch run --profile my-webapp",
            "",
            "Choose a config file:",
            "  litlaunch --config litlaunch.toml --profile my-webapp",
            "  litlaunch --config pyproject.toml --profile my-webapp",
            "",
            "Profile sources:",
            "  litlaunch.toml",
            "  pyproject.toml under [tool.litlaunch]",
            "",
            "CLI flags override profile values.",
        )
    if topic == "examples":
        return _join(
            "Examples",
            "",
            "Launch an app:",
            "  litlaunch app.py",
            "",
            "Launch a profile:",
            "  litlaunch --profile my-webapp",
            "",
            "Generate a report:",
            "  litlaunch report --profile my-webapp",
            "  litlaunch report --profile my-webapp --open",
            "",
            "Troubleshoot with more detail:",
            "  litlaunch app.py --verbose",
            "",
            "Preview the backend command:",
            "  litlaunch command app.py",
            "",
            "Check local capabilities:",
            "  litlaunch browsers --verbose",
            "  litlaunch platform --verbose",
            "",
            "Find the source-checkout example app:",
            "  litlaunch example",
        )
    if topic == "dev":
        return _join(
            "Developer tooling",
            "",
            "Console preview is internal developer-facing tooling for rapid "
            "formatting, color, category, and verbosity review.",
            "",
            "Commands:",
            "  litlaunch console-preview --all",
            "  litlaunch console-preview --normal",
            "  litlaunch console-preview --verbose",
            "",
            "Preview output is not a stable public workflow contract. Some values "
            "are simulated to resemble real runtime views.",
        )
    if topic == "all":
        return "\n\n".join(
            render_workflow_help(name) for name in HELP_TOPICS if name != "all"
        )
    available = ", ".join(HELP_TOPICS)
    raise LitLaunchError(f"Unknown help topic: {topic}. Available topics: {available}.")


def _join(*lines: str) -> str:
    return "\n".join(lines) + "\n"
