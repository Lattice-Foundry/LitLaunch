"""Typed configuration primitives for LitLaunch."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any

from litlaunch.exceptions import ConfigurationError


class LaunchMode(str, Enum):
    """Supported Streamlit launch modes."""

    BROWSER = "browser"
    WEBAPP = "webapp"


class BrowserChoice(str, Enum):
    """Supported browser selection values."""

    AUTO = "auto"
    EDGE = "edge"
    CHROME = "chrome"
    DEFAULT = "default"


StreamlitFlags = Mapping[str, str | int | float | bool | None] | Sequence[str]


@dataclass(frozen=True)
class LauncherConfig:
    """Configuration for a Streamlit launcher run."""

    app_path: str | Path
    title: str = "Streamlit App"
    mode: LaunchMode | str = LaunchMode.BROWSER
    browser: BrowserChoice | str = BrowserChoice.AUTO
    host: str = "127.0.0.1"
    port: int | None = None
    auto_port: bool = True
    headless: bool | None = None
    allow_browser_fallback: bool = True
    streamlit_flags: StreamlitFlags = field(default_factory=dict)
    app_args: Sequence[str] = field(default_factory=tuple)
    extra_browser_args: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        app_path = _normalize_path(self.app_path)
        title = _normalize_required_string(self.title, "title")
        mode = _normalize_enum(LaunchMode, self.mode, "mode")
        browser = _normalize_enum(BrowserChoice, self.browser, "browser")
        host = _normalize_required_string(self.host, "host")
        port = _normalize_port(self.port)
        auto_port = True if port is None else bool(self.auto_port)
        app_args = _normalize_string_sequence(self.app_args, "app_args")
        extra_browser_args = _normalize_string_sequence(
            self.extra_browser_args,
            "extra_browser_args",
        )
        streamlit_flags = _normalize_streamlit_flags(self.streamlit_flags)

        object.__setattr__(self, "app_path", app_path)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "browser", browser)
        object.__setattr__(self, "host", host)
        object.__setattr__(self, "port", port)
        object.__setattr__(self, "auto_port", auto_port)
        object.__setattr__(
            self, "allow_browser_fallback", bool(self.allow_browser_fallback)
        )
        object.__setattr__(self, "app_args", app_args)
        object.__setattr__(self, "extra_browser_args", extra_browser_args)
        object.__setattr__(self, "streamlit_flags", streamlit_flags)


def _normalize_path(value: str | Path) -> Path:
    if isinstance(value, Path):
        path = value
    else:
        raw_value = str(value).strip()
        if not raw_value:
            raise ConfigurationError("app_path cannot be empty.")
        path = Path(raw_value)
    if not str(path):
        raise ConfigurationError("app_path cannot be empty.")
    return path


def _normalize_required_string(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ConfigurationError(f"{field_name} cannot be empty.")
    return normalized


def _normalize_enum(
    enum_type: type[LaunchMode] | type[BrowserChoice],
    value: LaunchMode | BrowserChoice | str,
    field_name: str,
) -> LaunchMode | BrowserChoice:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(str(value).strip().lower())
    except ValueError as exc:
        valid = ", ".join(item.value for item in enum_type)
        raise ConfigurationError(
            f"Invalid {field_name}: {value!r}. Expected one of: {valid}."
        ) from exc


def _normalize_port(value: int | None) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigurationError("port must be an integer from 1 to 65535.")
    if value < 1 or value > 65535:
        raise ConfigurationError("port must be an integer from 1 to 65535.")
    return value


def _normalize_string_sequence(
    value: Sequence[str], field_name: str
) -> tuple[str, ...]:
    if isinstance(value, str):
        raise ConfigurationError(f"{field_name} must be a sequence of strings.")
    try:
        normalized = tuple(str(item) for item in value)
    except TypeError as exc:
        raise ConfigurationError(
            f"{field_name} must be a sequence of strings."
        ) from exc
    return normalized


def _normalize_streamlit_flags(
    flags: StreamlitFlags,
) -> MappingProxyType[str, str | int | float | bool | None] | tuple[str, ...]:
    if isinstance(flags, Mapping):
        copied: dict[str, str | int | float | bool | None] = {}
        for key, value in flags.items():
            flag_name = str(key).strip()
            if not flag_name:
                raise ConfigurationError("streamlit flag names cannot be empty.")
            copied[flag_name] = _validate_flag_value(value)
        return MappingProxyType(copied)

    if isinstance(flags, str):
        raise ConfigurationError("streamlit_flags must be a mapping or sequence.")

    try:
        return tuple(str(item) for item in flags)
    except TypeError as exc:
        raise ConfigurationError(
            "streamlit_flags must be a mapping or sequence."
        ) from exc


def _validate_flag_value(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ConfigurationError(
        "streamlit flag values must be str, int, float, bool, or None."
    )
