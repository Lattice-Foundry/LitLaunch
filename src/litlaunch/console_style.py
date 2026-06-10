"""Canonical ANSI styling helpers for LitLaunch console output."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from litlaunch.colors import THEME_COLORS

ANSI_PATTERN = re.compile(r"\033\[[0-9;]*m")
ANSI_RESET = "\033[0m"
STATUS_LABEL_WIDTH = 8

ANSI_COLORS: Mapping[str, str] = {
    **{name: color.ansi for name, color in THEME_COLORS.items()},
}


def style_text(text: str, color_name: str, *, use_color: bool) -> str:
    """Style text with a named LitLaunch console color."""

    if not use_color:
        return text
    color = ANSI_COLORS.get(color_name, "")
    return f"{color}{text}{ANSI_RESET}" if color else text


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from console output."""

    return ANSI_PATTERN.sub("", text)


def status_prefix(status: str, color_name: str, *, use_color: bool) -> str:
    """Return a fixed-width bracket status prefix."""

    padded = f"{status:^{STATUS_LABEL_WIDTH}}"
    return f"[{style_text(padded, color_name, use_color=use_color)}]"


def configure_argparse_help_colors() -> None:
    """Align stdlib argparse help colors with LitLaunch's console palette.

    Python 3.14 exposes help coloring through the private ``_colorize`` module.
    That API currently accepts ANSI color enum values rather than arbitrary
    RGB palette entries, so this is intentionally centralized here as the one
    documented bridge between argparse internals and LitLaunch console styling.
    """

    try:
        from _colorize import ANSIColors, get_theme, set_theme
    except ImportError:  # pragma: no cover - older Python versions.
        return

    theme = get_theme(force_color=True)
    set_theme(
        theme.copy_with(
            argparse=theme.argparse.copy_with(
                summary_label=ANSIColors.GREEN,
                label=ANSIColors.INTENSE_YELLOW,
            )
        )
    )


def apply_argparse_help_formatter_colors(formatter: Any) -> None:
    """Apply LitLaunch argparse color choices to one formatter instance."""

    try:
        from _colorize import ANSIColors
    except ImportError:  # pragma: no cover - older Python versions.
        return
    formatter._theme = formatter._theme.copy_with(
        summary_label=ANSIColors.GREEN,
        label=ANSIColors.INTENSE_YELLOW,
    )
