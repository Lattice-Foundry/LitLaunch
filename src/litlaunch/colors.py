"""Named console theme colors for LitLaunch."""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType

HEX_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")

streamlit_blue = "streamlit_blue"
streamlit_blue_light = "streamlit_blue_light"
terminal_green = "terminal_green"
powershell_red = "powershell_red"
muted_amber = "muted_amber"
hook_orange = "hook_orange"
muted_gray = "muted_gray"
success_green = "success_green"


def is_hex_color(value: str) -> bool:
    """Return whether a string is a #RRGGBB color."""

    return bool(HEX_COLOR_PATTERN.fullmatch(value))


@dataclass(frozen=True)
class ThemeColor:
    """Developer-facing named color value."""

    name: str
    hex: str
    ansi: str

    def __post_init__(self) -> None:
        if not is_hex_color(self.hex):
            raise ValueError(f"Theme color {self.name!r} must use #RRGGBB hex.")


THEME_COLORS = MappingProxyType(
    {
        streamlit_blue: ThemeColor(
            name=streamlit_blue,
            hex="#1c83e1",
            ansi="\033[38;2;28;131;225m",
        ),
        streamlit_blue_light: ThemeColor(
            name=streamlit_blue_light,
            hex="#83c9ff",
            ansi="\033[38;2;131;201;255m",
        ),
        terminal_green: ThemeColor(
            name=terminal_green,
            hex="#16c60c",
            ansi="\033[38;2;22;198;12m",
        ),
        powershell_red: ThemeColor(
            name=powershell_red,
            hex="#E74856",
            ansi="\033[38;2;231;72;86m",
        ),
        muted_amber: ThemeColor(
            name=muted_amber,
            hex="#F9F1A5",
            ansi="\033[38;2;249;241;165m",
        ),
        hook_orange: ThemeColor(
            name=hook_orange,
            hex="#F7630C",
            ansi="\033[38;2;247;99;12m",
        ),
        muted_gray: ThemeColor(
            name=muted_gray,
            hex="#8a8f98",
            ansi="\033[38;2;138;143;152m",
        ),
        success_green: ThemeColor(
            name=success_green,
            hex="#13a10e",
            ansi="\033[38;2;19;161;14m",
        ),
    }
)


def is_theme_color_name(value: str) -> bool:
    """Return whether a string is one of LitLaunch's named theme colors."""

    return value in THEME_COLORS


def get_theme_color(name: str) -> ThemeColor | None:
    """Return a named theme color, if LitLaunch defines it."""

    return THEME_COLORS.get(name)
