"""Generate app-owned Streamlit diagnostics page skeletons."""

from __future__ import annotations

import ast
import keyword
import tempfile
from dataclasses import dataclass
from pathlib import Path

from litlaunch.exceptions import ConfigurationError

DEFAULT_FUNCTION_NAME = "render_litlaunch_diagnostics"
DEFAULT_PAGE_TITLE = "Runtime Diagnostics"


@dataclass(frozen=True)
class DiagnosticsPageOptions:
    """Options for generating an app-owned Streamlit diagnostics page."""

    output_path: str | Path
    function_name: str = DEFAULT_FUNCTION_NAME
    page_title: str = DEFAULT_PAGE_TITLE
    app_name: str | None = None
    profile_name: str | None = None
    project_root: str | Path | None = None
    overwrite: bool = False
    include_events: bool = True
    event_log_path: str | Path | None = None

    def __post_init__(self) -> None:
        output_path = _normalize_required_path(self.output_path, "output_path")
        function_name = str(self.function_name).strip()
        page_title = str(self.page_title).strip()
        if not function_name:
            raise ConfigurationError("diagnostics page function_name cannot be empty.")
        if not function_name.isidentifier() or keyword.iskeyword(function_name):
            raise ConfigurationError(
                f"diagnostics page function_name is not a valid Python identifier: "
                f"{function_name!r}"
            )
        if not page_title:
            raise ConfigurationError("diagnostics page page_title cannot be empty.")

        object.__setattr__(self, "output_path", output_path)
        object.__setattr__(self, "function_name", function_name)
        object.__setattr__(self, "page_title", page_title)
        object.__setattr__(
            self,
            "app_name",
            _normalize_optional_text(self.app_name),
        )
        object.__setattr__(
            self,
            "profile_name",
            _normalize_optional_text(self.profile_name),
        )
        if self.project_root is not None:
            object.__setattr__(
                self,
                "project_root",
                _normalize_required_path(self.project_root, "project_root"),
            )
        if self.event_log_path is not None:
            object.__setattr__(
                self,
                "event_log_path",
                _normalize_required_path(self.event_log_path, "event_log_path"),
            )


class DiagnosticsPageBuilder:
    """Write a readable Streamlit diagnostics page skeleton for a host app."""

    def __init__(
        self,
        output_path: str | Path,
        *,
        function_name: str = DEFAULT_FUNCTION_NAME,
        page_title: str = DEFAULT_PAGE_TITLE,
        app_name: str | None = None,
        profile_name: str | None = None,
        project_root: str | Path | None = None,
        overwrite: bool = False,
        include_events: bool = True,
        event_log_path: str | Path | None = None,
    ) -> None:
        self.options = DiagnosticsPageOptions(
            output_path=output_path,
            function_name=function_name,
            page_title=page_title,
            app_name=app_name,
            profile_name=profile_name,
            project_root=project_root,
            overwrite=overwrite,
            include_events=include_events,
            event_log_path=event_log_path,
        )

    def render(self) -> str:
        """Return the generated Python source."""

        source = _render_page_template(self.options)
        _validate_generated_source(source, self.options.function_name)
        return source

    def write(self) -> Path:
        """Write the generated page and return the resolved output path."""

        source = self.render()
        output_path = _resolve_output_path(self.options)
        if output_path.exists() and output_path.is_dir():
            raise ConfigurationError(
                f"diagnostics page output path is a directory: {output_path}"
            )
        if output_path.exists() and not self.options.overwrite:
            raise ConfigurationError(
                f"diagnostics page already exists: {output_path}. "
                "Use overwrite=True to replace it."
            )
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_text(output_path, source)
        except OSError as exc:
            raise ConfigurationError(
                f"Could not write diagnostics page {output_path}: {exc}"
            ) from exc
        return output_path


def create_diagnostics_page(
    *,
    output_path: str | Path,
    function_name: str = DEFAULT_FUNCTION_NAME,
    page_title: str = DEFAULT_PAGE_TITLE,
    app_name: str | None = None,
    profile_name: str | None = None,
    project_root: str | Path | None = None,
    overwrite: bool = False,
    include_events: bool = True,
    event_log_path: str | Path | None = None,
) -> Path:
    """Create an app-owned Streamlit diagnostics page skeleton."""

    return DiagnosticsPageBuilder(
        output_path,
        function_name=function_name,
        page_title=page_title,
        app_name=app_name,
        profile_name=profile_name,
        project_root=project_root,
        overwrite=overwrite,
        include_events=include_events,
        event_log_path=event_log_path,
    ).write()


