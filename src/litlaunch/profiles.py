"""Project launch profile loading for LitLaunch."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from litlaunch.config import LauncherConfig
from litlaunch.exceptions import ConfigurationError
from litlaunch.windowing import WindowMonitorConfig

try:  # pragma: no cover - exercised on Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:  # pragma: no cover - environment-specific
        tomllib = None  # type: ignore[assignment]


PROFILE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
LITLAUNCH_TOML = "litlaunch.toml"
PYPROJECT_TOML = "pyproject.toml"

CONFIG_FIELDS = {
    "app_path",
    "title",
    "mode",
    "browser",
    "host",
    "port",
    "auto_port",
    "headless",
    "allow_browser_fallback",
    "allow_network_exposure",
    "trust_mode",
    "cwd",
    "extra_env",
    "runtime_event_log",
    "streamlit_flags",
    "streamlit_args",
    "app_args",
    "extra_browser_args",
}
RUNTIME_FIELDS = {
    "graceful_timeout",
    "window_monitor",
    "browser_window_monitor",
}
WINDOW_MONITOR_FIELDS = {
    "enabled",
    "appear_timeout",
    "poll_interval",
    "stable_polls",
}


@dataclass(frozen=True)
class LaunchProfile:
    """Reusable launch/runtime configuration loaded from project TOML."""

    name: str
    config: LauncherConfig
    monitor_window: bool = False
    monitor_browser_window: bool = False
    graceful_timeout_seconds: float = 3.0
    window_monitor_config: WindowMonitorConfig = field(
        default_factory=WindowMonitorConfig
    )
    browser_window_monitor_config: WindowMonitorConfig = field(
        default_factory=lambda: WindowMonitorConfig(require_app_mode=False)
    )

    def __post_init__(self) -> None:
        name = _normalize_profile_name(self.name)
        graceful_timeout = float(self.graceful_timeout_seconds)
        if graceful_timeout <= 0:
            raise ConfigurationError("profile graceful_timeout must be positive.")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "monitor_window", bool(self.monitor_window))
        object.__setattr__(
            self,
            "monitor_browser_window",
            bool(self.monitor_browser_window),
        )
        object.__setattr__(self, "graceful_timeout_seconds", graceful_timeout)


def load_profiles(
    config_path: str | Path | None = None,
    *,
    cwd: str | Path | None = None,
) -> dict[str, LaunchProfile]:
    """Load all LitLaunch profiles from an explicit or discovered TOML file."""

    source = _resolve_profile_source(config_path, cwd=cwd)
    if source is None:
        return {}
    table = _load_profile_table(source)
    return {
        name: _profile_from_mapping(name, values, base_dir=source.parent)
        for name, values in table.items()
    }


def load_profile(
    name: str,
    config_path: str | Path | None = None,
    *,
    cwd: str | Path | None = None,
) -> LaunchProfile:
    """Load one named LitLaunch profile."""

    profile_name = _normalize_profile_name(name)
    profiles = load_profiles(config_path, cwd=cwd)
    try:
        return profiles[profile_name]
    except KeyError as exc:
        available = ", ".join(sorted(profiles)) or "none"
        raise ConfigurationError(
            f"LitLaunch profile {profile_name!r} was not found. "
            f"Available profiles: {available}."
        ) from exc


def _resolve_profile_source(
    config_path: str | Path | None,
    *,
    cwd: str | Path | None,
) -> Path | None:
    if config_path is not None:
        path = Path(config_path)
        if not path.is_file():
            raise ConfigurationError(f"LitLaunch profile config not found: {path}")
        return path.resolve()

    root = Path.cwd() if cwd is None else Path(cwd)
    candidates = []
    for filename in (LITLAUNCH_TOML, PYPROJECT_TOML):
        path = root / filename
        if path.is_file() and _load_profile_table(path, missing_ok=True):
            candidates.append(path.resolve())

    if len(candidates) > 1:
        names = ", ".join(path.name for path in candidates)
        raise ConfigurationError(
            "Ambiguous LitLaunch profile configuration. "
            f"Found profiles in: {names}. Use --config to choose one."
        )
    return candidates[0] if candidates else None


def _load_profile_table(
    path: Path,
    *,
    missing_ok: bool = False,
) -> Mapping[str, Any]:
    data = _read_toml(path)
    if path.name == PYPROJECT_TOML:
        table = data.get("tool", {}).get("litlaunch", {}).get("profiles", {})
    else:
        table = data.get("profiles", {})

    if table is None:
        return {}
    if not isinstance(table, Mapping):
        raise ConfigurationError(f"LitLaunch profiles in {path} must be a table.")
    if not table and not missing_ok:
        raise ConfigurationError(f"No LitLaunch profiles found in {path}.")
    return table


def _read_toml(path: Path) -> Mapping[str, Any]:
    if tomllib is None:
        raise ConfigurationError(
            "TOML profile loading requires Python 3.11+ or the optional tomli "
            "package on Python 3.10."
        )
    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except tomllib.TOMLDecodeError as exc:  # type: ignore[union-attr]
        raise ConfigurationError(f"Invalid TOML in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigurationError(
            f"Could not read LitLaunch profile config {path}: {exc}"
        ) from exc
    if not isinstance(data, Mapping):
        raise ConfigurationError(f"TOML document {path} must contain tables.")
    return data


def _profile_from_mapping(
    name: str,
    values: Any,
    *,
    base_dir: Path,
) -> LaunchProfile:
    profile_name = _normalize_profile_name(name)
    if not isinstance(values, Mapping):
        raise ConfigurationError(f"Profile {profile_name!r} must be a table.")

    unknown = set(values) - CONFIG_FIELDS - RUNTIME_FIELDS
    if unknown:
        unknown_text = ", ".join(sorted(str(item) for item in unknown))
        raise ConfigurationError(
            f"Profile {profile_name!r} has unknown fields: {unknown_text}."
        )

    if "app_path" not in values:
        raise ConfigurationError(f"Profile {profile_name!r} requires app_path.")

    config_values = {key: values[key] for key in CONFIG_FIELDS if key in values}
    config_values["app_path"] = _profile_path(config_values["app_path"], base_dir)
    if "cwd" in config_values and config_values["cwd"] is not None:
        config_values["cwd"] = _profile_path(config_values["cwd"], base_dir)
    if (
        "runtime_event_log" in config_values
        and config_values["runtime_event_log"] is not None
    ):
        config_values["runtime_event_log"] = _profile_path(
            config_values["runtime_event_log"],
            base_dir,
        )

    window_values = values.get("window_monitor", {})
    if window_values is None:
        window_values = {}
    if not isinstance(window_values, Mapping):
        raise ConfigurationError(
            f"Profile {profile_name!r} window_monitor must be a table."
        )
    unknown_window = set(window_values) - WINDOW_MONITOR_FIELDS
    if unknown_window:
        unknown_text = ", ".join(sorted(str(item) for item in unknown_window))
        raise ConfigurationError(
            f"Profile {profile_name!r} window_monitor has unknown fields: "
            f"{unknown_text}."
        )

    try:
        monitor_config = WindowMonitorConfig(
            appear_timeout_seconds=float(window_values.get("appear_timeout", 60.0)),
            poll_interval_seconds=float(window_values.get("poll_interval", 1.0)),
            stable_poll_count=int(window_values.get("stable_polls", 2)),
        )
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(
            f"Profile {profile_name!r} has invalid window_monitor settings: {exc}"
        ) from exc

    browser_window_values = values.get("browser_window_monitor", {})
    if browser_window_values is None:
        browser_window_values = {}
    if not isinstance(browser_window_values, Mapping):
        raise ConfigurationError(
            f"Profile {profile_name!r} browser_window_monitor must be a table."
        )
    unknown_browser_window = set(browser_window_values) - WINDOW_MONITOR_FIELDS
    if unknown_browser_window:
        unknown_text = ", ".join(sorted(str(item) for item in unknown_browser_window))
        raise ConfigurationError(
            f"Profile {profile_name!r} browser_window_monitor has unknown fields: "
            f"{unknown_text}."
        )

    try:
        browser_window_monitor_config = WindowMonitorConfig(
            appear_timeout_seconds=float(
                browser_window_values.get("appear_timeout", 8.0)
            ),
            poll_interval_seconds=float(
                browser_window_values.get("poll_interval", 0.25)
            ),
            stable_poll_count=int(browser_window_values.get("stable_polls", 2)),
            require_app_mode=False,
        )
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(
            f"Profile {profile_name!r} has invalid browser_window_monitor "
            f"settings: {exc}"
        ) from exc

    return LaunchProfile(
        name=profile_name,
        config=LauncherConfig(**config_values),
        monitor_window=bool(window_values.get("enabled", False)),
        monitor_browser_window=bool(browser_window_values.get("enabled", False)),
        graceful_timeout_seconds=float(values.get("graceful_timeout", 3.0)),
        window_monitor_config=monitor_config,
        browser_window_monitor_config=browser_window_monitor_config,
    )


def _profile_path(value: Any, base_dir: Path) -> Path:
    path = Path(str(value).strip())
    if not str(path):
        raise ConfigurationError("profile path values cannot be empty.")
    return path if path.is_absolute() else base_dir / path


def _normalize_profile_name(name: str) -> str:
    normalized = str(name).strip()
    if not normalized:
        raise ConfigurationError("profile name cannot be empty.")
    if not PROFILE_NAME_PATTERN.fullmatch(normalized):
        raise ConfigurationError(
            "profile name must contain only letters, numbers, dots, underscores, "
            "or hyphens."
        )
    return normalized
