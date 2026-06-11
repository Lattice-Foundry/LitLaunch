"""Workflow-oriented CLI help for LitLaunch users.

This module intentionally complements argparse reference help. Use
``litlaunch --help`` or ``litlaunch run --help`` for flags and command syntax;
use ``litlaunch help ...`` for short workflow guidance.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from litlaunch.cli.common import CliContext, write
from litlaunch.colors import muted_amber, streamlit_blue, terminal_green
from litlaunch.console_style import style_text
from litlaunch.exceptions import LitLaunchError

HELP_TOPICS = (
    "launch",
    "diagnostics",
    "security",
    "profiles",
    "tools",
    "examples",
    "dev",
    "all",
)


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
            "  security     Review trust, exposure, and transport posture.",
            "  profiles     Reuse settings from litlaunch.toml or pyproject.toml.",
            "  tools        Create profiles and project assets.",
            "  examples     Copy/paste common commands.",
            f"  dev          {style.warning('Internal developer tooling.')}",
            "",
            style.label("Try:"),
            *style.commands(
                "litlaunch help launch",
                "litlaunch help diagnostics",
                "litlaunch help security",
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
                "litlaunch app.py --mode webapp",
                "litlaunch --profile NAME",
            ),
            "",
            style.label("Explicit:"),
            *style.commands(
                "litlaunch run app.py --mode webapp",
                "litlaunch run --profile NAME",
            ),
            "",
            style.label("Useful flags:"),
            "  --mode browser|webapp",
            "  --browser auto|edge|chrome|default",
            "  --trust-mode development|strict_local|internal_network",
            "  --allow-network-exposure",
            "  --no-monitor-browser-window",
            "  --monitor-window",
            "  --no-monitor-window",
            "  --verbose",
            "",
            "Browser mode uses managed browser-window monitoring where supported.",
            "Webapp mode uses app-window monitoring where supported.",
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
            (
                "Reports include Runtime Governance, Runtime Exposure, "
                "and Transport Security."
            ),
            "",
            style.label("HTML report:"),
            *style.commands(
                "litlaunch report",
                "litlaunch report app.py",
                "litlaunch report --profile NAME",
                "litlaunch report --profile NAME --open",
                "litlaunch report --output my-report.html --force",
            ),
            "  Default path: .litlaunch/reports/litlaunch-report.html",
            "",
            style.label("Advanced inspect outputs:"),
            *style.commands(
                "litlaunch inspect --json",
                "litlaunch inspect --bundle",
                "litlaunch inspect --html --output report.html",
            ),
            "",
            "JSON is machine-readable. Bundles are copyable support artifacts.",
            "Use --streamlit-flag to show Streamlit-native TLS settings.",
        )
    if topic == "security":
        return _join(
            style.heading("Security and governance workflows"),
            "",
            "LitLaunch reports operational runtime posture.",
            "LitLaunch does not secure Streamlit applications.",
            "",
            style.label("Local-only launch:"),
            *style.commands(
                "litlaunch app.py --trust-mode strict_local",
                "litlaunch report app.py --trust-mode strict_local",
            ),
            "",
            style.label("Intentional internal-network launch:"),
            *style.commands(
                (
                    "litlaunch app.py --host 0.0.0.0 "
                    "--trust-mode internal_network --allow-network-exposure"
                ),
                (
                    "litlaunch report app.py --host 0.0.0.0 "
                    "--trust-mode internal_network --allow-network-exposure"
                ),
            ),
            "",
            style.label("Streamlit-native TLS example:"),
            *style.commands(
                "litlaunch report app.py --host 0.0.0.0 --trust-mode internal_network "
                "--allow-network-exposure --streamlit-flag server.sslCertFile=cert.pem "
                "--streamlit-flag server.sslKeyFile=key.pem",
            ),
            "",
            style.label("Diagnostics sections:"),
            "  Runtime Governance summarizes allowed/blocked posture.",
            "  Runtime Exposure shows host scope and acknowledgement state.",
            "  Transport Security shows Streamlit-native TLS and plaintext risk.",
            "",
            (
                "Wildcard hosts bind Streamlit to the requested network-visible "
                "address; LitLaunch health/browser checks use a local client URL."
            ),
            "",
            style.warning(
                "TLS encrypts transport but does not add app authentication."
            ),
        )
    if topic == "profiles":
        return _join(
            style.heading("Profile workflows"),
            "",
            "Profiles store reusable launch settings.",
            "Profiles can declare trust mode and intentional exposure.",
            "",
            style.label("Create a profile:"),
            *style.commands("litlaunch create profile"),
            "  Choose Simple for guided defaults, or Advanced for runtime fields.",
            "",
            style.label("Create a launch shortcut:"),
            *style.commands("litlaunch create shortcut --profile NAME"),
            "  Writes a native launcher under .litlaunch/shortcuts by default.",
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
            "Use trust_mode and allow_network_exposure for network posture.",
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
            "  After writing, the wizard can optionally create a launch shortcut.",
            (
                "  Generated reports, shortcuts, temp browser profiles, "
                "and temp browser shortcuts use .litlaunch."
            ),
            "",
            style.label("Shortcuts:"),
            *style.commands(
                "litlaunch create shortcut --profile my-webapp",
                "litlaunch create shortcut --profile my-webapp --kind script",
                "litlaunch create shortcut --profile my-webapp --dry-run",
            ),
            "  Native shortcuts are .lnk on Windows, .desktop on Linux, and",
            "  .app bundles on macOS. Use --kind script for .bat/.sh/.command.",
            "  macOS shortcut support has lighter first-party validation",
            "  while community coverage broadens.",
        )
    if topic == "examples":
        return _join(
            style.heading("Examples"),
            "",
            style.label("Launch an app:"),
            *style.commands("litlaunch app.py --mode webapp"),
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
            *style.commands("litlaunch app.py --mode webapp --verbose"),
            "",
            style.label("Show the backend command:"),
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
                "Console rendering checks are internal developer-facing tooling, not a "
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
            "Console rendering output is an internal developer workflow. Some values "
            "are simulated to resemble real runtime views.",
        )
    if topic == "all":
        return _join(
            style.heading("LitLaunch workflow overview"),
            "",
            style.label("Launch:"),
            *style.commands(
                "litlaunch app.py --mode webapp",
                "litlaunch --profile NAME",
                "litlaunch run app.py --mode webapp",
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
                "litlaunch help security",
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
        return style_text(text, streamlit_blue, use_color=self.use_color)

    def label(self, text: str) -> str:
        return style_text(text, streamlit_blue, use_color=self.use_color)

    def command(self, text: str) -> str:
        return style_text(text, terminal_green, use_color=self.use_color)

    def warning(self, text: str) -> str:
        return style_text(text, muted_amber, use_color=self.use_color)

    def commands(self, *values: str) -> tuple[str, ...]:
        return tuple(f"  {self.command(value)}" for value in values)
