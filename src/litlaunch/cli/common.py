"""Shared helpers for the LitLaunch CLI."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from litlaunch.browsers.registry import create_default_browser_registry
from litlaunch.console import ConsoleMode, ConsoleRenderer, ConsoleTheme
from litlaunch.inspect import DiagnosticCollector
from litlaunch.launcher import StreamlitLauncher
from litlaunch.platforms import PlatformDetector
from litlaunch.windowing import create_window_monitor


@dataclass(frozen=True)
class CliContext:
    """Dependency injection context for CLI command handlers."""

    stream: TextIO
    env: Mapping[str, str]
    platform_detector_factory: Any
    browser_registry_factory: Any
    launcher_factory: Any
    diagnostic_collector_factory: Any
    window_monitor_factory: Any


def build_context(
    *,
    stream: TextIO | None = None,
    env: Mapping[str, str] | None = None,
    platform_detector_factory: Any = PlatformDetector,
    browser_registry_factory: Any = create_default_browser_registry,
    launcher_factory: Any = StreamlitLauncher,
    diagnostic_collector_factory: Any = DiagnosticCollector,
    window_monitor_factory: Any = create_window_monitor,
) -> CliContext:
    """Build a CLI context with production defaults."""

    return CliContext(
        stream=stream if stream is not None else sys.stdout,
        env=env if env is not None else os.environ,
        platform_detector_factory=platform_detector_factory,
        browser_registry_factory=browser_registry_factory,
        launcher_factory=launcher_factory,
        diagnostic_collector_factory=diagnostic_collector_factory,
        window_monitor_factory=window_monitor_factory,
    )


def renderer(args: argparse.Namespace, context: CliContext) -> ConsoleRenderer:
    """Create a console renderer for parsed CLI arguments."""

    use_color = (
        not bool(getattr(args, "no_color", False)) and "NO_COLOR" not in context.env
    )
    return ConsoleRenderer(
        mode=mode(args),
        theme=ConsoleTheme(use_color=use_color),
        stream=context.stream,
        env=context.env,
    )


def mode(args: argparse.Namespace) -> ConsoleMode:
    """Return the requested console mode for parsed CLI arguments."""

    if getattr(args, "quiet", False):
        return ConsoleMode.QUIET
    if getattr(args, "verbose", False):
        return ConsoleMode.VERBOSE
    return ConsoleMode.NORMAL


def write(stream: TextIO, message: str) -> None:
    """Write one line to a CLI stream and flush if possible."""

    stream.write(f"{message}\n")
    flush = getattr(stream, "flush", None)
    if callable(flush):
        flush()


def source_checkout_example_path(module_path: Path) -> Path:
    """Return the source-checkout minimal example path for a module path."""

    return module_path.resolve().parents[2] / "examples" / "minimal_app" / "app.py"


def split_passthrough_args(
    values: Sequence[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split raw Streamlit passthrough args from app args after ``--``."""

    items = tuple(str(value) for value in values)
    if "--" not in items:
        return items, ()
    separator_index = items.index("--")
    return items[:separator_index], items[separator_index + 1 :]
