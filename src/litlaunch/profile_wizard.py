"""Interactive profile wizard for LitLaunch CLI tooling."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from litlaunch.config import BrowserChoice, LauncherConfig, LaunchMode
from litlaunch.exceptions import ConfigurationError
from litlaunch.profile_detection import detect_app_root
from litlaunch.profile_writer import ProfileWriteResult, write_litlaunch_profile
from litlaunch.profiles import LaunchProfile, load_profiles
from litlaunch.windowing import WindowMonitorConfig

InputFunc = Callable[[], str]


@dataclass(frozen=True)
class ProfileWizardOptions:
    """Prefilled options for ``litlaunch create profile``."""

    name: str | None = None
    app_path: str | Path | None = None
    config_path: str | Path | None = None
    dry_run: bool = False
    force: bool = False


def run_profile_wizard(
    options: ProfileWizardOptions,
    *,
    stream: TextIO,
    platform_is_windows: bool,
    input_func: InputFunc | None = None,
) -> ProfileWriteResult | None:
    """Run the interactive profile wizard."""

    if input_func is None:
        input_func = input
    detection = detect_app_root()
    config_path = (
        Path(options.config_path) if options.config_path else detection.config_path
    )
    _write(stream, "LitLaunch create profile")
    _write(stream, "")
    mode = _choose(
        stream,
        input_func,
        "Setup mode",
        (("simple", "Simple"), ("advanced", "Advanced")),
        default="simple",
    )
    if mode == "advanced":
        _write(stream, "Advanced mode is not implemented yet.")
        return None

    profile_name = _ask_profile_name(
        stream,
        input_func,
        default=options.name or detection.suggested_profile_name,
        existing_names=_existing_profile_names(config_path, detection),
        force=options.force,
    )
    app_path = _ask_app_path(
        stream,
        input_func,
        default=Path(options.app_path) if options.app_path else detection.app_path,
    )
    title = _ask(
        stream,
        input_func,
        "App title",
        default=detection.suggested_title,
        validator=_nonempty,
    )
    launch_experience = _choose(
        stream,
        input_func,
        "Launch experience",
        (
            ("webapp", "App window, recommended"),
            ("browser", "Browser tab"),
        ),
        default="webapp",
    )
    browser = _choose(
        stream,
        input_func,
        "Browser",
        (
            ("auto", "auto"),
            ("edge", "edge"),
            ("chrome", "chrome"),
            ("default", "default"),
        ),
        default="auto",
    )
    monitor_window = False
    graceful_timeout = 3.0
    monitor_config = WindowMonitorConfig()
    if launch_experience == "webapp":
        monitor_default = platform_is_windows
        monitor_window = _ask_bool(
            stream,
            input_func,
            "Monitor app window close",
            default=monitor_default,
        )
        if monitor_window:
            graceful_timeout = 15.0
            monitor_config = WindowMonitorConfig(
                appear_timeout_seconds=60.0,
                poll_interval_seconds=1.0,
                stable_poll_count=2,
            )

    config = LauncherConfig(
        app_path=app_path,
        title=title,
        mode=LaunchMode.WEBAPP if launch_experience == "webapp" else LaunchMode.BROWSER,
        browser=BrowserChoice(browser),
        host="127.0.0.1",
        port=None,
        auto_port=True,
        allow_browser_fallback=True,
    )
    profile = LaunchProfile(
        name=profile_name,
        config=config,
        monitor_window=monitor_window,
        graceful_timeout_seconds=graceful_timeout,
        window_monitor_config=monitor_config,
    )
    config_path = Path(
        _ask(
            stream,
            input_func,
            "Output config file",
            default=str(config_path),
            validator=_litlaunch_toml_path,
        )
    )
    _preview_profile(
        stream,
        profile,
        config_path=config_path,
        launch_experience=launch_experience,
    )
    if not _ask_bool(stream, input_func, "Write profile", default=True):
        _write(stream, "Profile creation cancelled.")
        return None
    result = write_litlaunch_profile(
        profile,
        config_path,
        force=options.force,
        dry_run=options.dry_run,
    )
    if options.dry_run:
        _write(stream, "")
        _write(stream, result.toml.rstrip())
        _write(stream, "")
        _write(stream, "Dry run complete; no files were written.")
    else:
        _write(stream, f"Wrote profile {profile.name!r} to {result.path}.")
    return result


def _ask_profile_name(
    stream: TextIO,
    input_func: InputFunc,
    *,
    default: str,
    existing_names: set[str],
    force: bool,
) -> str:
    while True:
        value = _ask(stream, input_func, "Profile name", default=default)
        try:
            LaunchProfile(name=value, config=LauncherConfig(app_path="app.py"))
        except ConfigurationError as exc:
            _write(stream, f"Invalid profile name: {exc}")
            continue
        if value in existing_names and not force:
            _write(
                stream,
                f"Profile {value!r} already exists. Use --force to overwrite.",
            )
            continue
        return value


def _existing_profile_names(config_path: Path, detection) -> set[str]:
    if config_path == detection.config_path:
        return set(detection.existing_profile_names)
    if not config_path.is_file():
        return set()
    return set(load_profiles(config_path))


def _ask_app_path(
    stream: TextIO,
    input_func: InputFunc,
    *,
    default: Path | None,
) -> Path:
    while True:
        value = _ask(
            stream,
            input_func,
            "App path",
            default=str(default) if default is not None else None,
        )
        path = Path(value)
        if path.is_file():
            return path
        _write(stream, f"App path does not exist: {path}")


def _choose(
    stream: TextIO,
    input_func: InputFunc,
    label: str,
    choices: tuple[tuple[str, str], ...],
    *,
    default: str,
) -> str:
    choice_map = {str(index): value for index, (value, _) in enumerate(choices, 1)}
    choice_map.update({value: value for value, _ in choices})
    while True:
        _write(stream, f"{label}:")
        for index, (value, text) in enumerate(choices, 1):
            suffix = " (default)" if value == default else ""
            recommended = (
                " (recommended)"
                if value == "webapp" and "recommended" not in text.lower()
                else ""
            )
            _write(stream, f"  {index}. {text}{recommended}{suffix}")
        answer = input_func().strip().lower()
        if not answer:
            return default
        if answer in choice_map:
            return choice_map[answer]
        _write(stream, f"Choose one of: {', '.join(choice_map)}")


def _ask_bool(
    stream: TextIO,
    input_func: InputFunc,
    label: str,
    *,
    default: bool,
) -> bool:
    suffix = "Y/n" if default else "y/N"
    while True:
        _write(stream, f"{label} [{suffix}]")
        answer = input_func().strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        _write(stream, "Answer yes or no.")


def _ask(
    stream: TextIO,
    input_func: InputFunc,
    label: str,
    *,
    default: str | None = None,
    validator: Callable[[str], str] | None = None,
) -> str:
    prompt = f"{label}"
    if default is not None:
        prompt += f" [{default}]"
    _write(stream, prompt)
    value = input_func().strip() or (default or "")
    if validator is None:
        return value
    return validator(value)


def _preview_profile(
    stream: TextIO,
    profile: LaunchProfile,
    *,
    config_path: Path,
    launch_experience: str,
) -> None:
    _write(stream, "")
    _write(stream, "Profile preview")
    _write(stream, f"Profile: {profile.name}")
    _write(stream, f"Config: {config_path}")
    _write(stream, f"App: {profile.config.app_path}")
    _write(stream, f"Title: {profile.config.title}")
    label = "App window" if launch_experience == "webapp" else "Browser tab"
    _write(stream, f"Launch experience: {label}")
    _write(stream, f"Browser: {profile.config.browser.value}")
    monitor_status = "enabled" if profile.monitor_window else "disabled"
    _write(stream, f"Monitor window: {monitor_status}")
    _write(stream, "Port: auto")
    _write(stream, "Browser fallback: enabled")
    _write(stream, "")


def _nonempty(value: str) -> str:
    if not value.strip():
        raise ConfigurationError("value cannot be empty.")
    return value.strip()


def _litlaunch_toml_path(value: str) -> str:
    path = Path(value)
    if path.name != "litlaunch.toml":
        raise ConfigurationError("create profile writes only litlaunch.toml.")
    return value


def _write(stream: TextIO, message: str) -> None:
    stream.write(f"{message}\n")
    flush = getattr(stream, "flush", None)
    if callable(flush):
        flush()
