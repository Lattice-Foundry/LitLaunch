"""Structured text diagnostics for LitLaunch runtime inspection."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from importlib import metadata
from pathlib import Path

from litlaunch.browsers import BrowserCapability, BrowserResolution
from litlaunch.browsers.registry import BrowserRegistry, create_default_browser_registry
from litlaunch.config import BrowserChoice, LauncherConfig, LaunchMode, StreamlitFlags
from litlaunch.health import build_streamlit_app_url, build_streamlit_health_url
from litlaunch.launcher import StreamlitLauncher
from litlaunch.platforms import PlatformDetector, PlatformInfo
from litlaunch.version import __version__

SCHEMA_VERSION = 1
SENSITIVE_MARKERS = (
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "api-key",
)
SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(token|secret|password|passwd|api_key|apikey|key)"
    r"(\s*[:=]\s*)"
    r"([^\s,;]+)"
)
SENSITIVE_WORD_PATTERN = re.compile(
    r"(?i)\b((?:token|secret|password|passwd|api_key|apikey|key)\s+)"
    r"([A-Za-z0-9._~+/=-]{6,})"
)


class DiagnosticStatus(str, Enum):
    """Diagnostic item status values."""

    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    INFO = "info"


@dataclass(frozen=True)
class DiagnosticItem:
    """One diagnostic finding."""

    name: str
    status: DiagnosticStatus
    message: str
    detail: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "message", self.message.strip())
        if not self.name:
            raise ValueError("diagnostic item name cannot be empty.")
        if not self.message:
            raise ValueError("diagnostic item message cannot be empty.")
        if self.detail is not None:
            object.__setattr__(self, "detail", str(self.detail))

    def to_dict(self) -> dict[str, object]:
        """Return a sanitized stable dictionary representation."""

        data: dict[str, object] = {
            "name": redact_sensitive_text(self.name),
            "status": self.status.value,
            "message": redact_sensitive_text(self.message),
            "detail": None,
        }
        if self.detail is not None:
            data["detail"] = redact_sensitive_text(self.detail)
        return data


@dataclass(frozen=True)
class DiagnosticSection:
    """A titled group of diagnostic items."""

    title: str
    items: tuple[DiagnosticItem, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", self.title.strip())
        object.__setattr__(self, "items", tuple(self.items))
        if not self.title:
            raise ValueError("diagnostic section title cannot be empty.")

    def to_dict(self) -> dict[str, object]:
        """Return a sanitized stable dictionary representation."""

        return {
            "title": redact_sensitive_text(self.title),
            "items": [item.to_dict() for item in self.items],
        }


@dataclass(frozen=True)
class DiagnosticsReport:
    """Complete structured diagnostics report."""

    title: str
    sections: tuple[DiagnosticSection, ...] = ()
    generated_at_utc: str = field(default_factory=lambda: current_utc_timestamp())
    ok: bool = field(init=False)
    warnings: int = field(init=False)
    errors: int = field(init=False)

    def __post_init__(self) -> None:
        title = self.title.strip()
        sections = tuple(self.sections)
        generated_at = str(self.generated_at_utc).strip()
        warnings = _count_status(sections, DiagnosticStatus.WARNING)
        errors = _count_status(sections, DiagnosticStatus.ERROR)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "sections", sections)
        object.__setattr__(self, "generated_at_utc", generated_at)
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "errors", errors)
        object.__setattr__(self, "ok", errors == 0)
        if not title:
            raise ValueError("diagnostics report title cannot be empty.")
        if not generated_at:
            raise ValueError("diagnostics report timestamp cannot be empty.")

    def to_dict(self) -> dict[str, object]:
        """Return a sanitized stable dictionary representation."""

        return {
            "schema_version": SCHEMA_VERSION,
            "generated_by": "litlaunch",
            "litlaunch_version": __version__,
            "generated_at_utc": redact_sensitive_text(self.generated_at_utc),
            "title": redact_sensitive_text(self.title),
            "ok": self.ok,
            "warnings": self.warnings,
            "errors": self.errors,
            "sections": [section.to_dict() for section in self.sections],
        }


@dataclass(frozen=True)
class StreamlitAvailability:
    """Streamlit import/version availability check result."""

    available: bool
    version: str | None
    message: str


class DiagnosticCollector:
    """Collect local LitLaunch diagnostics without launching Streamlit."""

    def __init__(
        self,
        *,
        platform_detector: PlatformDetector | None = None,
        browser_registry: BrowserRegistry | None = None,
        streamlit_checker: Callable[[], StreamlitAvailability] | None = None,
        launcher_factory: type[StreamlitLauncher] = StreamlitLauncher,
    ) -> None:
        self.platform_detector = platform_detector or PlatformDetector()
        self.browser_registry = browser_registry or create_default_browser_registry()
        self.streamlit_checker = streamlit_checker or check_streamlit_availability
        self.launcher_factory = launcher_factory

    def collect(
        self,
        app_path: str | Path | None = None,
        *,
        mode: LaunchMode | str = LaunchMode.BROWSER,
        browser: BrowserChoice | str = BrowserChoice.AUTO,
        host: str = "127.0.0.1",
        port: int | None = None,
        allow_browser_fallback: bool = True,
        streamlit_flags: StreamlitFlags | None = None,
        streamlit_args: Sequence[str] = (),
        app_args: Sequence[str] = (),
    ) -> DiagnosticsReport:
        """Collect diagnostics for the current environment and optional app target."""

        platform_info = self.platform_detector.detect()
        streamlit = self.streamlit_checker()
        capabilities = self.browser_registry.detect_all(platform_info)
        resolution = self.browser_registry.resolve(
            _normalize_browser_choice(browser),
            platform_info,
            prefer_app_mode=_normalize_launch_mode(mode) == LaunchMode.WEBAPP,
            allow_fallback=allow_browser_fallback,
        )

        sections = [
            self._litlaunch_section(),
            self._platform_section(platform_info),
            self._streamlit_section(streamlit),
            self._browser_section(capabilities, resolution),
        ]
        if app_path is not None:
            sections.append(
                self._target_section(
                    app_path,
                    mode=mode,
                    browser=browser,
                    host=host,
                    port=port,
                    allow_browser_fallback=allow_browser_fallback,
                    streamlit_flags=streamlit_flags or {},
                    streamlit_args=streamlit_args,
                    app_args=app_args,
                )
            )

        return DiagnosticsReport("LitLaunch Inspect", tuple(sections))

    def _litlaunch_section(self) -> DiagnosticSection:
        return DiagnosticSection(
            "LitLaunch",
            (
                DiagnosticItem(
                    "Version",
                    DiagnosticStatus.OK,
                    f"LitLaunch {__version__}",
                ),
            ),
        )

    def _platform_section(self, platform_info: PlatformInfo) -> DiagnosticSection:
        return DiagnosticSection(
            "Platform",
            (
                DiagnosticItem(
                    "Platform",
                    DiagnosticStatus.OK,
                    platform_info.summary(),
                ),
                DiagnosticItem(
                    "Python executable",
                    DiagnosticStatus.INFO,
                    platform_info.python_executable,
                ),
                DiagnosticItem(
                    "Chromium app mode",
                    _capability_status(platform_info.supports_chromium_app_mode),
                    _supported_message(platform_info.supports_chromium_app_mode),
                ),
                DiagnosticItem(
                    "Default browser open",
                    _capability_status(platform_info.supports_default_browser_open),
                    _supported_message(platform_info.supports_default_browser_open),
                ),
                DiagnosticItem(
                    "Window monitoring",
                    _capability_status(platform_info.supports_window_monitoring),
                    _supported_message(platform_info.supports_window_monitoring),
                ),
            ),
        )

    def _streamlit_section(
        self,
        streamlit: StreamlitAvailability,
    ) -> DiagnosticSection:
        status = DiagnosticStatus.OK if streamlit.available else DiagnosticStatus.ERROR
        return DiagnosticSection(
            "Streamlit",
            (
                DiagnosticItem(
                    "Availability",
                    status,
                    streamlit.message,
                ),
            ),
        )

    def _browser_section(
        self,
        capabilities: tuple[BrowserCapability, ...],
        resolution: BrowserResolution,
    ) -> DiagnosticSection:
        items: list[DiagnosticItem] = []
        for capability in capabilities:
            status = (
                DiagnosticStatus.OK
                if capability.available
                else DiagnosticStatus.WARNING
            )
            support = []
            if capability.supports_app_mode:
                support.append("app-mode")
            if capability.supports_full_browser:
                support.append("full-browser")
            support_text = ", ".join(support) if support else "no launch modes"
            availability = "available" if capability.available else "unavailable"
            detail = "; ".join(capability.notes) if capability.notes else None
            items.append(
                DiagnosticItem(
                    capability.name,
                    status,
                    f"{availability}, {support_text}",
                    detail=detail,
                )
            )

        resolution_status = (
            DiagnosticStatus.OK
            if resolution.selected is not None
            else DiagnosticStatus.WARNING
        )
        items.append(
            DiagnosticItem(
                "Browser resolution",
                resolution_status,
                resolution.message,
            )
        )
        return DiagnosticSection("Browsers", tuple(items))

    def _target_section(
        self,
        app_path: str | Path,
        *,
        mode: LaunchMode | str,
        browser: BrowserChoice | str,
        host: str,
        port: int | None,
        allow_browser_fallback: bool,
        streamlit_flags: StreamlitFlags,
        streamlit_args: Sequence[str],
        app_args: Sequence[str],
    ) -> DiagnosticSection:
        path = Path(app_path)
        resolved_path = path.resolve()
        items: list[DiagnosticItem] = []

        exists = path.exists()
        is_file = path.is_file()
        items.append(
            DiagnosticItem(
                "App path exists",
                DiagnosticStatus.OK if exists else DiagnosticStatus.ERROR,
                f"{path} exists" if exists else f"{path} does not exist",
            )
        )
        items.append(
            DiagnosticItem(
                "App path is file",
                DiagnosticStatus.OK if is_file else DiagnosticStatus.ERROR,
                f"{path} is a file" if is_file else f"{path} is not a file",
            )
        )
        items.append(
            DiagnosticItem(
                "Resolved app path",
                DiagnosticStatus.INFO,
                str(resolved_path),
            )
        )

        if not exists or not is_file:
            return DiagnosticSection("Target", tuple(items))

        try:
            config = LauncherConfig(
                app_path=path,
                mode=mode,
                browser=browser,
                host=host,
                port=port,
                allow_browser_fallback=allow_browser_fallback,
                streamlit_flags=streamlit_flags,
                streamlit_args=streamlit_args,
                app_args=app_args,
            )
            launcher = self.launcher_factory(config)
            resolved_port = launcher.resolve_port()
            command = launcher.command_builder.build(port=resolved_port)
            app_url = build_streamlit_app_url(config.host, resolved_port)
            health_url = build_streamlit_health_url(config.host, resolved_port)
            target_resolution = launcher.resolve_browser(
                prefer_app_mode=config.mode == LaunchMode.WEBAPP
            )
        except Exception as exc:
            items.append(
                DiagnosticItem(
                    "Launch preview",
                    DiagnosticStatus.ERROR,
                    str(exc),
                )
            )
            return DiagnosticSection("Target", tuple(items))

        items.extend(
            (
                DiagnosticItem(
                    "Command preview",
                    DiagnosticStatus.OK,
                    "Streamlit command can be built.",
                    detail=format_command_preview(command),
                ),
                DiagnosticItem(
                    "App URL preview",
                    DiagnosticStatus.INFO,
                    app_url,
                ),
                DiagnosticItem(
                    "Health URL preview",
                    DiagnosticStatus.INFO,
                    health_url,
                ),
                DiagnosticItem(
                    "Browser resolution",
                    (
                        DiagnosticStatus.OK
                        if target_resolution.selected is not None
                        else DiagnosticStatus.WARNING
                    ),
                    target_resolution.message,
                ),
            )
        )
        return DiagnosticSection("Target", tuple(items))


class TextDiagnosticsRenderer:
    """Render structured diagnostics to plain text."""

    def __init__(self, *, include_details: bool = True) -> None:
        self.include_details = include_details

    def render(self, report: DiagnosticsReport) -> str:
        """Render a diagnostics report to a deterministic text string."""

        lines = [redact_sensitive_text(report.title), ""]
        for section in report.sections:
            lines.append(redact_sensitive_text(section.title))
            for item in section.items:
                lines.append(_render_item(item))
                if self.include_details and item.detail:
                    detail = redact_sensitive_text(item.detail)
                    for detail_line in detail.splitlines():
                        lines.append(f"    {detail_line}")
            lines.append("")
        lines.append("Summary")
        lines.append(f"{report.errors} errors, {report.warnings} warnings")
        return "\n".join(lines).rstrip() + "\n"


class JSONDiagnosticsRenderer:
    """Render structured diagnostics to deterministic JSON."""

    def render(self, report: DiagnosticsReport) -> str:
        """Render a diagnostics report as pretty JSON."""

        return json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"


class SanitizedBundleRenderer:
    """Render a concise copyable support bundle."""

    SANITIZATION_NOTE = (
        "This report is sanitized and does not include raw environment variables "
        "or shutdown tokens."
    )

    def __init__(self, *, include_details: bool = True) -> None:
        self.include_details = include_details

    def render(self, report: DiagnosticsReport) -> str:
        """Render a sanitized text support bundle."""

        status = "ok" if report.ok else "failed"
        lines = [
            "LitLaunch Support Bundle",
            f"Version: {__version__}",
            f"Generated at: {redact_sensitive_text(report.generated_at_utc)}",
            f"Summary: {status}; {report.errors} errors; {report.warnings} warnings",
            f"Note: {self.SANITIZATION_NOTE}",
            "",
        ]
        for section in report.sections:
            lines.append(redact_sensitive_text(section.title))
            for item in section.items:
                lines.append(f"- {_render_item(item)}")
                if self.include_details and item.detail:
                    detail = redact_sensitive_text(item.detail)
                    for detail_line in detail.splitlines():
                        lines.append(f"  {detail_line}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"


def check_streamlit_availability() -> StreamlitAvailability:
    """Return Streamlit package availability using package metadata only."""

    try:
        version = metadata.version("streamlit")
    except metadata.PackageNotFoundError:
        return StreamlitAvailability(
            available=False,
            version=None,
            message="Streamlit is not installed in this Python environment.",
        )
    return StreamlitAvailability(
        available=True,
        version=version,
        message=f"Streamlit {version} detected.",
    )


def current_utc_timestamp() -> str:
    """Return a compact UTC ISO timestamp for diagnostics metadata."""

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def format_command_preview(command: Sequence[str]) -> str:
    """Format a shell-free command sequence for display with basic redaction."""

    return subprocess.list2cmdline(redact_sensitive_args(command))


def redact_sensitive_args(command: Sequence[str]) -> tuple[str, ...]:
    """Redact sensitive-looking command argument values."""

    redacted: list[str] = []
    redact_next = False
    for part in command:
        value = str(part)
        if redact_next:
            redacted.append("<redacted>")
            redact_next = False
            continue
        if _is_sensitive_argument_name(value):
            if "=" in value:
                key, _separator, _secret = value.partition("=")
                redacted.append(f"{key}=<redacted>")
            else:
                redacted.append(value)
                redact_next = True
            continue
        redacted.append(value)
    return tuple(redacted)


def redact_sensitive_text(value: object) -> str:
    """Redact sensitive-looking values in display/report strings."""

    text = str(value)
    text = SENSITIVE_ASSIGNMENT_PATTERN.sub(r"\1\2<redacted>", text)
    return SENSITIVE_WORD_PATTERN.sub(r"\1<redacted>", text)


def sanitize_report_dict(value: object) -> object:
    """Recursively redact strings in a report-like data structure."""

    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, Mapping):
        return {
            redact_sensitive_text(key): sanitize_report_dict(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [sanitize_report_dict(item) for item in value]
    return value


def _count_status(
    sections: tuple[DiagnosticSection, ...],
    status: DiagnosticStatus,
) -> int:
    return sum(
        1 for section in sections for item in section.items if item.status == status
    )


def _capability_status(supported: bool) -> DiagnosticStatus:
    return DiagnosticStatus.OK if supported else DiagnosticStatus.WARNING


def _supported_message(supported: bool) -> str:
    return "supported" if supported else "not supported"


def _normalize_launch_mode(value: LaunchMode | str) -> LaunchMode:
    return value if isinstance(value, LaunchMode) else LaunchMode(str(value))


def _normalize_browser_choice(value: BrowserChoice | str) -> BrowserChoice:
    return value if isinstance(value, BrowserChoice) else BrowserChoice(str(value))


def _render_item(item: DiagnosticItem) -> str:
    name = redact_sensitive_text(item.name)
    message = redact_sensitive_text(item.message)
    return f"[{item.status.value.upper()}] {name}: {message}"


def _is_sensitive_argument_name(value: str) -> bool:
    lowered = value.lower().lstrip("-")
    name = lowered.split("=", 1)[0]
    if any(marker in name for marker in SENSITIVE_MARKERS):
        return True
    return name == "key" or name.endswith((".key", "_key", "-key"))
