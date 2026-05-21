"""Inspect command helpers for the LitLaunch CLI."""

from __future__ import annotations

import argparse
import webbrowser
from collections.abc import Callable
from pathlib import Path

from litlaunch.cli.common import CliContext, mode, renderer, write
from litlaunch.cli.config import add_profile_flags, load_cli_profile, profile_value
from litlaunch.config import BrowserChoice, LaunchMode, TrustMode
from litlaunch.console import ConsoleMode
from litlaunch.exceptions import LitLaunchError
from litlaunch.inspect import (
    HTMLDiagnosticsRenderer,
    JSONDiagnosticsRenderer,
    SanitizedBundleRenderer,
)


def add_inspect_flags(parser: argparse.ArgumentParser) -> None:
    """Add flags for the ``inspect`` command."""

    parser.add_argument("app_path", nargs="?")
    add_profile_flags(parser)
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
    parser.add_argument(
        "--trust-mode",
        choices=[item.value for item in TrustMode],
        help="Set the operational trust mode for diagnostics.",
    )
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
        "--allow-network-exposure",
        action="store_true",
        default=None,
        help=(
            "Acknowledge that a non-loopback host may expose the app beyond "
            "this machine."
        ),
    )
    parser.add_argument(
        "--output",
        help=(
            "Write inspect output to a UTF-8 file. Supports JSON, HTML, "
            "and bundle output."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing inspect output file.",
    )


def add_report_flags(parser: argparse.ArgumentParser) -> None:
    """Add flags for the ergonomic HTML diagnostics ``report`` command."""

    parser.add_argument("app_path", nargs="?")
    add_profile_flags(parser)
    parser.add_argument(
        "--trust-mode",
        choices=[item.value for item in TrustMode],
        help="Set the operational trust mode for diagnostics.",
    )
    parser.add_argument("--host")
    parser.add_argument(
        "--allow-network-exposure",
        action="store_true",
        default=None,
        help=(
            "Acknowledge that a non-loopback host may expose the app beyond "
            "this machine."
        ),
    )
    parser.add_argument(
        "--output",
        default="litlaunch-report.html",
        help="Write the HTML diagnostics report to this file.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing diagnostics report file.",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the generated HTML report in the default browser.",
    )


def cmd_inspect(args: argparse.Namespace, context: CliContext) -> int:
    """Run the ``inspect`` command."""

    validate_inspect_output_args(args)
    profile = load_cli_profile(args)
    if not _explicit_output_format(args):
        render_inspect_guidance(args, context)
        return 0

    report = collect_diagnostics_report(args, context, profile=profile)
    rendered = render_inspect_report(args, report)

    if args.output:
        output_path = write_inspect_output(
            Path(args.output),
            rendered,
            force=args.force,
        )
        write(context.stream, f"Wrote inspect report to {output_path}")
    else:
        context.stream.write(rendered)
        flush = getattr(context.stream, "flush", None)
        if callable(flush):
            flush()
    return 0 if report.ok else 1


def cmd_report(args: argparse.Namespace, context: CliContext) -> int:
    """Run the ergonomic standalone HTML diagnostics report command."""

    profile = load_cli_profile(args)
    report = collect_diagnostics_report(args, context, profile=profile)
    rendered = HTMLDiagnosticsRenderer(
        include_details=mode(args) == ConsoleMode.VERBOSE
    ).render(report)
    output_path = write_inspect_output(
        Path(args.output),
        rendered,
        force=args.force,
    )
    console = renderer(args, context)
    console.success(f"Report: wrote HTML diagnostics report to {output_path}")
    if args.open:
        open_report_path(output_path, console=console)
    return 0 if report.ok else 1


def collect_diagnostics_report(
    args: argparse.Namespace,
    context: CliContext,
    *,
    profile=None,
):
    """Collect diagnostics using the shared inspect/report collection semantics."""

    profile_config = profile.config if profile is not None else None
    collector = context.diagnostic_collector_factory(
        platform_detector=context.platform_detector_factory(),
        browser_registry=context.browser_registry_factory(),
        launcher_factory=context.launcher_factory,
    )
    return collector.collect(
        app_path=(
            args.app_path
            if getattr(args, "app_path", None) is not None
            else profile_config.app_path
            if profile_config is not None
            else None
        ),
        mode=profile_value(
            getattr(args, "mode", None),
            profile_config,
            "mode",
            LaunchMode.BROWSER,
        ),
        browser=profile_value(
            getattr(args, "browser", None),
            profile_config,
            "browser",
            BrowserChoice.AUTO,
        ),
        host=profile_value(
            getattr(args, "host", None),
            profile_config,
            "host",
            "127.0.0.1",
        ),
        port=profile_value(getattr(args, "port", None), profile_config, "port", None),
        auto_port=profile_value(
            getattr(args, "auto_port", None),
            profile_config,
            "auto_port",
            True,
        ),
        allow_browser_fallback=profile_value(
            getattr(args, "allow_browser_fallback", None),
            profile_config,
            "allow_browser_fallback",
            True,
        ),
        allow_network_exposure=profile_value(
            getattr(args, "allow_network_exposure", None),
            profile_config,
            "allow_network_exposure",
            False,
        ),
        trust_mode=profile_value(
            getattr(args, "trust_mode", None),
            profile_config,
            "trust_mode",
            TrustMode.DEVELOPMENT,
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


def render_inspect_report(args: argparse.Namespace, report) -> str:
    """Render a diagnostics report for parsed inspect args."""

    include_details = mode(args) == ConsoleMode.VERBOSE
    if args.json:
        return JSONDiagnosticsRenderer().render(report)
    if args.html:
        return HTMLDiagnosticsRenderer(include_details=include_details).render(report)
    if args.bundle:
        return SanitizedBundleRenderer(include_details=include_details).render(report)
    raise LitLaunchError("Choose --html, --json, or --bundle for inspect output.")


def render_inspect_guidance(args: argparse.Namespace, context: CliContext) -> None:
    """Render concise guidance for choosing a diagnostics artifact format."""

    console = renderer(args, context)
    console.success("Inspect reports are available as HTML, JSON, or support bundle")
    console.next_step("Run: litlaunch inspect --html --output litlaunch-report.html")
    console.next_step("Or: litlaunch inspect --json")
    console.next_step("Or: litlaunch inspect --bundle")


def validate_inspect_output_args(args: argparse.Namespace) -> None:
    """Validate inspect output path options."""

    if args.output and not (args.json or args.bundle or args.html):
        raise LitLaunchError("--output requires --json, --bundle, or --html.")
    if args.force and not args.output:
        raise LitLaunchError("--force requires --output.")


def _explicit_output_format(args: argparse.Namespace) -> bool:
    return bool(args.json or args.bundle or args.html)


def write_inspect_output(path: Path, rendered: str, *, force: bool) -> Path:
    """Write rendered inspect output to a UTF-8 file."""

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


def open_report_path(
    path: Path,
    *,
    console,
    browser_open: Callable[[str], bool] = webbrowser.open,
) -> bool:
    """Open a generated HTML diagnostics report with warning-only failures."""

    try:
        opened = bool(browser_open(path.resolve().as_uri()))
    except Exception as exc:  # pragma: no cover - defensive stdlib boundary.
        console.warning(f"Report: could not open generated report: {exc}")
        return False
    if not opened:
        console.warning("Report: could not open generated report.")
        return False
    console.success("Report: opened generated report in the default browser")
    return True
