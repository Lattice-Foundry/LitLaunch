"""Workflow-oriented CLI help for LitLaunch users.

This module intentionally complements argparse reference help. Use
``litlaunch --help`` or ``litlaunch run --help`` for flags and command syntax;
use ``litlaunch help ...`` for short workflow guidance.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from litlaunch.cli.common import CliContext, write
from litlaunch.colors import THEME_COLORS, muted_amber, streamlit_blue, terminal_green
from litlaunch.exceptions import LitLaunchError

HELP_TOPICS = ("launch", "diagnostics", "profiles", "tools", "examples", "dev", "all")


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
    use_color = (
        not bool(getattr(args, "no_color", False)) and "NO_COLOR" not in context.env
    )
    write(context.stream, render_workflow_help(topic, use_color=use_color))
    return 0


def render_workflow_help(topic: str, *, use_color: bool = False) -> str:
    """Return workflow help text for a supported topic."""

    style = _HelpStyle(use_color=use_color)
    if topic == "menu":
        return _join(
            style.heading("LitLaunch workflow help"),
            "",
            "Use --help for command reference.",
            "Use litlaunch help <topic> for workflows.",
            "",
            style.label("Topics:"),
            "  launch       Run Streamlit apps.",
            "  diagnostics  Generate reports and support diagnostics.",
            "  profiles     Reuse settings from litlaunch.toml or pyproject.toml.",
            "  tools        Create profiles and project assets.",
            "  examples     Copy/paste common commands.",
            f"  dev          {style.warning('Internal developer preview tooling.')}",
            "",
            style.label("Try:"),
            *style.commands(
                "litlaunch help launch",
                "litlaunch help diagnostics",
            ),
        )
    if topic == "launch":
        return _join(
            style.heading("Launch workflows"),
            "",
            "Run Streamlit apps with friendly shorthand or explicit commands.",
            "",
            style.label("Friendly:"),
            *style.commands(
                "litlaunch app.py",
                "litlaunch --profile NAME",
            ),
            "",
            style.label("Explicit:"),
            *style.commands(
                "litlaunch run app.py",
                "litlaunch run --profile NAME",
            ),
            "",
            style.label("Useful flags:"),
            "  --mode browser|webapp",
            "  --browser auto|edge|chrome|default",
            "  --monitor-window",
            "  --verbose",
            "",
            style.warning(
                "Bare profile names are intentionally not supported; "
                "use --profile NAME."
            ),
        )
    if topic == "diagnostics":
        return _join(
            style.heading("Diagnostics workflows"),
            "",
            "`report` is the recommended human-readable HTML diagnostics workflow.",
            "`inspect` is for advanced diagnostics artifacts.",
            "",
            style.label("HTML report:"),
            *style.commands(
                "litlaunch report",
                "litlaunch report app.py",
                "litlaunch report --profile NAME",
                "litlaunch report --profile NAME --open",
                "litlaunch report --output litlaunch-report.html --force",
            ),
            "",
            style.label("Advanced inspect outputs:"),
            *style.commands(
                "litlaunch inspect --json",
                "litlaunch inspect --bundle",
                "litlaunch inspect --html --output report.html",
            ),
            "",
            "JSON is machine-readable. Bundles are copyable support artifacts.",
        )
    if topic == "profiles":
        return _join(
            style.heading("Profile workflows"),
            "",
            "Profiles store reusable launch settings.",
            "",
            style.label("Create a profile:"),
            *style.commands("litlaunch create profile"),
            "  Choose Simple for guided defaults, or Advanced for runtime fields.",
            "",
            style.label("Create a launch shortcut:"),
            *style.commands("litlaunch create shortcut --profile NAME"),
            "  Writes a .bat, .sh, or .command file into the app root.",
            "",
            style.label("Run a profile:"),
            *style.commands(
                "litlaunch --profile NAME",
                "litlaunch run --profile NAME",
            ),
            "",
            style.label("Choose a config file:"),
            *style.commands(
                "litlaunch --config litlaunch.toml --profile NAME",
                "litlaunch --config pyproject.toml --profile NAME",
            ),
            "",
            style.label("Profile sources:"),
            "  litlaunch.toml",
            "  pyproject.toml under [tool.litlaunch]",
            "",
            "CLI flags override profile values.",
        )
    if topic == "tools":
        return _join(
            style.heading("Tools workflows"),
            "",
            "Create project assets without launching the app.",
            "",
            style.label("Profiles:"),
            *style.commands(
                "litlaunch create profile",
                "litlaunch create profile --name my-webapp --app app.py",
                "litlaunch create profile --dry-run",
            ),
            "  Simple mode covers common app-window profiles.",
            "  Advanced mode exposes network, browser, monitor, args, cwd, and env.",
            "",
            style.label("Shortcuts:"),
            *style.commands(
                "litlaunch create shortcut --profile my-webapp",
                "litlaunch create shortcut --profile my-webapp --dry-run",
            ),
            "  Shortcut files are written to the app root by default.",
            "",
            style.warning("Wizard shortcut integration is planned separately."),
        )
    if topic == "examples":
        return _join(
            style.heading("Examples"),
            "",
            style.label("Launch an app:"),
            *style.commands("litlaunch app.py"),
            "",
            style.label("Launch a profile:"),
            *style.commands("litlaunch --profile my-webapp"),
            "",
            style.label("Create a profile:"),
            *style.commands("litlaunch create profile"),
            "",
            style.label("Generate a report:"),
            *style.commands(
                "litlaunch report --profile my-webapp",
                "litlaunch report --profile my-webapp --open",
            ),
            "",
            style.label("Troubleshoot with more detail:"),
            *style.commands("litlaunch app.py --verbose"),
            "",
            style.label("Preview the backend command:"),
            *style.commands(
                "litlaunch command app.py",
                "litlaunch command --profile my-webapp",
            ),
            "",
            style.label("Check local capabilities:"),
            *style.commands(
                "litlaunch browsers",
                "litlaunch browsers --verbose",
                "litlaunch platform",
                "litlaunch platform --verbose",
                "litlaunch version",
            ),
            "",
            style.label("Find the source-checkout example app:"),
            *style.commands("litlaunch example"),
        )
    if topic == "dev":
        return _join(
            style.heading("Developer tooling"),
            "",
            style.warning(
                "Console preview is internal developer-facing tooling, not a "
                "main user workflow."
            ),
            "Use it for rapid formatting, color, category, and verbosity review.",
            "",
            style.label("Commands:"),
            *style.commands(
                "litlaunch console-preview --all",
                "litlaunch console-preview --normal",
                "litlaunch console-preview --verbose",
            ),
            "",
            "Preview output is not a stable public workflow contract. Some values "
            "are simulated to resemble real runtime views.",
        )
    if topic == "all":
        return _join(
            style.heading("LitLaunch workflow overview"),
            "",
            style.label("Launch:"),
            *style.commands(
                "litlaunch app.py",
                "litlaunch --profile NAME",
                "litlaunch run app.py",
            ),
            "",
            style.label("Diagnostics:"),
            *style.commands(
                "litlaunch report --profile NAME --open",
                "litlaunch inspect --json",
                "litlaunch inspect --bundle",
            ),
            "",
            style.label("Planning and info:"),
            *style.commands(
                "litlaunch command app.py",
                "litlaunch command --profile NAME",
                "litlaunch create profile",
                "litlaunch browsers --verbose",
                "litlaunch platform --verbose",
                "litlaunch version",
            ),
            "",
            style.label("Topics:"),
            *style.commands(
                "litlaunch help launch",
                "litlaunch help diagnostics",
                "litlaunch help profiles",
                "litlaunch help tools",
                "litlaunch help examples",
                "litlaunch help dev",
            ),
            "",
            style.warning(
                "Bare profile names are intentionally not supported; "
                "use --profile NAME."
            ),
        )
    available = ", ".join(HELP_TOPICS)
    raise LitLaunchError(f"Unknown help topic: {topic}. Available topics: {available}.")


def _join(*lines: str) -> str:
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class _HelpStyle:
    """Small color layer for workflow help, separate from argparse help."""

    use_color: bool = False

    def heading(self, text: str) -> str:
        return self._style(text, streamlit_blue)

    def label(self, text: str) -> str:
        return self._style(text, streamlit_blue)

    def command(self, text: str) -> str:
        return self._style(text, terminal_green)

    def warning(self, text: str) -> str:
        return self._style(text, muted_amber)

    def commands(self, *values: str) -> tuple[str, ...]:
        return tuple(f"  {self.command(value)}" for value in values)

    def _style(self, text: str, color_name: str) -> str:
        if not self.use_color:
            return text
        color = THEME_COLORS[color_name].ansi
        reset = "\033[0m"
        return f"{color}{text}{reset}"
