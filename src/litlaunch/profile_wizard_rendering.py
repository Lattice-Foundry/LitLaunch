"""Terminal rendering helpers for the profile wizard."""

from __future__ import annotations

from pathlib import Path
from typing import TextIO

from litlaunch.colors import help_magenta, muted_amber, streamlit_blue, terminal_green
from litlaunch.console_style import status_prefix, style_text
from litlaunch.profile_wizard_state import WizardIo, WizardState, WizardStep
from litlaunch.profiles import LaunchProfile


def render_step_header(
    io: WizardIo,
    state: WizardState,
    steps: tuple[WizardStep, ...],
    index: int,
) -> None:
    """Render the current wizard step header, state summary, and help notes."""

    clear_screen(io.stream)
    visible_steps = [step for step in steps if not step.skip(state)]
    current = sum(1 for step in steps[:index] if not step.skip(state)) + 1
    title = steps[index].title
    mode = "Advanced" if state.setup_mode == "advanced" else "Simple"
    write(
        io.stream,
        style_text("Create Profile Wizard", streamlit_blue, use_color=io.use_color),
    )
    mode_text = style_text(mode, help_magenta, use_color=io.use_color)
    step_text = style_text(
        f"Step {current} of {len(visible_steps)} - {title}",
        streamlit_blue,
        use_color=io.use_color,
    )
    write(io.stream, f"{mode_text} - {step_text}")
    render_current_data(io, state)
    render_step_notes(io, steps[index])


def render_current_data(io: WizardIo, state: WizardState) -> None:
    """Render compact wizard state gathered so far."""

    values = current_data_values(state)
    if not values:
        return
    write(io.stream, "Current profile:")
    for label, value in values:
        label_text = style_text(
            f"  {label}:",
            streamlit_blue,
            use_color=io.use_color,
        )
        value_text = style_text(str(value), terminal_green, use_color=io.use_color)
        write(io.stream, f"{label_text} {value_text}")
    write(io.stream, "")


def render_step_notes(io: WizardIo, step: WizardStep) -> None:
    """Render a short explanation and navigation hint for one wizard step."""

    label = style_text("About:", streamlit_blue, use_color=io.use_color)
    write(io.stream, f"{label} {step.context}")
    label = style_text("Navigation:", streamlit_blue, use_color=io.use_color)
    write(
        io.stream,
        (
            f"{label} Enter accepts bracketed or marked defaults; "
            "type 'back', 'b', or 'r' to return; 'quit' or 'q' to cancel."
        ),
    )
    write(io.stream, "")


def current_data_values(state: WizardState) -> tuple[tuple[str, str], ...]:
    """Return compact state values suitable for step headers."""

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
    if state.setup_mode == "advanced":
        values.append(("Host", state.host))
        values.append(("Port", "auto" if state.port is None else str(state.port)))
        values.append(("Auto-port", "enabled" if state.auto_port else "disabled"))
        fallback = "enabled" if state.allow_browser_fallback else "disabled"
        values.append(("Browser fallback", fallback))
        if state.allow_network_exposure:
            values.append(("Network exposure", "acknowledged"))
        if state.headless is not None:
            values.append(("Headless", str(state.headless).lower()))
        if state.cwd is not None:
            values.append(("Cwd", str(state.cwd)))
        append_count(values, "Streamlit flags", len(state.streamlit_flags))
        append_count(values, "Streamlit args", len(state.streamlit_args))
        append_count(values, "App args", len(state.app_args))
        append_count(values, "Browser args", len(state.extra_browser_args))
        append_count(values, "Env vars", len(state.extra_env))
    if state.launch_experience == "webapp" and state.monitor_window is not None:
        values.append(("Monitor", "enabled" if state.monitor_window else "disabled"))
    if state.config_path:
        values.append(("Config", str(state.config_path)))
    return tuple(values)


def append_count(
    values: list[tuple[str, str]],
    label: str,
    count: int,
) -> None:
    """Append a count to the current-data summary when non-zero."""

    if count:
        values.append((label, str(count)))


def preview_profile(
    stream: TextIO,
    profile: LaunchProfile,
    *,
    config_path: Path,
    launch_experience: str,
) -> None:
    """Render the final profile preview before confirmation."""

    write(stream, "")
    write(stream, "Profile preview")
    write(stream, f"Profile: {profile.name}")
    write(stream, f"Config: {config_path}")
    write(stream, f"App: {profile.config.app_path}")
    write(stream, f"Title: {profile.config.title}")
    label = "App window" if launch_experience == "webapp" else "Browser tab"
    write(stream, f"Launch experience: {label}")
    write(stream, f"Browser: {profile.config.browser.value}")
    write(stream, f"Host: {profile.config.host}")
    port = "auto" if profile.config.port is None else str(profile.config.port)
    write(stream, f"Port: {port}")
    auto_port = "enabled" if profile.config.auto_port else "disabled"
    write(stream, f"Auto-port: {auto_port}")
    fallback = "enabled" if profile.config.allow_browser_fallback else "disabled"
    write(stream, f"Browser fallback: {fallback}")
    if profile.config.allow_network_exposure:
        write(stream, "Network exposure: acknowledged")
    if profile.config.headless is not None:
        write(stream, f"Headless: {str(profile.config.headless).lower()}")
    if profile.config.cwd is not None:
        write(stream, f"Working directory: {profile.config.cwd}")
    monitor_status = "enabled" if profile.monitor_window else "disabled"
    write(stream, f"Monitor window: {monitor_status}")
    if profile.config.streamlit_flags:
        write(stream, f"Streamlit flags: {len(profile.config.streamlit_flags)}")
    if profile.config.streamlit_args:
        write(stream, f"Streamlit args: {len(profile.config.streamlit_args)}")
    if profile.config.app_args:
        write(stream, f"App args: {len(profile.config.app_args)}")
    if profile.config.extra_browser_args:
        write(stream, f"Extra browser args: {len(profile.config.extra_browser_args)}")
    if profile.config.extra_env:
        write(stream, f"Extra env vars: {len(profile.config.extra_env)}")
    write(stream, "")


def write_warning_status(stream: TextIO, message: str, use_color: bool = False) -> None:
    """Render a wizard warning status line through shared console styling."""

    prefix = status_prefix("warn", muted_amber, use_color=use_color)
    write(stream, f"{prefix} {message}")


def write(stream: TextIO, message: str) -> None:
    """Write one wizard output line and flush when supported."""

    stream.write(f"{message}\n")
    flush = getattr(stream, "flush", None)
    if callable(flush):
        flush()


def clear_screen(stream: TextIO) -> None:
    """Clear the terminal between wizard steps when running interactively."""

    isatty = getattr(stream, "isatty", None)
    if not callable(isatty) or not isatty():
        return
    stream.write("\033[2J\033[H")
    flush = getattr(stream, "flush", None)
    if callable(flush):
        flush()
