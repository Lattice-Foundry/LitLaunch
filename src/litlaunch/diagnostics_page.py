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
    event_log_path = repr(
        str(options.event_log_path) if options.event_log_path else None
    )
    include_events = repr(bool(options.include_events))
    page_title = repr(options.page_title)
    generated_function = options.function_name
    return f'''"""Streamlit diagnostics page generated by LitLaunch.

This file is app-owned after generation. You can edit, theme, move, or replace
it to match your Streamlit application.
"""

from __future__ import annotations


APP_NAME = {app_name}
PROFILE_NAME = {profile_name}
INCLUDE_EVENTS = {include_events}
EVENT_LOG_PATH = {event_log_path}


def {generated_function}() -> None:
    """Render the generated LitLaunch diagnostics page skeleton."""

    import streamlit as st

    st.title({page_title})
    if APP_NAME:
        st.caption(f"App: {{APP_NAME}}")
    if PROFILE_NAME:
        st.caption(f"LitLaunch profile: {{PROFILE_NAME}}")

    st.info(
        "Generated by LitLaunch. This page is owned by your app and can be "
        "customized to match your support workflow."
    )
    st.write("Diagnostics content will be rendered here in a later generator pass.")

    if INCLUDE_EVENTS and EVENT_LOG_PATH:
        st.caption(f"Runtime event log: {{EVENT_LOG_PATH}}")
'''


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
