"""Lifecycle state and result types for LitLaunch."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from litlaunch.browsers.base import BrowserCapability, BrowserResolution
from litlaunch.config import BrowserChoice, LaunchMode


class LaunchState(str, Enum):
    """Coarse lifecycle states for launcher-owned backend runs."""

    CREATED = "created"
    CONFIGURED = "configured"
    PORT_READY = "port_ready"
    COMMAND_BUILT = "command_built"
    PROCESS_STARTING = "process_starting"
    PROCESS_RUNNING = "process_running"
    HEALTH_CHECKING = "health_checking"
    HEALTHY = "healthy"
    BROWSER_RESOLVING = "browser_resolving"
    BROWSER_LAUNCHING = "browser_launching"
    WINDOW_MONITORING = "window_monitoring"
    WINDOW_CLOSED = "window_closed"
    RUNNING = "running"
    FAILED = "failed"
    TERMINATING = "terminating"
    TERMINATED = "terminated"


@dataclass(frozen=True)
class LaunchEvent:
    """One timestamped lifecycle state transition or diagnostic event."""

    state: LaunchState
    message: str
    timestamp: float


@dataclass(frozen=True)
class LaunchResult:
    """Result from a launcher lifecycle operation."""

    ok: bool
    state: LaunchState
    command: tuple[str, ...] | None
    pid: int | None
    url: str | None
    message: str
    events: tuple[LaunchEvent, ...]
    browser: BrowserCapability | None = None
    browser_command: tuple[str, ...] | None = None
    browser_launched: bool = False


@dataclass(frozen=True)
class LaunchPlan:
    """Resolved launch preview that does not start backend or browser processes."""

    command: tuple[str, ...]
    command_display: str
    backend_description: str
    backend_kind: str | None
    cwd: Path | None
    app_url: str
    health_url: str
    host: str
    port: int | None
    port_range: tuple[int, int] | None
    resolved_port: int
    auto_port: bool
    mode: LaunchMode
    headless: bool
    browser_requested: BrowserChoice
    browser_resolution: BrowserResolution | None
    allow_browser_fallback: bool
    app_args: tuple[str, ...]
    streamlit_flags: Mapping[str, str | int | float | bool | None] | tuple[str, ...]
    streamlit_args: tuple[str, ...]
    extra_env_preview: str
    port_selection: str = "requested/default port available"
    streamlit_chrome_policy: str = "hidden"
    streamlit_output_policy: str = "hidden"
    app_icon: Path | None = None
    app_icon_support: str = "not configured"
    runtime_state_root: Path | None = None
    browser_profile_root: Path | None = None
    browser_profile_policy: str = "external/default browser profile"
    browser_profile_cleanup: str = "not owned by LitLaunch"
