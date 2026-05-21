"""Small TOML writer for LitLaunch-owned profile files."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from litlaunch.exceptions import ConfigurationError
from litlaunch.profiles import LaunchProfile, load_profile, load_profiles
from litlaunch.windowing import WindowMonitorConfig

try:  # pragma: no cover - exercised on Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:  # pragma: no cover - environment-specific
        tomllib = None  # type: ignore[assignment]


@dataclass(frozen=True)
class ProfileWriteResult:
    """Result from writing or previewing a LitLaunch profile."""

    path: Path
    toml: str
    profile: LaunchProfile


def write_litlaunch_profile(
    profile: LaunchProfile,
    path: str | Path,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> ProfileWriteResult:
    """Write one profile to a LitLaunch-owned ``litlaunch.toml`` file."""

    config_path = Path(path)
    if config_path.name != "litlaunch.toml":
        raise ConfigurationError(
            "create profile writes only litlaunch.toml in this pass."
        )
    existing_profiles = _read_existing_profiles(config_path)
    if profile.name in existing_profiles and not force:
        raise ConfigurationError(
            f"Profile {profile.name!r} already exists in {config_path}. "
            "Use --force to overwrite it."
        )
    profiles = {**existing_profiles, profile.name: profile}
    toml = render_litlaunch_profiles_toml(profiles, base_dir=config_path.parent)
    if not dry_run:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(toml, encoding="utf-8")
        load_profile(profile.name, config_path)
    else:
        _validate_rendered_profile(profile.name, toml, config_path)
    return ProfileWriteResult(path=config_path, toml=toml, profile=profile)


def render_litlaunch_profiles_toml(
    profiles: Mapping[str, LaunchProfile],
    *,
    base_dir: Path,
) -> str:
    """Render LitLaunch profiles as stable, human-readable TOML."""

    blocks = [
        _render_profile(name, profile, base_dir=base_dir)
        for name, profile in sorted(profiles.items())
    ]
    return "\n\n".join(blocks).rstrip() + "\n"


def _read_existing_profiles(path: Path) -> dict[str, LaunchProfile]:
    if not path.exists():
        return {}
    if tomllib is None:
        raise ConfigurationError(
            "TOML profile writing requires Python 3.11+ or tomli on Python 3.10."
        )
    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except tomllib.TOMLDecodeError as exc:  # type: ignore[union-attr]
        raise ConfigurationError(f"Invalid TOML in {path}: {exc}") from exc
    if set(data) - {"profiles"}:
        raise ConfigurationError(
            f"{path} contains non-profile TOML content. "
            "Use a LitLaunch-owned litlaunch.toml or --dry-run and paste manually."
        )
    if not data.get("profiles"):
        return {}
    return load_profiles(path)


def _render_profile(name: str, profile: LaunchProfile, *, base_dir: Path) -> str:
    config = profile.config
    profile_header = f"profiles.{_toml_string(name)}"
    lines = [f"[{profile_header}]"]
    lines.append(f"app_path = {_toml_string(_display_path(config.app_path, base_dir))}")
    lines.append(f"title = {_toml_string(config.title)}")
    lines.append(f'mode = "{config.mode.value}"')
    lines.append(f'browser = "{config.browser.value}"')
    if config.host != "127.0.0.1":
        lines.append(f"host = {_toml_string(config.host)}")
    if config.port is not None:
        lines.append(f"port = {config.port}")
    if config.auto_port is not True:
        lines.append(f"auto_port = {_toml_bool(config.auto_port)}")
    if config.headless is not None:
        lines.append(f"headless = {_toml_bool(config.headless)}")
    if config.allow_browser_fallback is not True:
        lines.append(
            f"allow_browser_fallback = {_toml_bool(config.allow_browser_fallback)}"
        )
    if config.cwd is not None:
        lines.append(f"cwd = {_toml_string(_display_path(config.cwd, base_dir))}")
    if config.streamlit_args:
        lines.append(f"streamlit_args = {_toml_array(config.streamlit_args)}")
    if config.app_args:
        lines.append(f"app_args = {_toml_array(config.app_args)}")
    if config.extra_browser_args:
        lines.append(f"extra_browser_args = {_toml_array(config.extra_browser_args)}")
    if profile.graceful_timeout_seconds != 3.0:
        lines.append(f"graceful_timeout = {profile.graceful_timeout_seconds:g}")
    if config.extra_env:
        lines.extend(("", f"[{profile_header}.extra_env]"))
        lines.extend(
            f"{key} = {_toml_string(value)}"
            for key, value in sorted(config.extra_env.items())
        )
    if isinstance(config.streamlit_flags, Mapping) and config.streamlit_flags:
        lines.extend(("", f"[{profile_header}.streamlit_flags]"))
        lines.extend(
            f"{_toml_key(str(key))} = {_toml_value(value)}"
            for key, value in sorted(config.streamlit_flags.items())
        )
    elif config.streamlit_flags:
        lines.append(f"streamlit_flags = {_toml_array(config.streamlit_flags)}")
    if profile.monitor_window or profile.window_monitor_config != WindowMonitorConfig():
        monitor = profile.window_monitor_config
        lines.extend(("", f"[{profile_header}.window_monitor]"))
        lines.append(f"enabled = {_toml_bool(profile.monitor_window)}")
        lines.append(f"appear_timeout = {monitor.appear_timeout_seconds:g}")
        lines.append(f"poll_interval = {monitor.poll_interval_seconds:g}")
        lines.append(f"stable_polls = {monitor.stable_poll_count}")
    return "\n".join(lines)


def _validate_rendered_profile(name: str, toml: str, path: Path) -> None:
    from tempfile import TemporaryDirectory

    with TemporaryDirectory(prefix="litlaunch-profile-preview-") as directory:
        preview_path = Path(directory) / path.name
        preview_path.write_text(toml, encoding="utf-8")
        load_profile(name, preview_path)


def _display_path(path: Path, base_dir: Path) -> str:
    try:
        return os.path.relpath(path, base_dir)
    except ValueError:
        return str(path)


def _toml_key(value: str) -> str:
    if value.replace("_", "").isalnum():
        return value
    return _toml_string(value)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return _toml_bool(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:g}" if isinstance(value, float) else str(value)
    if value is None:
        return '""'
    return _toml_string(str(value))


def _toml_array(values) -> str:
    return "[" + ", ".join(_toml_string(str(value)) for value in values) + "]"


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
