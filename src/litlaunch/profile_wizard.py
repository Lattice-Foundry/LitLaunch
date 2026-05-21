"""Interactive profile wizard for LitLaunch CLI tooling."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from litlaunch.colors import THEME_COLORS, streamlit_blue, terminal_green
from litlaunch.config import BrowserChoice, LauncherConfig, LaunchMode
from litlaunch.exceptions import ConfigurationError
from litlaunch.profile_detection import AppRootDetection, detect_app_root
from litlaunch.profile_writer import ProfileWriteResult, write_litlaunch_profile
from litlaunch.profiles import LaunchProfile, load_profiles
from litlaunch.windowing import WindowMonitorConfig

InputFunc = Callable[[], str]

BACK_COMMANDS = {"back", "b"}
QUIT_COMMANDS = {"quit", "q", "exit", "cancel"}


class ProfileWizardCancelled(Exception):
    """Raised when profile creation is cancelled by the user."""


class _WizardBack(Exception):
    """Internal control flow for moving to the previous wizard step."""


class _WizardQuit(Exception):
    """Internal control flow for clean wizard cancellation."""


@dataclass(frozen=True)
class ProfileWizardOptions:
    """Prefilled options for ``litlaunch create profile``."""

    name: str | None = None
    app_path: str | Path | None = None
    config_path: str | Path | None = None
    dry_run: bool = False
    force: bool = False
    use_color: bool = True


@dataclass
class _WizardState:
    detection: AppRootDetection
    config_path: Path
    existing_names: set[str]
    setup_mode: str | None = None
    profile_name: str | None = None
    app_path: Path | None = None
    title: str | None = None
    launch_experience: str | None = None
    browser: str | None = None
    monitor_window: bool | None = None
    graceful_timeout: float = 3.0
    monitor_config: WindowMonitorConfig = WindowMonitorConfig()
    force: bool = False
    write_confirmed: bool = False


@dataclass(frozen=True)
class _WizardStep:
    title: str
    handler: Callable[[_WizardState, _WizardIo], None]
    skip: Callable[[_WizardState], bool] = lambda _state: False


@dataclass(frozen=True)
class _WizardIo:
    stream: TextIO
    input_func: InputFunc
    use_color: bool


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
    io = _WizardIo(
        stream=stream,
        input_func=input_func,
        use_color=options.use_color,
    )
    try:
        return _run_profile_wizard(options, io, platform_is_windows=platform_is_windows)
    except (KeyboardInterrupt, _WizardQuit) as exc:
        _write_warning_status(stream, "Profile creation cancelled.")
        raise ProfileWizardCancelled from exc


def _run_profile_wizard(
    options: ProfileWizardOptions,
    io: _WizardIo,
    *,
    platform_is_windows: bool,
) -> ProfileWriteResult | None:
    detection = detect_app_root()
    config_path = (
        Path(options.config_path) if options.config_path else detection.config_path
    )
    state = _WizardState(
        detection=detection,
        config_path=config_path,
        existing_names=_existing_profile_names(config_path, detection),
        profile_name=options.name,
        app_path=Path(options.app_path) if options.app_path else detection.app_path,
        title=detection.suggested_title,
        launch_experience="webapp",
        browser="auto",
        monitor_window=platform_is_windows,
        force=options.force,
    )
    steps = _simple_mode_steps(platform_is_windows=platform_is_windows)

    _render_header(io)
    index = 0
    while index < len(steps):
        if steps[index].skip(state):
            index += 1
            continue
        _render_step_header(io, state, steps, index)
        try:
            steps[index].handler(state, io)
            if index == 0 and state.setup_mode == "advanced":
                _write(io.stream, "Advanced mode is not implemented yet.")
                return None
            index += 1
        except _WizardBack:
            previous_index = _previous_step_index(steps, state, index)
            if previous_index == index:
                _write(io.stream, "Already at the first step.")
            index = previous_index

    if state.setup_mode == "advanced":
        _write(io.stream, "Advanced mode is not implemented yet.")
        return None
    if not state.write_confirmed:
        _write(io.stream, "Profile creation cancelled.")
        return None

    profile = _build_profile(state)
    result = write_litlaunch_profile(
        profile,
        state.config_path,
        force=options.force,
        dry_run=options.dry_run,
    )
    if options.dry_run:
        _write(io.stream, "")
        _write(io.stream, result.toml.rstrip())
        _write(io.stream, "")
        _write(io.stream, "Dry run complete; no files were written.")
    else:
        _write(io.stream, f"Wrote profile {profile.name!r} to {result.path}.")
    return result


def _simple_mode_steps(*, platform_is_windows: bool) -> tuple[_WizardStep, ...]:
    return (
        _WizardStep("Setup mode", _step_setup_mode),
        _WizardStep("Profile name", _step_profile_name),
        _WizardStep("App path", _step_app_path),
        _WizardStep("App title", _step_title),
        _WizardStep("Launch experience", _step_launch_experience),
        _WizardStep("Browser", _step_browser),
        _WizardStep(
            "Monitor window",
            lambda state, io: _step_monitor_window(
                state,
                io,
                platform_is_windows=platform_is_windows,
            ),
            skip=lambda state: state.launch_experience != "webapp",
        ),
        _WizardStep("Output config file", _step_config_path),
        _WizardStep("Preview and confirm", _step_preview_confirm),
    )


def _step_setup_mode(state: _WizardState, io: _WizardIo) -> None:
    state.setup_mode = _choose(
        io,
        "Setup mode",
        (("simple", "Simple"), ("advanced", "Advanced")),
        default=state.setup_mode or "simple",
    )


def _step_profile_name(state: _WizardState, io: _WizardIo) -> None:
    while True:
        value = _ask(
            io,
            "Profile name",
            default=state.profile_name or state.detection.suggested_profile_name,
        )
        try:
            LaunchProfile(name=value, config=LauncherConfig(app_path="app.py"))
        except ConfigurationError as exc:
            _write(io.stream, f"Invalid profile name: {exc}")
            continue
        if value in state.existing_names and not state.force:
            _write(
                io.stream,
                f"Profile {value!r} already exists. Use --force to overwrite.",
            )
            continue
        state.profile_name = value
        return


def _step_app_path(state: _WizardState, io: _WizardIo) -> None:
    while True:
        value = _ask(
            io,
            "App path",
            default=str(state.app_path) if state.app_path is not None else None,
        )
        path = Path(value)
        if path.is_file():
            state.app_path = path
            return
        _write(io.stream, f"App path does not exist: {path}.")


def _step_title(state: _WizardState, io: _WizardIo) -> None:
    state.title = _ask(
        io,
        "App title",
        default=state.title or state.detection.suggested_title,
        validator=_nonempty,
    )


def _step_launch_experience(state: _WizardState, io: _WizardIo) -> None:
    state.launch_experience = _choose(
        io,
        "Launch experience",
        (
            ("webapp", "App window, recommended"),
            ("browser", "Browser tab"),
        ),
        default=state.launch_experience or "webapp",
    )
    if state.launch_experience != "webapp":
        state.monitor_window = False
        state.graceful_timeout = 3.0
        state.monitor_config = WindowMonitorConfig()


def _step_browser(state: _WizardState, io: _WizardIo) -> None:
    state.browser = _choose(
        io,
        "Browser",
        (
            ("auto", "auto"),
            ("edge", "edge"),
            ("chrome", "chrome"),
            ("default", "default"),
        ),
        default=state.browser or "auto",
    )


def _step_monitor_window(
    state: _WizardState,
    io: _WizardIo,
    *,
    platform_is_windows: bool,
) -> None:
    if state.monitor_window is None:
        default = platform_is_windows
    else:
        default = state.monitor_window
    state.monitor_window = _ask_bool(
        io,
        "Monitor app window close",
        default=bool(default),
    )
    if state.monitor_window:
        state.graceful_timeout = 15.0
        state.monitor_config = WindowMonitorConfig(
            appear_timeout_seconds=60.0,
            poll_interval_seconds=1.0,
            stable_poll_count=2,
        )
    else:
        state.graceful_timeout = 3.0
        state.monitor_config = WindowMonitorConfig()


def _step_config_path(state: _WizardState, io: _WizardIo) -> None:
    state.config_path = Path(
        _ask(
            io,
            "Output config file",
            default=str(state.config_path),
            validator=_litlaunch_toml_path,
        )
    )
    state.existing_names = _existing_profile_names(state.config_path, state.detection)


def _step_preview_confirm(state: _WizardState, io: _WizardIo) -> None:
    profile = _build_profile(state)
    _preview_profile(
        io.stream,
        profile,
        config_path=state.config_path,
        launch_experience=state.launch_experience or "webapp",
    )
    state.write_confirmed = _ask_bool(io, "Write profile", default=True)


def _build_profile(state: _WizardState) -> LaunchProfile:
    if state.profile_name is None:
        raise ConfigurationError("profile name is required.")
    if state.app_path is None:
        raise ConfigurationError("app path is required.")
    title = state.title or state.detection.suggested_title
    launch_experience = state.launch_experience or "webapp"
    browser = state.browser or "auto"
    config = LauncherConfig(
        app_path=state.app_path,
        title=title,
        mode=LaunchMode.WEBAPP if launch_experience == "webapp" else LaunchMode.BROWSER,
        browser=BrowserChoice(browser),
        host="127.0.0.1",
        port=None,
        auto_port=True,
        allow_browser_fallback=True,
    )
    return LaunchProfile(
        name=state.profile_name,
        config=config,
        monitor_window=bool(state.monitor_window),
        graceful_timeout_seconds=state.graceful_timeout,
        window_monitor_config=state.monitor_config,
    )


def _existing_profile_names(config_path: Path, detection: AppRootDetection) -> set[str]:
    if config_path == detection.config_path:
        return set(detection.existing_profile_names)
    if not config_path.is_file():
        return set()
    return set(load_profiles(config_path))


def _choose(
    io: _WizardIo,
    label: str,
    choices: tuple[tuple[str, str], ...],
    *,
    default: str,
) -> str:
    choice_map = {str(index): value for index, (value, _) in enumerate(choices, 1)}
    choice_map.update({value: value for value, _ in choices})
    while True:
        _write(io.stream, f"{label}:")
        for index, (value, text) in enumerate(choices, 1):
            suffix = " (default)" if value == default else ""
            recommended = (
                " (recommended)"
                if value == "webapp" and "recommended" not in text.lower()
                else ""
            )
            _write(io.stream, f"  {index}. {text}{recommended}{suffix}")
        _write(io.stream, "Selection:")
        answer = _read_answer(io).strip().lower()
        if not answer:
            return default
        if answer in choice_map:
            return choice_map[answer]
        _write(io.stream, f"Choose one of: {', '.join(choice_map)}.")


def _ask_bool(
    io: _WizardIo,
    label: str,
    *,
    default: bool,
) -> bool:
    suffix = "Y/n" if default else "y/N"
    while True:
        answer = _ask(io, label, default=suffix, raw_default=True).strip().lower()
        if not answer or answer == suffix.lower():
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        _write(io.stream, "Answer yes or no.")


def _ask(
    io: _WizardIo,
    label: str,
    *,
    default: str | None = None,
    validator: Callable[[str], str] | None = None,
    raw_default: bool = False,
) -> str:
    prompt = f"{label}"
    if default is not None:
        prompt += f" [{default}]"
    prompt = f"Selection: {prompt}:"
    _write(io.stream, prompt)
    answer = _read_answer(io)
    value = answer.strip() if answer.strip() else (default or "")
    if raw_default and value == (default or ""):
        return answer.strip()
    if validator is None:
        return value
    return validator(value)


def _read_answer(io: _WizardIo) -> str:
    answer = io.input_func()
    normalized = answer.strip().lower()
    if normalized in BACK_COMMANDS:
        raise _WizardBack
    if normalized in QUIT_COMMANDS:
        raise _WizardQuit
    return answer


def _render_header(io: _WizardIo) -> None:
    _write(io.stream, _style("Create Profile Wizard", streamlit_blue, io.use_color))
    _write(io.stream, _style("Simple Mode", terminal_green, io.use_color))
    _write(io.stream, "Type 'back' to revisit the previous step, or 'quit' to cancel.")
    _write(io.stream, "")


def _render_step_header(
    io: _WizardIo,
    state: _WizardState,
    steps: tuple[_WizardStep, ...],
    index: int,
) -> None:
    visible_steps = [step for step in steps if not step.skip(state)]
    current = sum(1 for step in steps[:index] if not step.skip(state)) + 1
    title = steps[index].title
    _write(
        io.stream,
        _style(
            f"Step {current} of {len(visible_steps)} — {title}",
            streamlit_blue,
            io.use_color,
        ),
    )
    _render_current_data(io, state)


def _render_current_data(io: _WizardIo, state: _WizardState) -> None:
    values = _current_data_values(state)
    if not values:
        return
    _write(io.stream, "Current profile:")
    for label, value in values:
        label_text = _style(f"  {label}:", streamlit_blue, io.use_color)
        value_text = _style(str(value), terminal_green, io.use_color)
        _write(io.stream, f"{label_text} {value_text}")
    _write(io.stream, "")


def _current_data_values(state: _WizardState) -> tuple[tuple[str, str], ...]:
    values: list[tuple[str, str]] = []
    if state.profile_name:
        values.append(("Name", state.profile_name))
    if state.app_path:
        values.append(("App", str(state.app_path)))
    if state.title:
        values.append(("Title", state.title))
    if state.launch_experience:
        launch = "App window" if state.launch_experience == "webapp" else "Browser tab"
        values.append(("Launch", launch))
    if state.browser:
        values.append(("Browser", state.browser))
    if state.launch_experience == "webapp" and state.monitor_window is not None:
        values.append(("Monitor", "enabled" if state.monitor_window else "disabled"))
    if state.config_path:
        values.append(("Config", str(state.config_path)))
    return tuple(values)


def _previous_step_index(
    steps: tuple[_WizardStep, ...],
    state: _WizardState,
    index: int,
) -> int:
    for previous in range(index - 1, -1, -1):
        if not steps[previous].skip(state):
            return previous
    return index


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


def _style(text: str, color_name: str, use_color: bool) -> str:
    if not use_color:
        return text
    color = THEME_COLORS[color_name].ansi
    return f"{color}{text}\033[0m"


def _write_warning_status(stream: TextIO, message: str) -> None:
    _write(stream, f"[  warn  ] {message}")


def _write(stream: TextIO, message: str) -> None:
    stream.write(f"{message}\n")
    flush = getattr(stream, "flush", None)
    if callable(flush):
        flush()
