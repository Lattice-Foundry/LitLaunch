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

    st.title(PAGE_TITLE)
    if APP_NAME:
        st.caption(f"App: {APP_NAME}")
    if PROFILE_NAME:
        st.caption(f"LitLaunch profile: {PROFILE_NAME}")

    st.info(
        "Generated by LitLaunch. This app-owned page summarizes runtime "
        "diagnostics and can be customized to match your support workflow."
    )
    st.warning(
        "Diagnostics are intended for support review. Sanitization is "
        "pattern-based, so review generated artifacts before sharing them."
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
        st.json(metadata)


def _render_posture_cards(st: Any, data: dict[str, Any]) -> None:
    st.subheader("Posture")
    sections = _sections(data)
    cards = (
        (
            "Runtime Governance",
            _item_message(sections, "Runtime Governance", "Launch posture"),
            _section_status(sections, "Runtime Governance"),
        ),
        (
            "Runtime Exposure",
            _item_message(sections, "Runtime Exposure", "Exposure scope"),
            _section_status(sections, "Runtime Exposure"),
        ),
        (
            "Transport Security",
            _item_message(sections, "Transport Security", "TLS configuration"),
            _section_status(sections, "Transport Security"),
        ),
        (
            "Browser/Platform",
            _item_message(sections, "Browsers", "Browser resolution"),
            _section_status(sections, "Browsers"),
        ),
    )
    columns = st.columns(len(cards))
    for column, (label, value, status) in zip(columns, cards):
        column.metric(label, value or "not reported", status)


def _render_artifact_actions(st: Any, report: Any) -> None:
    from litlaunch import (
        HTMLDiagnosticsRenderer,
        JSONDiagnosticsRenderer,
        SanitizedBundleRenderer,
    )

    html_report = HTMLDiagnosticsRenderer(include_details=True).render(report)
    json_report = JSONDiagnosticsRenderer().render(report)
    support_bundle = SanitizedBundleRenderer(include_details=True).render(report)

    st.subheader("Support Artifacts")
    st.caption(
        "Downloads are generated in memory. Files are written under "
        ".litlaunch/reports/ only when you click a write button."
    )
    columns = st.columns(3)
    _render_artifact_column(
        st,
        columns[0],
        label="HTML report",
        file_name="litlaunch-report.html",
        content=html_report,
        mime="text/html",
        button_key="litlaunch_html",
    )
    _render_artifact_column(
        st,
        columns[1],
        label="JSON diagnostics",
        file_name="litlaunch-report.json",
        content=json_report,
        mime="application/json",
        button_key="litlaunch_json",
    )
    _render_artifact_column(
        st,
        columns[2],
        label="Support bundle",
        file_name="litlaunch-support-bundle.txt",
        content=support_bundle,
        mime="text/plain",
        button_key="litlaunch_bundle",
    )


def _render_artifact_column(
    st: Any,
    column: Any,
    *,
    label: str,
    file_name: str,
    content: str,
    mime: str,
    button_key: str,
) -> None:
    with column:
        st.download_button(
            f"Download {label}",
            data=content.encode("utf-8"),
            file_name=file_name,
            mime=mime,
            key=f"{button_key}_download",
        )
        if st.button(f"Write {label}", key=f"{button_key}_write"):
            path = _write_report_artifact(file_name, content)
            st.success(f"Wrote {path}")


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
    line = f"**{name}:** {message}"
    if status == "error":
        st.error(line)
    elif status == "warning":
        st.warning(line)
    elif status == "ok":
        st.success(line)
    else:
        st.info(line)
    if detail:
        st.caption(str(detail))


def _render_event_trail(st: Any) -> None:
    if not INCLUDE_EVENTS:
        return

    st.subheader("Runtime Event Trail")
    if not EVENT_LOG_PATH:
        st.info("No runtime event log path is configured for this generated page.")
        return

    event_path = _resolve_project_path(EVENT_LOG_PATH)
    if not event_path.is_file():
        st.info(f"No runtime event log found at {event_path}.")
        return

    lines = event_path.read_text(encoding="utf-8", errors="replace").splitlines()
    recent_lines = lines[-80:]
    st.caption(f"Showing {len(recent_lines)} recent lines from {event_path}.")
    st.code("\\n".join(recent_lines) or "No events recorded yet.")


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
