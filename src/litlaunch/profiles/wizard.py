"""Interactive profile wizard for LitLaunch CLI tooling."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TextIO, TypeVar

from litlaunch.config import BrowserChoice, LauncherConfig, LaunchMode
from litlaunch.exceptions import ConfigurationError
from litlaunch.exposure import classify_host_exposure
from litlaunch.platforms import PlatformInfo
from litlaunch.shortcut_writer import (
    ShortcutRequest,
    build_shortcut_plan,
    write_shortcut,
)
from litlaunch.windowing import WindowMonitorConfig

from .core import LaunchProfile, load_profiles
from .detection import AppRootDetection, detect_app_root
from .rendering import (
    preview_profile as _preview_profile,
)
from .rendering import (
    render_step_header as _render_step_header,
)
from .rendering import (
    write as _write,
)
from .rendering import (
    write_warning_status as _write_warning_status,
)
from .state import (
    BACK_COMMANDS,
    QUIT_COMMANDS,
    InputFunc,
    ProfileWizardCancelled,
    ProfileWizardOptions,
    previous_step_index,
)
from .state import (
    WizardBack as _WizardBack,
)
from .state import (
    WizardIo as _WizardIo,
)
from .state import (
    WizardQuit as _WizardQuit,
)
from .state import (
    WizardState as _WizardState,
)
from .state import (
    WizardStep as _WizardStep,
)
from .writer import ProfileWriteResult, write_litlaunch_profile

_MappingValue = TypeVar("_MappingValue")


def run_profile_wizard(
    options: ProfileWizardOptions,
    *,
    stream: TextIO,
    platform_is_windows: bool,
    platform_info: PlatformInfo | None = None,
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
        return _run_profile_wizard(
            options,
            io,
            platform_is_windows=platform_is_windows,
            platform_info=platform_info,
        )
    except (KeyboardInterrupt, _WizardQuit) as exc:
        _write_warning_status(stream, "Profile creation cancelled.", io.use_color)
        raise ProfileWizardCancelled from exc


def _run_profile_wizard(
    options: ProfileWizardOptions,
    io: _WizardIo,
    *,
    platform_is_windows: bool,
    platform_info: PlatformInfo | None,
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
        app_icon=Path(options.app_icon) if options.app_icon else None,
        title=detection.suggested_title,
        launch_experience="webapp",
        browser="auto",
        monitor_window=platform_is_windows,
        force=options.force,
    )
    steps = _wizard_steps(platform_is_windows=platform_is_windows)

    index = 0
    while index < len(steps):
        if steps[index].skip(state):
            index += 1
            continue
        _render_step_header(io, state, steps, index)
        try:
            steps[index].handler(state, io)
            index += 1
        except _WizardBack:
            previous_index = previous_step_index(steps, state, index)
            if previous_index == index:
                _write(io.stream, "Already at the first step.")
            index = previous_index

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
        _write(
            io.stream,
            "Shortcut creation would be offered after writing the profile.",
        )
    else:
        _write(io.stream, f"Wrote profile {profile.name!r} to {result.path}.")
        _offer_shortcut_creation(io, result.profile, state, platform_info)
    return result


def _wizard_steps(*, platform_is_windows: bool) -> tuple[_WizardStep, ...]:
    return (
        _WizardStep(
            "Setup mode",
            _step_setup_mode,
            "Choose the guided Simple flow or the full Advanced profile surface.",
        ),
        _WizardStep(
            "Profile name",
            _step_profile_name,
            "Name the reusable launch profile you will run with --profile.",
        ),
        _WizardStep(
            "App path",
            _step_app_path,
            "Point LitLaunch at the Streamlit entrypoint for this profile.",
        ),
        _WizardStep(
            "App title",
            _step_title,
            ("Set the title used for shortcuts and monitored app-window matching."),
        ),
        _WizardStep(
            "App icon",
            _step_app_icon,
            ("Optionally set an icon used by LitLaunch-generated native shortcuts."),
            skip=_simple_mode,
        ),
        _WizardStep(
            "Launch experience",
            _step_launch_experience,
            "Choose App window for the polished recommended experience.",
        ),
        _WizardStep(
            "Browser",
            _step_browser,
            "Choose which browser family LitLaunch should prefer.",
        ),
        _WizardStep(
            "Host",
            _step_host,
            "Choose the network interface Streamlit should bind to.",
            skip=_simple_mode,
        ),
        _WizardStep(
            "Port",
            _step_port,
            "Choose a fixed Streamlit port or leave it on automatic selection.",
            skip=_simple_mode,
        ),
        _WizardStep(
            "Auto-port",
            _step_auto_port,
            "Decide whether LitLaunch may move to another port if needed.",
            skip=_simple_mode,
        ),
        _WizardStep(
            "Browser fallback",
            _step_browser_fallback,
            "Allow LitLaunch to fall back if the preferred browser is unavailable.",
            skip=_simple_mode,
        ),
        _WizardStep(
            "Headless",
            _step_headless,
            "Choose whether to override LitLaunch's Streamlit headless default.",
            skip=_simple_mode,
        ),
        _WizardStep(
            "Extra browser args",
            _step_extra_browser_args,
            "Add optional browser command-line arguments for this profile.",
            skip=_simple_mode,
        ),
        _WizardStep(
            "Monitor window",
            lambda state, io: _step_monitor_window(
                state,
                io,
                platform_is_windows=platform_is_windows,
            ),
            "Track the app window so closing it can stop the backend cleanly.",
            skip=lambda state: state.launch_experience != "webapp",
        ),
        _WizardStep(
            "Graceful timeout",
            _step_graceful_timeout,
            "Set how long shutdown cleanup may run before fallback termination.",
            skip=lambda state: _simple_mode(state) or not state.monitor_window,
        ),
        _WizardStep(
            "Monitor appear timeout",
            _step_monitor_appear_timeout,
            "Set how long LitLaunch should wait for the app window to appear.",
            skip=lambda state: _simple_mode(state) or not state.monitor_window,
        ),
        _WizardStep(
            "Monitor poll interval",
            _step_monitor_poll_interval,
            "Set how often LitLaunch checks the monitored app window.",
            skip=lambda state: _simple_mode(state) or not state.monitor_window,
        ),
        _WizardStep(
            "Monitor stable polls",
            _step_monitor_stable_polls,
            "Set how many stable checks confirm the intended app window.",
            skip=lambda state: _simple_mode(state) or not state.monitor_window,
        ),
        _WizardStep(
            "Streamlit flags",
            _step_streamlit_flags,
            "Add Streamlit config flags such as server.maxUploadSize=200.",
            skip=_simple_mode,
        ),
        _WizardStep(
            "Streamlit args",
            _step_streamlit_args,
            "Add raw Streamlit CLI arguments when a flag is not enough.",
            skip=_simple_mode,
        ),
        _WizardStep(
            "App args",
            _step_app_args,
            "Add arguments passed after -- to your Streamlit app.",
            skip=_simple_mode,
        ),
        _WizardStep(
            "Working directory",
            _step_cwd,
            "Choose the working directory used when the profile launches.",
            skip=_simple_mode,
        ),
        _WizardStep(
            "Extra environment",
            _step_extra_env,
            "Add profile-specific environment variables stored in litlaunch.toml.",
            skip=_simple_mode,
        ),
        _WizardStep(
            "Output config file",
            _step_config_path,
            "Choose which litlaunch.toml file will receive the profile.",
        ),
        _WizardStep(
            "Preview and confirm",
            _step_preview_confirm,
            "Review the final profile before LitLaunch writes anything.",
        ),
    )


def _simple_mode(state: _WizardState) -> bool:
    return state.setup_mode != "advanced"


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


def _step_app_icon(state: _WizardState, io: _WizardIo) -> None:
    while True:
        default = "" if state.app_icon is None else str(state.app_icon)
        value = _ask_optional(
            io,
            "App icon path (blank for none)",
            default=default,
        )
        if not value:
            state.app_icon = None
            return
        path = Path(value)
        try:
            LauncherConfig(app_path="app.py", app_icon=path)
        except ConfigurationError as exc:
            _write(io.stream, f"Invalid app icon: {exc}")
            continue
        state.app_icon = path
        return


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


def _step_host(state: _WizardState, io: _WizardIo) -> None:
    while True:
        value = _ask(io, "Host", default=state.host, validator=_nonempty)
        try:
            LauncherConfig(app_path="app.py", host=value)
        except ConfigurationError as exc:
            _write(io.stream, f"Invalid host: {exc}")
            continue
        state.host = value
        exposure = classify_host_exposure(value)
        if exposure.exposed:
            _write_warning_status(io.stream, exposure.warning or "", io.use_color)
            state.allow_network_exposure = _ask_bool(
                io,
                "Acknowledge network exposure for this profile",
                default=False,
            )
            if not state.allow_network_exposure:
                _write(
                    io.stream,
                    (
                        "Use a loopback host such as 127.0.0.1 unless exposure "
                        "is intentional."
                    ),
                )
                continue
        else:
            state.allow_network_exposure = False
        return


def _step_port(state: _WizardState, io: _WizardIo) -> None:
    while True:
        default = "" if state.port is None else str(state.port)
        value = _ask_optional(io, "Port (blank for auto)", default=default)
        if not value:
            state.port = None
            state.auto_port = True
            return
        try:
            port = int(value)
            LauncherConfig(app_path="app.py", port=port)
        except (ConfigurationError, ValueError) as exc:
            _write(io.stream, f"Invalid port: {exc}")
            continue
        state.port = port
        return


def _step_auto_port(state: _WizardState, io: _WizardIo) -> None:
    if state.port is None:
        state.auto_port = True
        _write(io.stream, "Auto-port is enabled because no fixed port is set.")
        return
    state.auto_port = _ask_bool(
        io,
        "Try another port if the requested port is busy",
        default=state.auto_port,
    )


def _step_browser_fallback(state: _WizardState, io: _WizardIo) -> None:
    state.allow_browser_fallback = _ask_bool(
        io,
        "Allow browser fallback",
        default=state.allow_browser_fallback,
    )


def _step_headless(state: _WizardState, io: _WizardIo) -> None:
    choice = _choose(
        io,
        "Streamlit headless setting",
        (
            ("default", "Use LitLaunch default"),
            ("true", "true"),
            ("false", "false"),
        ),
        default="default" if state.headless is None else str(state.headless).lower(),
    )
    state.headless = None if choice == "default" else choice == "true"


def _step_extra_browser_args(state: _WizardState, io: _WizardIo) -> None:
    state.extra_browser_args = _ask_list(
        io,
        "Extra browser arg",
        current=state.extra_browser_args,
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
    _write(
        io.stream,
        (
            "Highly recommended: keep this enabled for app-window profiles "
            "so closing the app window stops the backend cleanly."
        ),
    )
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


def _step_graceful_timeout(state: _WizardState, io: _WizardIo) -> None:
    state.graceful_timeout = _ask_positive_float(
        io,
        "Graceful shutdown timeout seconds",
        default=state.graceful_timeout,
    )


def _step_monitor_appear_timeout(state: _WizardState, io: _WizardIo) -> None:
    monitor = state.monitor_config
    state.monitor_config = WindowMonitorConfig(
        appear_timeout_seconds=_ask_positive_float(
            io,
            "Monitor appear timeout seconds",
            default=monitor.appear_timeout_seconds,
        ),
        poll_interval_seconds=monitor.poll_interval_seconds,
        stable_poll_count=monitor.stable_poll_count,
    )


def _step_monitor_poll_interval(state: _WizardState, io: _WizardIo) -> None:
    monitor = state.monitor_config
    state.monitor_config = WindowMonitorConfig(
        appear_timeout_seconds=monitor.appear_timeout_seconds,
        poll_interval_seconds=_ask_positive_float(
            io,
            "Monitor poll interval seconds",
            default=monitor.poll_interval_seconds,
        ),
        stable_poll_count=monitor.stable_poll_count,
    )


def _step_monitor_stable_polls(state: _WizardState, io: _WizardIo) -> None:
    monitor = state.monitor_config
    state.monitor_config = WindowMonitorConfig(
        appear_timeout_seconds=monitor.appear_timeout_seconds,
        poll_interval_seconds=monitor.poll_interval_seconds,
        stable_poll_count=_ask_positive_int(
            io,
            "Monitor stable poll count",
            default=monitor.stable_poll_count,
        ),
    )


def _step_streamlit_flags(state: _WizardState, io: _WizardIo) -> None:
    state.streamlit_flags = _ask_mapping(
        io,
        "Streamlit flag",
        current=state.streamlit_flags,
        value_parser=_parse_profile_scalar,
        hint="Use key=value, for example server.maxUploadSize=200.",
    )


def _step_streamlit_args(state: _WizardState, io: _WizardIo) -> None:
    state.streamlit_args = _ask_list(
        io,
        "Raw Streamlit arg",
        current=state.streamlit_args,
    )


def _step_app_args(state: _WizardState, io: _WizardIo) -> None:
    state.app_args = _ask_list(io, "App arg", current=state.app_args)


def _step_cwd(state: _WizardState, io: _WizardIo) -> None:
    default = "" if state.cwd is None else str(state.cwd)
    value = _ask_optional(
        io,
        "Working directory (blank for profile config folder)",
        default=default,
    )
    if not value:
        state.cwd = None
        return
    path = Path(value)
    if not path.exists():
        _write(io.stream, "Working directory does not exist.")
        _step_cwd(state, io)
        return
    if not path.is_dir():
        _write(io.stream, "Working directory must be a directory.")
        _step_cwd(state, io)
        return
    state.cwd = path


def _step_extra_env(state: _WizardState, io: _WizardIo) -> None:
    _write_warning_status(
        io.stream,
        "Extra environment values are stored as plaintext in litlaunch.toml.",
        io.use_color,
    )
    state.extra_env = {
        key: str(value)
        for key, value in _ask_mapping(
            io,
            "Environment variable",
            current=state.extra_env,
            value_parser=str,
            hint=(
                "Use NAME=value. Values are written to the child process profile only."
            ),
        ).items()
    }


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
        app_icon=state.app_icon,
        mode=LaunchMode.WEBAPP if launch_experience == "webapp" else LaunchMode.BROWSER,
        browser=BrowserChoice(browser),
        host=state.host,
        port=state.port,
        auto_port=state.auto_port,
        headless=state.headless,
        allow_browser_fallback=state.allow_browser_fallback,
        allow_network_exposure=state.allow_network_exposure,
        cwd=state.cwd,
        extra_env=state.extra_env,
        streamlit_flags=state.streamlit_flags,
        streamlit_args=state.streamlit_args,
        app_args=state.app_args,
        extra_browser_args=state.extra_browser_args,
    )
    return LaunchProfile(
        name=state.profile_name,
        config=config,
        monitor_window=bool(state.monitor_window),
        graceful_timeout_seconds=state.graceful_timeout,
        window_monitor_config=state.monitor_config,
    )


def _offer_shortcut_creation(
    io: _WizardIo,
    profile: LaunchProfile,
    state: _WizardState,
    platform_info: PlatformInfo | None,
) -> None:
    if not _ask_bool(io, "Create a shortcut for this profile now", default=False):
        return
    if platform_info is None:
        _write(io.stream, "Shortcut creation skipped; platform information missing.")
        return
    plan = build_shortcut_plan(
        ShortcutRequest(
            profile=profile,
            platform=platform_info,
            config_path=state.config_path.resolve(),
        )
    )
    force = False
    if plan.output_path.exists():
        force = _ask_bool(
            io,
            f"Shortcut already exists at {plan.output_path}. Overwrite",
            default=False,
        )
        if not force:
            _write(io.stream, "Shortcut creation skipped.")
            return
    write_shortcut(plan, force=force)
    _write(io.stream, f"Created shortcut: {plan.output_path}.")


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
        _write(io.stream, "Press Enter for the default selection.")
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
    while True:
        prompt = f"{label}"
        if default is not None:
            prompt += f" [{default}]"
            _write(io.stream, "Press Enter for the default value.")
        prompt = f"Selection: {prompt}:"
        _write(io.stream, prompt)
        answer = _read_answer(io)
        stripped = answer.strip()
        if not stripped and default is None:
            _write(io.stream, f"{label} requires a value.")
            continue
        value = stripped if stripped else (default or "")
        if raw_default and value == (default or ""):
            return stripped
        if validator is None:
            return value
        return validator(value)


def _ask_optional(io: _WizardIo, label: str, *, default: str = "") -> str:
    prompt = f"Selection: {label}"
    if default:
        prompt += f" [{default}]"
        _write(io.stream, "Press Enter for the default value.")
    prompt += ":"
    _write(io.stream, prompt)
    answer = _read_answer(io).strip()
    return answer if answer else default


def _ask_positive_float(io: _WizardIo, label: str, *, default: float) -> float:
    while True:
        value = _ask(io, label, default=f"{default:g}")
        try:
            number = float(value)
        except ValueError:
            _write(io.stream, "Enter a positive number.")
            continue
        if number > 0:
            return number
        _write(io.stream, "Enter a positive number.")


def _ask_positive_int(io: _WizardIo, label: str, *, default: int) -> int:
    while True:
        value = _ask(io, label, default=str(default))
        try:
            number = int(value)
        except ValueError:
            _write(io.stream, "Enter a positive integer.")
            continue
        if number > 0:
            return number
        _write(io.stream, "Enter a positive integer.")


def _ask_list(io: _WizardIo, label: str, *, current: list[str]) -> list[str]:
    if current:
        _write(io.stream, f"Current entries: {', '.join(current)}")
    _write(io.stream, f"Enter {label.lower()} values one at a time.")
    _write(io.stream, "Leave blank when finished, or type 'clear' to reset.")
    values = list(current)
    while True:
        _write(io.stream, f"Selection: {label}:")
        answer = _read_answer(io).strip()
        if not answer:
            return values
        if answer.lower() == "clear":
            values = []
            _write(io.stream, "Entries cleared.")
            continue
        values.append(answer)


def _ask_mapping(
    io: _WizardIo,
    label: str,
    *,
    current: Mapping[str, _MappingValue],
    value_parser: Callable[[str], _MappingValue],
    hint: str,
) -> dict[str, _MappingValue]:
    if current:
        _write(io.stream, f"Current entries: {', '.join(sorted(current))}")
    _write(io.stream, hint)
    _write(io.stream, "Leave blank when finished, or type 'clear' to reset.")
    values = dict(current)
    while True:
        _write(io.stream, f"Selection: {label}:")
        answer = _read_answer(io).strip()
        if not answer:
            return values
        if answer.lower() == "clear":
            values = {}
            _write(io.stream, "Entries cleared.")
            continue
        key, separator, raw_value = answer.partition("=")
        key = key.strip()
        if not separator or not key:
            _write(io.stream, "Use key=value.")
            continue
        values[key] = value_parser(raw_value.strip())


def _parse_profile_scalar(value: str) -> str | int | float | bool | None:
    normalized = value.strip()
    if normalized.lower() == "true":
        return True
    if normalized.lower() == "false":
        return False
    if normalized.lower() in {"none", "null"}:
        return None
    try:
        return int(normalized)
    except ValueError:
        pass
    try:
        return float(normalized)
    except ValueError:
        return normalized


def _read_answer(io: _WizardIo) -> str:
    answer = io.input_func()
    normalized = answer.strip().lower()
    if normalized in BACK_COMMANDS:
        raise _WizardBack
    if normalized in QUIT_COMMANDS:
        raise _WizardQuit
    return answer


def _nonempty(value: str) -> str:
    if not value.strip():
        raise ConfigurationError("value cannot be empty.")
    return value.strip()


def _litlaunch_toml_path(value: str) -> str:
    path = Path(value)
    if path.name != "litlaunch.toml":
        raise ConfigurationError("create profile writes only litlaunch.toml.")
    return value
