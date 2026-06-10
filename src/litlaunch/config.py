"""Typed configuration primitives for LitLaunch."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from litlaunch.exceptions import ConfigurationError

HOSTNAME_PATTERN = re.compile(r"^[A-Za-z0-9.-]+$")


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


class TrustMode(str, Enum):
    """Operational trust posture for a LitLaunch runtime."""

    DEVELOPMENT = "development"
    STRICT_LOCAL = "strict_local"
    INTERNAL_NETWORK = "internal_network"


FlagValue = str | int | float | bool | None
StreamlitFlags = Mapping[str, FlagValue] | Sequence[str]
NormalizedStreamlitFlags = MappingProxyType[str, FlagValue] | tuple[str, ...]
_EMPTY_ENV: Mapping[str, str] = MappingProxyType({})
_EMPTY_STREAMLIT_FLAGS: Mapping[str, FlagValue] = MappingProxyType({})


@dataclass(frozen=True, init=False)
class LauncherConfig:
    """Configuration for a Streamlit launcher run."""

    app_path: Path
    title: str
    mode: LaunchMode
    browser: BrowserChoice
    host: str
    port: int | None
    auto_port: bool
    headless: bool | None
    show_streamlit_chrome: bool
    allow_browser_fallback: bool
    allow_network_exposure: bool
    trust_mode: TrustMode
    cwd: Path | None
    extra_env: MappingProxyType[str, str]
    runtime_event_log: Path | None
    streamlit_flags: NormalizedStreamlitFlags
    streamlit_args: tuple[str, ...]
    app_args: tuple[str, ...]
    extra_browser_args: tuple[str, ...]

    def __init__(
        self,
        app_path: str | Path,
        title: str = "Streamlit App",
        mode: LaunchMode | str = LaunchMode.BROWSER,
        browser: BrowserChoice | str = BrowserChoice.AUTO,
        host: str = "127.0.0.1",
        port: int | None = None,
        auto_port: bool = True,
        headless: bool | None = None,
        show_streamlit_chrome: bool = False,
        allow_browser_fallback: bool = True,
        allow_network_exposure: bool = False,
        trust_mode: TrustMode | str = TrustMode.DEVELOPMENT,
        cwd: str | Path | None = None,
        extra_env: Mapping[str, str] = _EMPTY_ENV,
        runtime_event_log: str | Path | None = None,
        streamlit_flags: StreamlitFlags = _EMPTY_STREAMLIT_FLAGS,
        streamlit_args: Sequence[str] = (),
        app_args: Sequence[str] = (),
        extra_browser_args: Sequence[str] = (),
    ) -> None:
        app_path = _normalize_path(app_path)
        title = _normalize_required_string(title, "title")
        mode = _normalize_launch_mode(mode)
        browser = _normalize_browser_choice(browser)
        trust_mode = _normalize_trust_mode(trust_mode)
        host = _normalize_host(host)
        port = _normalize_port(port)
        auto_port = True if port is None else bool(auto_port)
        cwd = _normalize_optional_path(cwd, "cwd")
        runtime_event_log = _normalize_optional_path(
            runtime_event_log,
            "runtime_event_log",
        )
        extra_env = _normalize_env_mapping(extra_env)
        streamlit_args = _normalize_string_sequence(
            streamlit_args,
            "streamlit_args",
        )
        app_args = _normalize_string_sequence(app_args, "app_args")
        extra_browser_args = _normalize_string_sequence(
            extra_browser_args,
            "extra_browser_args",
        )
        streamlit_flags = _normalize_streamlit_flags(streamlit_flags)
        show_streamlit_chrome = bool(show_streamlit_chrome)
        _validate_webapp_headless(
            mode,
            headless,
            streamlit_flags,
            streamlit_args,
        )

        object.__setattr__(self, "app_path", app_path)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "browser", browser)
        object.__setattr__(self, "host", host)
        object.__setattr__(self, "port", port)
        object.__setattr__(self, "auto_port", auto_port)
        object.__setattr__(self, "headless", headless)
        object.__setattr__(self, "allow_browser_fallback", bool(allow_browser_fallback))
        object.__setattr__(self, "allow_network_exposure", bool(allow_network_exposure))
        object.__setattr__(self, "trust_mode", trust_mode)
        object.__setattr__(self, "cwd", cwd)
        object.__setattr__(self, "extra_env", extra_env)
        object.__setattr__(self, "runtime_event_log", runtime_event_log)
        object.__setattr__(self, "streamlit_args", streamlit_args)
        object.__setattr__(self, "app_args", app_args)
        object.__setattr__(self, "extra_browser_args", extra_browser_args)
        object.__setattr__(self, "streamlit_flags", streamlit_flags)
        object.__setattr__(self, "show_streamlit_chrome", show_streamlit_chrome)


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


def _normalize_optional_path(value: str | Path | None, field_name: str) -> Path | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return value
    raw_value = str(value).strip()
    if not raw_value:
        raise ConfigurationError(f"{field_name} cannot be empty.")
    return Path(raw_value)


def _normalize_env_mapping(value: Mapping[str, str]) -> MappingProxyType[str, str]:
    if not isinstance(value, Mapping):
        raise ConfigurationError("extra_env must be a mapping of strings.")
    copied: dict[str, str] = {}
    for key, item in value.items():
        env_name = str(key).strip()
        if not env_name:
            raise ConfigurationError("extra_env variable names cannot be empty.")
        if "\x00" in env_name:
            raise ConfigurationError("extra_env variable names cannot contain NUL.")
        env_value = str(item)
        if "\x00" in env_value:
            raise ConfigurationError("extra_env values cannot contain NUL.")
        copied[env_name] = env_value
    return MappingProxyType(copied)


def _normalize_required_string(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ConfigurationError(f"{field_name} cannot be empty.")
    return normalized


def _normalize_host(value: str) -> str:
    host = _normalize_required_string(value, "host")
    if _is_ip_address(host) or _is_plausible_hostname(host):
        return host
    raise ConfigurationError("host must be a valid IP address or plausible hostname.")


def _is_ip_address(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def _is_plausible_hostname(value: str) -> bool:
    if len(value) > 253 or not HOSTNAME_PATTERN.fullmatch(value):
        return False
    hostname = value[:-1] if value.endswith(".") else value
    if not hostname:
        return False
    labels = hostname.split(".")
    for label in labels:
        if not label or len(label) > 63:
            return False
        if label.startswith("-") or label.endswith("-"):
            return False
    return True


def _normalize_enum(
    enum_type: type[LaunchMode] | type[BrowserChoice] | type[TrustMode],
    value: LaunchMode | BrowserChoice | TrustMode | str,
    field_name: str,
) -> LaunchMode | BrowserChoice | TrustMode:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(str(value).strip().lower())
    except ValueError as exc:
        valid = ", ".join(item.value for item in enum_type)
        raise ConfigurationError(
            f"Invalid {field_name}: {value!r}. Expected one of: {valid}."
        ) from exc


def _normalize_launch_mode(value: LaunchMode | str) -> LaunchMode:
    return cast(LaunchMode, _normalize_enum(LaunchMode, value, "mode"))


def _normalize_browser_choice(value: BrowserChoice | str) -> BrowserChoice:
    return cast(BrowserChoice, _normalize_enum(BrowserChoice, value, "browser"))


def _normalize_trust_mode(value: TrustMode | str) -> TrustMode:
    return cast(TrustMode, _normalize_enum(TrustMode, value, "trust_mode"))


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


def _validate_webapp_headless(
    mode: LaunchMode,
    headless: bool | None,
    streamlit_flags: MappingProxyType[str, object] | tuple[str, ...],
    streamlit_args: tuple[str, ...],
) -> None:
    if mode != LaunchMode.WEBAPP or headless is not False:
        return
    if _has_streamlit_flag(streamlit_flags, "server.headless") or _has_streamlit_flag(
        streamlit_args, "server.headless"
    ):
        return
    raise ConfigurationError(
        "mode='webapp' requires headless=True. Use browser mode or pass "
        "an explicit Streamlit server.headless flag if you intentionally need "
        "Streamlit-native override behavior."
    )


def _has_streamlit_flag(
    flags: MappingProxyType[str, object] | tuple[str, ...],
    name: str,
) -> bool:
    if isinstance(flags, Mapping):
        return any(_normalize_flag_name(key) == name for key in flags)
    return any(
        _normalize_flag_name(item) == name
        for item in flags
        if str(item).strip().startswith("--")
    )


def _normalize_flag_name(name: str) -> str:
    stripped = str(name).strip()
    if stripped.startswith("--"):
        stripped = stripped[2:]
    return stripped.split("=", 1)[0].strip().lower()