def _render_page_template(options: DiagnosticsPageOptions) -> str:
    app_name = repr(options.app_name)
    profile_name = repr(options.profile_name)
    project_root = repr(str(options.project_root) if options.project_root else None)
    event_log_path = repr(
        str(options.event_log_path) if options.event_log_path else None
    )
    include_events = repr(bool(options.include_events))
    page_title = repr(options.page_title)
    generated_function = options.function_name
    template = '''"""Streamlit diagnostics page generated by LitLaunch.

This file is app-owned after generation. You can edit, theme, move, or replace
it to match your Streamlit application.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
import traceback
from typing import Any


APP_NAME = __APP_NAME__
PROFILE_NAME = __PROFILE_NAME__
PROJECT_ROOT = __PROJECT_ROOT__
INCLUDE_EVENTS = __INCLUDE_EVENTS__
EVENT_LOG_PATH = __EVENT_LOG_PATH__
PAGE_TITLE = __PAGE_TITLE__


def __FUNCTION_NAME__() -> None:
    """Render the generated LitLaunch diagnostics support page."""

    import streamlit as st

    _inject_litlaunch_styles(st)
    st.title(PAGE_TITLE)
    _render_page_intro(st)
    _render_notice(
        st,
        "info",
        "Generated by LitLaunch. This app-owned page summarizes runtime "
        "diagnostics and can be customized to match your support workflow.",
    )
    _render_notice(
        st,
        "warning",
        "Diagnostics are intended for support review. Sanitization is "
        "pattern-based, so review generated artifacts before sharing them.",
    )

    report, error_message, error_detail = _collect_diagnostics()
    if report is None:
        _render_collection_error(st, error_message, error_detail)
        return

    data = report.to_dict()
    _render_summary(st, data)
    _render_posture_cards(st, data)
    _render_artifact_actions(st, report)
    _render_sections(st, data)
    _render_event_trail(st)


def _collect_diagnostics() -> tuple[Any | None, str | None, str | None]:
    try:
        from litlaunch import DiagnosticCollector, load_profile

        profile = None
        profile_config = None
        if PROFILE_NAME:
            profile = load_profile(PROFILE_NAME, cwd=_project_root())
            profile_config = profile.config

        collector = DiagnosticCollector()
        report = collector.collect(
            app_path=profile_config.app_path if profile_config else None,
            mode=profile_config.mode if profile_config else "browser",
            browser=profile_config.browser if profile_config else "auto",
            host=profile_config.host if profile_config else "127.0.0.1",
            port=profile_config.port if profile_config else None,
            auto_port=profile_config.auto_port if profile_config else True,
            allow_browser_fallback=(
                profile_config.allow_browser_fallback if profile_config else True
            ),
            allow_network_exposure=(
                profile_config.allow_network_exposure if profile_config else False
            ),
            trust_mode=profile_config.trust_mode if profile_config else "development",
            cwd=profile_config.cwd if profile_config else _project_root(),
            extra_env=profile_config.extra_env if profile_config else None,
            streamlit_flags=profile_config.streamlit_flags if profile_config else {},
            streamlit_args=profile_config.streamlit_args if profile_config else (),
            app_args=profile_config.app_args if profile_config else (),
            profile_name=profile.name if profile else None,
            monitor_window=profile.monitor_window if profile else None,
            graceful_timeout_seconds=(
                profile.graceful_timeout_seconds if profile else None
            ),
            window_monitor_config=profile.window_monitor_config if profile else None,
        )
        return report, None, None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}", traceback.format_exc()


def _inject_litlaunch_styles(st: Any) -> None:
    st.markdown(
        """
<style>
.litlaunch-meta-row {
    align-items: center;
    display: flex;
    flex-wrap: wrap;
    gap: 0.55rem;
    margin: 0.35rem 0 0.2rem 0;
}
.litlaunch-meta-label {
    color: #1A73E8;
    font-size: 0.88rem;
    font-weight: 700;
}
.litlaunch-slug {
    background: #202326;
    border: 1px solid rgba(62, 180, 137, 0.35);
    border-radius: 0.35rem;
    color: #3EB489;
    display: inline-block;
    font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
    font-size: 0.84rem;
    font-weight: 700;
    line-height: 1.35;
    padding: 0.14rem 0.42rem;
}
.litlaunch-muted {
    color: #8B949E;
    font-size: 0.9rem;
    line-height: 1.45;
}
.litlaunch-notice {
    border-left: 3px solid #1A73E8;
    border-radius: 0.42rem;
    margin: 0.45rem 0;
    padding: 0.55rem 0.75rem;
}
.litlaunch-notice-info {
    background: rgba(26, 115, 232, 0.08);
    border-left-color: #1A73E8;
}
.litlaunch-notice-ok {
    background: rgba(62, 180, 137, 0.10);
    border-left-color: #3EB489;
}
.litlaunch-notice-warning {
    background: rgba(244, 241, 90, 0.13);
    border-left-color: #F4F15A;
}
.litlaunch-notice-error {
    background: rgba(231, 76, 60, 0.13);
    border-left-color: #E74C3C;
}
.litlaunch-posture-card {
    background: #202326;
    border: 1px solid rgba(232, 232, 232, 0.12);
    border-left: 4px solid #1A73E8;
    border-radius: 0.48rem;
    min-height: 6rem;
    padding: 0.72rem 0.78rem;
}
.litlaunch-posture-label {
    color: #1A73E8;
    font-size: 0.82rem;
    font-weight: 800;
    margin-bottom: 0.35rem;
}
.litlaunch-posture-value {
    color: #E8E8E8;
    font-size: 1.18rem;
    font-weight: 750;
    line-height: 1.25;
}
.litlaunch-posture-status {
    color: #8B949E;
    font-size: 0.78rem;
    margin-top: 0.38rem;
}
.litlaunch-status-ok {
    border-left-color: #3EB489;
}
.litlaunch-status-info {
    border-left-color: #F4F15A;
}
.litlaunch-status-warning {
    border-left-color: #F4F15A;
}
.litlaunch-status-error {
    border-left-color: #E74C3C;
}
.litlaunch-row {
    background: rgba(32, 35, 38, 0.72);
    border: 1px solid rgba(232, 232, 232, 0.10);
    border-left: 3px solid #1A73E8;
    border-radius: 0.42rem;
    margin: 0.42rem 0;
    padding: 0.55rem 0.7rem;
}
.litlaunch-row-title {
    color: #E8E8E8;
    font-weight: 750;
}
.litlaunch-row-message {
    color: #C9D1D9;
    margin-top: 0.12rem;
}
.litlaunch-row-detail {
    color: #8B949E;
    font-size: 0.86rem;
    margin-top: 0.28rem;
}
.litlaunch-pill {
    border-radius: 999px;
    display: inline-block;
    font-size: 0.72rem;
    font-weight: 800;
    margin-right: 0.45rem;
    padding: 0.05rem 0.42rem;
    text-transform: uppercase;
}
.litlaunch-pill-ok {
    background: rgba(62, 180, 137, 0.14);
    color: #3EB489;
}
.litlaunch-pill-info {
    background: rgba(244, 241, 90, 0.13);
    color: #F4F15A;
}
.litlaunch-pill-warning {
    background: rgba(244, 241, 90, 0.13);
    color: #F4F15A;
}
.litlaunch-pill-error {
    background: rgba(231, 76, 60, 0.14);
    color: #E74C3C;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _render_page_intro(st: Any) -> None:
    st.caption(
        "A Streamlit-native support surface generated by LitLaunch and owned by "
        "this application."
    )
    if APP_NAME or PROFILE_NAME:
        parts: list[str] = []
        if APP_NAME:
            parts.append(_meta_pair("App", APP_NAME))
        if PROFILE_NAME:
            parts.append(_meta_pair("LitLaunch profile", PROFILE_NAME))
        st.markdown(
            f"<div class='litlaunch-meta-row'>{''.join(parts)}</div>",
            unsafe_allow_html=True,
        )


def _render_collection_error(st: Any, message: str | None, detail: str | None) -> None:
    st.error("Could not collect LitLaunch diagnostics.")
    if message:
        st.caption(message)
    if detail:
        with st.expander("Technical details"):
            st.code(detail)


def _render_summary(st: Any, data: dict[str, Any]) -> None:
    st.subheader("Runtime Summary")
    columns = st.columns(4)
    status = "OK" if data.get("ok") else "Needs attention"
    columns[0].metric("Diagnostics", status)
    columns[1].metric("Errors", data.get("errors", 0))
    columns[2].metric("Warnings", data.get("warnings", 0))
    columns[3].metric("LitLaunch", data.get("litlaunch_version", "unknown"))

    metadata = {
        "App": APP_NAME or "not configured",
        "Profile": PROFILE_NAME or "not configured",
        "Project root": str(_project_root()),
        "Generated": str(data.get("generated_at_utc", "unknown")),
    }
    with st.expander("Runtime metadata", expanded=False):
        _render_key_value_rows(st, metadata)


def _render_posture_cards(st: Any, data: dict[str, Any]) -> None:
    st.subheader("Posture")
    sections = _sections(data)
    cards = (
        (
            "Runtime Governance",
            _item_message(sections, "Runtime Governance", "Launch posture"),
            _item_status(sections, "Runtime Governance", "Launch posture"),
        ),
        (
            "Runtime Exposure",
            _item_message(sections, "Runtime Exposure", "Exposure scope"),
            _item_status(sections, "Runtime Exposure", "Exposure scope"),
        ),
        (
            "Transport Security",
            _item_message(sections, "Transport Security", "TLS configuration"),
            _item_status(sections, "Transport Security", "TLS configuration"),
        ),
        (
            "Browser/Platform",
            _item_message(sections, "Browsers", "Browser resolution"),
            _item_status(sections, "Browsers", "Browser resolution"),
        ),
    )
    columns = st.columns(len(cards))
    for column, (label, value, status) in zip(columns, cards):
        with column:
            _render_posture_card(st, label, _compact_metric_value(label, value), status)


def _render_artifact_actions(st: Any, report: Any) -> None:
    from litlaunch import (
        HTMLDiagnosticsRenderer,
        JSONDiagnosticsRenderer,
        SanitizedBundleRenderer,
    )

    html_report = HTMLDiagnosticsRenderer(include_details=True).render(report)
    json_report = JSONDiagnosticsRenderer().render(report)
    support_bundle = SanitizedBundleRenderer(include_details=True).render(report)
    artifacts = {
        "HTML report": {
            "file_name": "litlaunch-report.html",
            "content": html_report,
            "mime": "text/html",
        },
        "JSON diagnostics": {
            "file_name": "litlaunch-report.json",
            "content": json_report,
            "mime": "application/json",
        },
        "Support bundle": {
            "file_name": "litlaunch-support-bundle.txt",
            "content": support_bundle,
            "mime": "text/plain",
        },
    }

    st.subheader("Support Artifacts")
    _render_muted(
        st,
        "Downloads are generated in memory. Writes create persistent artifacts "
        "under .litlaunch/reports/.",
    )
    download_column, write_column = st.columns(2)
    _render_download_artifact_group(st, download_column, artifacts)
    _render_write_artifact_group(st, write_column, artifacts)


def _render_download_artifact_group(
    st: Any,
    column: Any,
    artifacts: dict[str, dict[str, str]],
) -> None:
    with column:
        label = st.selectbox(
            "Download Artifact",
            options=list(artifacts),
            key="litlaunch_download_artifact_select",
        )
        artifact = artifacts[label]
        st.download_button(
            "Download",
            data=artifact["content"].encode("utf-8"),
            file_name=artifact["file_name"],
            mime=artifact["mime"],
            key="litlaunch_download_artifact_button",
        )


def _render_write_artifact_group(
    st: Any,
    column: Any,
    artifacts: dict[str, dict[str, str]],
) -> None:
    with column:
        label = st.selectbox(
            "Write Artifact",
            options=list(artifacts),
            key="litlaunch_write_artifact_select",
        )
        artifact = artifacts[label]
        if st.button("Write", key="litlaunch_write_artifact_button"):
            path = _write_report_artifact(artifact["file_name"], artifact["content"])
            _render_notice(st, "ok", f"Wrote {label}.")
            st.code(str(path))


def _write_report_artifact(file_name: str, content: str) -> Path:
    from litlaunch.artifacts import reports_dir

    report_dir = reports_dir(_project_root(), create=True)
    output_path = report_dir / file_name
    output_path.write_text(content, encoding="utf-8")
    return output_path


def _render_sections(st: Any, data: dict[str, Any]) -> None:
    st.subheader("Diagnostics Details")
    sections = _sections(data)
    for section in data.get("sections", []):
        title = str(section.get("title", "Untitled section"))
        status = _section_status(sections, title)
        expanded = title in {
            "Runtime Governance",
            "Runtime Exposure",
            "Transport Security",
        }
        with st.expander(f"{title} - {status}", expanded=expanded):
            for item in section.get("items", []):
                _render_item(st, item)


def _render_item(st: Any, item: dict[str, Any]) -> None:
    status = str(item.get("status", "info")).lower()
    name = str(item.get("name", "Item"))
    message = str(item.get("message", ""))
    detail = item.get("detail")
    _render_diagnostic_row(st, status, name, message, str(detail) if detail else None)


def _render_event_trail(st: Any) -> None:
    if not INCLUDE_EVENTS:
        return

    st.subheader("Runtime Event Trail")
    if not EVENT_LOG_PATH:
        _render_notice(
            st,
            "info",
            "No runtime event log path is configured for this generated page.",
        )
        return

    event_path = _resolve_project_path(EVENT_LOG_PATH)
    if not event_path.is_file():
        _render_notice(st, "info", "No runtime event log found.")
        st.code(str(event_path))
        return

    lines = event_path.read_text(encoding="utf-8", errors="replace").splitlines()
    recent_lines = lines[-80:]
    _render_muted(st, f"Showing {len(recent_lines)} recent lines from:")
    st.code(str(event_path))
    st.code("\\n".join(recent_lines) or "No events recorded yet.")


def _render_posture_card(st: Any, label: str, value: str, status: str) -> None:
    status_class = _status_class(status)
    status_label = _status_label(status)
    st.markdown(
        (
            f"<div class='litlaunch-posture-card {status_class}'>"
            f"<div class='litlaunch-posture-label'>{_html(label)}</div>"
            f"<div class='litlaunch-posture-value'>{_html(value)}</div>"
            f"<div class='litlaunch-posture-status'>{_html(status_label)}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_diagnostic_row(
    st: Any,
    status: str,
    name: str,
    message: str,
    detail: str | None,
) -> None:
    normalized = _normalize_status(status)
    detail_html = (
        f"<div class='litlaunch-row-detail'>{_html(detail)}</div>" if detail else ""
    )
    st.markdown(
        (
            f"<div class='litlaunch-row {_status_class(normalized)}'>"
            f"<span class='litlaunch-pill litlaunch-pill-{normalized}'>"
            f"{_html(_status_label(normalized))}</span>"
            f"<span class='litlaunch-row-title'>{_html(name)}</span>"
            f"<div class='litlaunch-row-message'>{_html(message)}</div>"
            f"{detail_html}</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_key_value_rows(st: Any, rows: dict[str, Any]) -> None:
    for label, value in rows.items():
        st.markdown(
            (
                "<div class='litlaunch-meta-row'>"
                f"<span class='litlaunch-meta-label'>{_html(str(label))}</span>"
                f"<span class='litlaunch-slug'>{_html(str(value))}</span>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )


def _render_notice(st: Any, status: str, message: str) -> None:
    normalized = _normalize_status(status)
    st.markdown(
        (
            f"<div class='litlaunch-notice litlaunch-notice-{normalized}'>"
            f"{_html(message)}</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_muted(st: Any, message: str) -> None:
    st.markdown(
        f"<div class='litlaunch-muted'>{_html(message)}</div>",
        unsafe_allow_html=True,
    )


def _meta_pair(label: str, value: str) -> str:
    return (
        f"<span class='litlaunch-meta-label'>{_html(label)}</span>"
        f"<span class='litlaunch-slug'>{_html(value)}</span>"
    )


def _html(value: Any) -> str:
    return escape(str(value), quote=True)


def _normalize_status(status: str) -> str:
    normalized = str(status or "info").lower()
    if normalized in {"ok", "info", "warning", "error"}:
        return normalized
    return "info"


def _status_class(status: str) -> str:
    return f"litlaunch-status-{_normalize_status(status)}"


def _status_label(status: str) -> str:
    normalized = _normalize_status(status)
    if normalized == "ok":
        return "OK"
    if normalized == "warning":
        return "Warning"
    if normalized == "error":
        return "Error"
    return "Info"


def _sections(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        str(section.get("title", "")): list(section.get("items", []))
        for section in data.get("sections", [])
    }


def _section_status(sections: dict[str, list[dict[str, Any]]], title: str) -> str:
    items = sections.get(title, [])
    statuses = {str(item.get("status", "info")).lower() for item in items}
    if "error" in statuses:
        return "error"
    if "warning" in statuses:
        return "warning"
    if "ok" in statuses:
        return "ok"
    return "info"


def _item_message(
    sections: dict[str, list[dict[str, Any]]],
    title: str,
    item_name: str,
) -> str | None:
    for item in sections.get(title, []):
        if item.get("name") == item_name:
            return str(item.get("message", ""))
    return None


def _item_status(
    sections: dict[str, list[dict[str, Any]]],
    title: str,
    item_name: str,
) -> str:
    for item in sections.get(title, []):
        if item.get("name") == item_name:
            return str(item.get("status", "info")).lower()
    return _section_status(sections, title)


def _compact_metric_value(label: str, value: str | None) -> str:
    if not value:
        return "not reported"
    normalized = value.strip()
    if label == "Transport Security":
        if normalized == "not_configured":
            return "No TLS"
        if normalized == "configured":
            return "TLS"
        if normalized == "incomplete":
            return "Incomplete"
    if label == "Browser/Platform":
        if "Microsoft Edge" in normalized:
            return "Edge"
        if "Chrome" in normalized or "Chromium" in normalized:
            return "Chrome"
        if "Default browser" in normalized:
            return "Default"
    if normalized == "wildcard_bind":
        return "wildcard"
    return normalized.replace("_", " ")


def _project_root() -> Path:
    if PROJECT_ROOT:
        return Path(PROJECT_ROOT).expanduser().resolve()
    return Path.cwd()


def _resolve_project_path(value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return _project_root() / path
'''
    return (
        template.replace("__APP_NAME__", app_name)
        .replace("__PROFILE_NAME__", profile_name)
        .replace("__PROJECT_ROOT__", project_root)
        .replace("__INCLUDE_EVENTS__", include_events)
        .replace("__EVENT_LOG_PATH__", event_log_path)
        .replace("__PAGE_TITLE__", page_title)
        .replace("__FUNCTION_NAME__", generated_function)
    )


