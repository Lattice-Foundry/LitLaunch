"""Structured text diagnostics for LitLaunch runtime inspection."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from html import escape
from importlib import metadata
from pathlib import Path

from litlaunch.browsers import BrowserCapability, BrowserResolution
from litlaunch.browsers.registry import BrowserRegistry, create_default_browser_registry
from litlaunch.config import BrowserChoice, LauncherConfig, LaunchMode, StreamlitFlags
from litlaunch.launcher import StreamlitLauncher
from litlaunch.platforms import PlatformDetector, PlatformInfo
from litlaunch.redaction import (
    redact_sensitive_args,  # noqa: F401 - re-exported for inspect consumers.
    redact_sensitive_text,
    sanitize_report_dict,  # noqa: F401 - re-exported for inspect consumers.
)
from litlaunch.version import __version__
from litlaunch.windowing import WindowMonitorConfig

SCHEMA_VERSION = 1


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
        auto_port: bool = True,
        allow_browser_fallback: bool = True,
        cwd: str | Path | None = None,
        extra_env: Mapping[str, str] | None = None,
        streamlit_flags: StreamlitFlags | None = None,
        streamlit_args: Sequence[str] = (),
        app_args: Sequence[str] = (),
        profile_name: str | None = None,
        monitor_window: bool | None = None,
        graceful_timeout_seconds: float | None = None,
        window_monitor_config: WindowMonitorConfig | None = None,
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
        if profile_name is not None:
            sections.append(
                self._profile_section(
                    profile_name,
                    monitor_window=monitor_window,
                    graceful_timeout_seconds=graceful_timeout_seconds,
                    window_monitor_config=window_monitor_config,
                )
            )
        if app_path is not None:
            sections.append(
                self._target_section(
                    app_path,
                    mode=mode,
                    browser=browser,
                    host=host,
                    port=port,
                    auto_port=auto_port,
                    allow_browser_fallback=allow_browser_fallback,
                    cwd=cwd,
                    extra_env=extra_env or {},
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

    def _profile_section(
        self,
        profile_name: str,
        *,
        monitor_window: bool | None,
        graceful_timeout_seconds: float | None,
        window_monitor_config: WindowMonitorConfig | None,
    ) -> DiagnosticSection:
        items = [
            DiagnosticItem(
                "Profile",
                DiagnosticStatus.INFO,
                profile_name,
            ),
        ]
        if monitor_window is not None:
            items.append(
                DiagnosticItem(
                    "Window monitoring",
                    DiagnosticStatus.INFO,
                    "enabled" if monitor_window else "disabled",
                )
            )
        if graceful_timeout_seconds is not None:
            items.append(
                DiagnosticItem(
                    "Graceful timeout",
                    DiagnosticStatus.INFO,
                    f"{float(graceful_timeout_seconds):g} seconds",
                )
            )
        if window_monitor_config is not None:
            items.extend(
                (
                    DiagnosticItem(
                        "Monitor appear timeout",
                        DiagnosticStatus.INFO,
                        f"{window_monitor_config.appear_timeout_seconds:g} seconds",
                    ),
                    DiagnosticItem(
                        "Monitor poll interval",
                        DiagnosticStatus.INFO,
                        f"{window_monitor_config.poll_interval_seconds:g} seconds",
                    ),
                    DiagnosticItem(
                        "Monitor stable polls",
                        DiagnosticStatus.INFO,
                        str(window_monitor_config.stable_poll_count),
                    ),
                )
            )
        return DiagnosticSection("Profile", tuple(items))

    def _target_section(
        self,
        app_path: str | Path,
        *,
        mode: LaunchMode | str,
        browser: BrowserChoice | str,
        host: str,
        port: int | None,
        auto_port: bool,
        allow_browser_fallback: bool,
        cwd: str | Path | None,
        extra_env: Mapping[str, str],
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
                auto_port=auto_port,
                allow_browser_fallback=allow_browser_fallback,
                cwd=cwd,
                extra_env=extra_env,
                streamlit_flags=streamlit_flags,
                streamlit_args=streamlit_args,
                app_args=app_args,
            )
            launcher = self.launcher_factory(config)
            plan = launcher.build_launch_plan()
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
                    detail=plan.command_display,
                ),
                DiagnosticItem(
                    "App URL preview",
                    DiagnosticStatus.INFO,
                    plan.app_url,
                ),
                DiagnosticItem(
                    "Health URL preview",
                    DiagnosticStatus.INFO,
                    plan.health_url,
                ),
                DiagnosticItem(
                    "Working directory",
                    DiagnosticStatus.INFO,
                    str(plan.cwd) if plan.cwd is not None else "not set",
                ),
                DiagnosticItem(
                    "Environment overrides",
                    DiagnosticStatus.INFO,
                    plan.extra_env_preview,
                ),
                DiagnosticItem(
                    "Browser resolution",
                    (
                        DiagnosticStatus.OK
                        if plan.browser_resolution is not None
                        and plan.browser_resolution.selected is not None
                        else DiagnosticStatus.WARNING
                    ),
                    (
                        plan.browser_resolution.message
                        if plan.browser_resolution is not None
                        else "Browser resolution skipped."
                    ),
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


class HTMLDiagnosticsRenderer:
    """Render structured diagnostics to a sanitized standalone HTML report."""

    SANITIZATION_NOTE = (
        "This report is sanitized and does not include raw environment variables "
        "or shutdown tokens."
    )

    def __init__(self, *, include_details: bool = True) -> None:
        self.include_details = include_details

    def render(self, report: DiagnosticsReport) -> str:
        """Render a diagnostics report as dependency-free HTML."""

        data = report.to_dict()
        status_text = "OK" if data["ok"] else "Needs attention"
        sections = data["sections"]
        lines = [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8">',
            '  <meta name="viewport" content="width=device-width, initial-scale=1">',
            f"  <title>{_html(data['title'])}</title>",
            "  <style>",
            "    :root { color-scheme: light dark; }",
            "    body { font-family: system-ui, -apple-system, Segoe UI, "
            "sans-serif; margin: 2rem; line-height: 1.45; }",
            "    main { max-width: 960px; }",
            "    h1, h2 { line-height: 1.15; }",
            "    .meta, .note, .detail { color: #666; }",
            "    section { border-top: 1px solid #ccc; padding-top: 1rem; "
            "margin-top: 1.5rem; }",
            "    table { border-collapse: collapse; width: 100%; }",
            "    th, td { border-bottom: 1px solid #ddd; padding: .5rem; "
            "text-align: left; vertical-align: top; }",
            "    .status-ok { color: #17803d; font-weight: 700; }",
            "    .status-warning { color: #946200; font-weight: 700; }",
            "    .status-error { color: #b42318; font-weight: 700; }",
            "    .status-info { color: #1c83e1; font-weight: 700; }",
            "    code { white-space: pre-wrap; word-break: break-word; }",
            "  </style>",
            "</head>",
            "<body>",
            "<main>",
            f"  <h1>{_html(data['title'])}</h1>",
            (
                f'  <p class="meta">Generated by {_html(data["generated_by"])} '
                f"{_html(data['litlaunch_version'])} at "
                f"{_html(data['generated_at_utc'])}</p>"
            ),
            (
                f"  <p><strong>Status:</strong> {_html(status_text)}. "
                f"<strong>Errors:</strong> {_html(data['errors'])}. "
                f"<strong>Warnings:</strong> {_html(data['warnings'])}.</p>"
            ),
            (
                f'  <p class="note">{_html(self.SANITIZATION_NOTE)} '
                "Review reports before sharing publicly.</p>"
            ),
        ]
        for section in sections:
            lines.extend(self._render_section(section))
        lines.extend(["</main>", "</body>", "</html>", ""])
        return "\n".join(lines)

    def _render_section(self, section: object) -> list[str]:
        section_data = section if isinstance(section, Mapping) else {}
        title = section_data.get("title", "")
        items = section_data.get("items", [])
        lines = [
            "  <section>",
            f"    <h2>{_html(title)}</h2>",
            "    <table>",
            "      <thead><tr><th>Status</th><th>Name</th><th>Message</th>"
            "<th>Detail</th></tr></thead>",
            "      <tbody>",
        ]
        if isinstance(items, list):
            for item in items:
                lines.append(self._render_item(item))
        lines.extend(["      </tbody>", "    </table>", "  </section>"])
        return lines

    def _render_item(self, item: object) -> str:
        item_data = item if isinstance(item, Mapping) else {}
        status = str(item_data.get("status", "info"))
        detail = item_data.get("detail") if self.include_details else None
        detail_text = "" if detail is None else str(detail)
        return (
            "        <tr>"
            f'<td class="status-{_html_attr(status)}">{_html(status.upper())}</td>'
            f"<td>{_html(item_data.get('name', ''))}</td>"
            f"<td>{_html(item_data.get('message', ''))}</td>"
            f"<td><code>{_html(detail_text)}</code></td>"
            "</tr>"
        )


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

    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


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


def _html(value: object) -> str:
    return escape(str(value), quote=True)


def _html_attr(value: object) -> str:
    text = str(value)
    safe = "".join(char for char in text if char.isalnum() or char in {"-", "_"})
    return escape(safe or "info", quote=True)
