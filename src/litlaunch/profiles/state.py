"""State and control-flow models for the profile wizard."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from litlaunch.windowing import WindowMonitorConfig

from .detection import AppRootDetection

InputFunc = Callable[[], str]

BACK_COMMANDS = {"back", "b", "r", "return"}
QUIT_COMMANDS = {"quit", "q", "exit", "cancel"}


class ProfileWizardCancelled(Exception):
    """Raised when profile creation is cancelled by the user."""


class WizardBack(Exception):
    """Internal control flow for moving to the previous wizard step."""


class WizardQuit(Exception):
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
class WizardState:
    """Mutable state accumulated while the user moves through wizard steps."""

    detection: AppRootDetection
    config_path: Path
    existing_names: set[str]
    setup_mode: str | None = None
    profile_name: str | None = None
    app_path: Path | None = None
    title: str | None = None
    launch_experience: str | None = None
    browser: str | None = None
    host: str = "127.0.0.1"
    port: int | None = None
    auto_port: bool = True
    headless: bool | None = None
    allow_browser_fallback: bool = True
    allow_network_exposure: bool = False
    cwd: Path | None = None
    streamlit_flags: dict[str, str | int | float | bool | None] = field(
        default_factory=dict
    )
    streamlit_args: list[str] = field(default_factory=list)
    app_args: list[str] = field(default_factory=list)
    extra_browser_args: list[str] = field(default_factory=list)
    extra_env: dict[str, str] = field(default_factory=dict)
    monitor_window: bool | None = None
    graceful_timeout: float = 3.0
    monitor_config: WindowMonitorConfig = WindowMonitorConfig()
    force: bool = False
    write_confirmed: bool = False


@dataclass(frozen=True)
class WizardIo:
    """Terminal IO dependencies for wizard prompts and rendering."""

    stream: TextIO
    input_func: InputFunc
    use_color: bool


@dataclass(frozen=True)
class WizardStep:
    """One navigable profile wizard step."""

    title: str
    handler: Callable[[WizardState, WizardIo], None]
    context: str
    skip: Callable[[WizardState], bool] = lambda _state: False


def previous_step_index(
    steps: tuple[WizardStep, ...],
    state: WizardState,
    index: int,
) -> int:
    """Return the nearest previous visible wizard step index."""

    for previous in range(index - 1, -1, -1):
        if not steps[previous].skip(state):
            return previous
    return index
