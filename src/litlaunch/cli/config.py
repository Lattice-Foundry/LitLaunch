"""CLI argument and profile mapping helpers."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from litlaunch.cli.common import split_passthrough_args
from litlaunch.config import BrowserChoice, LauncherConfig, LaunchMode, TrustMode
from litlaunch.exceptions import LitLaunchError
from litlaunch.profiles import LaunchProfile, load_profile
from litlaunch.windowing import WindowMonitorConfig


@dataclass(frozen=True)
class MonitorOptions:
    """Resolved window-monitoring options from profile and CLI values."""

    enabled: bool
    graceful_timeout_seconds: float
    window_monitor_config: WindowMonitorConfig


def add_runtime_flags(
    parser: argparse.ArgumentParser,
    *,
    include_dry_run: bool,
) -> None:
    """Add common runtime flags to ``run`` and ``command`` parsers."""

    parser.add_argument("app_path", nargs="?")
    add_profile_flags(parser)
    parser.add_argument(
        "--title",
        help="Set the runtime title used for browser/app-mode window matching.",
    )
    parser.add_argument("--mode", choices=[item.value for item in LaunchMode])
    parser.add_argument("--browser", choices=[item.value for item in BrowserChoice])
    parser.add_argument(
        "--trust-mode",
        choices=[item.value for item in TrustMode],
        help="Set the operational trust mode for this launch.",
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
        "--allow-network-exposure",
        action="store_true",
        default=None,
        help=(
            "Acknowledge that a non-loopback host may expose the app beyond "
            "this machine."
        ),
    )
    parser.add_argument(
        "--streamlit-flag",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        type=parse_streamlit_flag,
        help="Add a Streamlit flag. Repeatable.",
    )
    parser.add_argument(
        "--app-arg",
        action="append",
        default=[],
        help="Add an app argument after Streamlit's -- separator. Repeatable.",
    )


def add_profile_flags(parser: argparse.ArgumentParser) -> None:
    """Add profile selection flags to a parser."""

    parser.add_argument("--profile", help="Load a named LitLaunch launch profile.")
    parser.add_argument(
        "--config",
        dest="config_path",
        help="Load profiles from an explicit litlaunch.toml or pyproject.toml file.",
    )


def parse_streamlit_flag(value: str) -> tuple[str, str | None]:
    """Parse ``--streamlit-flag`` values."""

    key, separator, flag_value = value.partition("=")
    key = key.strip()
    if not key:
        raise argparse.ArgumentTypeError("streamlit flag key cannot be empty.")
    return key, flag_value if separator else None


def runtime_config_from_args(
    args: argparse.Namespace,
    *,
    profile: LaunchProfile | None = None,
) -> LauncherConfig:
    """Resolve CLI/profile values into a ``LauncherConfig``."""

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
        raise LitLaunchError(f"App path does not exist: {app_path}")

    streamlit_args, app_args = split_passthrough_args(args.passthrough_args)
    config = LauncherConfig(
        app_path=app_path,
        title=profile_value(args.title, profile_config, "title", "Streamlit App"),
        mode=profile_value(args.mode, profile_config, "mode", LaunchMode.BROWSER),
        browser=profile_value(
            args.browser,
            profile_config,
            "browser",
            BrowserChoice.AUTO,
        ),
        host=profile_value(args.host, profile_config, "host", "127.0.0.1"),
        port=profile_value(args.port, profile_config, "port", None),
        auto_port=profile_value(args.auto_port, profile_config, "auto_port", True),
        headless=profile_value(None, profile_config, "headless", None),
        allow_browser_fallback=profile_value(
            args.allow_browser_fallback,
            profile_config,
            "allow_browser_fallback",
            True,
        ),
        allow_network_exposure=profile_value(
            args.allow_network_exposure,
            profile_config,
            "allow_network_exposure",
            False,
        ),
        trust_mode=profile_value(
            args.trust_mode,
            profile_config,
            "trust_mode",
            TrustMode.DEVELOPMENT,
        ),
        cwd=profile_config.cwd if profile_config is not None else None,
        extra_env=profile_config.extra_env if profile_config is not None else {},
        streamlit_flags=merge_streamlit_flags(
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


def monitor_options_from_args(
    args: argparse.Namespace,
    profile: LaunchProfile | None,
) -> MonitorOptions:
    """Resolve window-monitoring options from CLI/profile values."""

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
    return MonitorOptions(
        enabled=bool(monitor_window),
        graceful_timeout_seconds=float(graceful_timeout),
        window_monitor_config=WindowMonitorConfig(
            appear_timeout_seconds=float(appear_timeout),
            poll_interval_seconds=float(poll_interval),
            stable_poll_count=int(stable_polls),
        ),
    )


def load_cli_profile(args: argparse.Namespace) -> LaunchProfile | None:
    """Load a named profile from parsed CLI args if requested."""

    config_path = getattr(args, "config_path", None)
    profile_name = getattr(args, "profile", None)
    if config_path and not profile_name:
        raise LitLaunchError("--config requires --profile.")
    if not profile_name:
        return None
    return load_profile(profile_name, config_path)


def profile_value(value, profile_config, field_name: str, default):
    """Return a CLI override, profile value, or default in that order."""

    if value is not None:
        return value
    if profile_config is not None:
        return getattr(profile_config, field_name)
    return default


def merge_streamlit_flags(profile_flags, cli_values):
    """Merge profile and CLI Streamlit flag representations."""

    cli_flags = streamlit_flags_mapping(cli_values)
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


def streamlit_flags_mapping(
    values: Sequence[tuple[str, str | None]],
) -> dict[str, str | None]:
    """Convert parsed ``--streamlit-flag`` values into a mapping."""

    return {key: value for key, value in values}