def _validate_generated_source(source: str, function_name: str) -> None:
    try:
        module = ast.parse(source)
    except SyntaxError as exc:
        raise ConfigurationError(
            f"Generated diagnostics page is invalid Python: {exc}"
        ) from exc
    if not any(
        isinstance(node, ast.FunctionDef) and node.name == function_name
        for node in module.body
    ):
        raise ConfigurationError(
            f"Generated diagnostics page did not define {function_name!r}."
        )


def _resolve_output_path(options: DiagnosticsPageOptions) -> Path:
    output_path = Path(options.output_path).expanduser()
    project_root = (
        Path(options.project_root).expanduser().resolve(strict=False)
        if options.project_root is not None
        else None
    )
    if output_path.is_absolute():
        return output_path.resolve(strict=False)

    base = project_root if project_root is not None else Path.cwd()
    resolved = (base / output_path).resolve(strict=False)
    if project_root is not None and not _is_relative_to(resolved, project_root):
        raise ConfigurationError(
            "diagnostics page output_path must stay under project_root unless "
            "an absolute output path is provided."
        )
    return resolved


def _atomic_write_text(path: Path, text: str) -> None:
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(text)
    try:
        temp_path.replace(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _normalize_required_path(value: str | Path, name: str) -> Path:
    raw = str(value).strip()
    if not raw:
        raise ConfigurationError(f"diagnostics page {name} cannot be empty.")
    return Path(raw)


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
