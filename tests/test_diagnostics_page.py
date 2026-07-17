import ast
import builtins
import json

import pytest

from litlaunch import (
    DiagnosticsPageBuilder,
    DiagnosticsPageOptions,
    create_diagnostics_page,
)
from litlaunch.exceptions import ConfigurationError


def _function_names(source: str) -> set[str]:
    module = ast.parse(source)
    return {node.name for node in module.body if isinstance(node, ast.FunctionDef)}


def _source_for(**kwargs) -> str:
    return DiagnosticsPageBuilder("diagnostics.py", **kwargs).render()


def test_create_diagnostics_page_writes_valid_python(tmp_path):
    output_path = create_diagnostics_page(
        output_path=tmp_path / "ui" / "litlaunch_diagnostics.py",
        app_name="RoleThread Lite",
        profile_name="rolethread-webapp",
    )

    source = output_path.read_text(encoding="utf-8")
    assert output_path.is_file()
    assert "render_litlaunch_diagnostics" in _function_names(source)
    assert "RoleThread Lite" in source
    assert "rolethread-webapp" in source
    assert "import streamlit as st" in source
    assert "Runtime Summary" in source
    assert "Support Artifacts" in source
    assert "This app-owned page summarizes runtime diagnostics" not in source
    assert "Diagnostics are intended for support review" not in source


def test_builder_api_writes_custom_function_and_creates_parent(tmp_path):
    output_path = tmp_path / "nested" / "support" / "runtime_page.py"

    written = DiagnosticsPageBuilder(
        output_path,
        function_name="render_support_page",
        page_title="Support Diagnostics",
    ).write()

    source = written.read_text(encoding="utf-8")
    assert written == output_path
    assert "render_support_page" in _function_names(source)
    assert "Support Diagnostics" in source


def test_builder_render_returns_parseable_source_without_writing(tmp_path):
    builder = DiagnosticsPageBuilder(tmp_path / "diagnostics.py")

    source = builder.render()

    assert "render_litlaunch_diagnostics" in _function_names(source)
    assert not (tmp_path / "diagnostics.py").exists()


def test_generated_page_contains_real_diagnostics_sections():
    source = _source_for()

    assert "Diagnostics content will be rendered here" not in source
    assert "litlaunch-meta-label" in source
    assert "litlaunch-slug" in source
    assert "litlaunch-summary-value" in source
    assert "litlaunch-section" in source
    assert "litlaunch-posture-card" in source
    assert "litlaunch-row" in source
    assert "Runtime Summary" in source
    assert "Posture" in source
    assert "Operational Snapshot" in source
    assert "Runtime Event Trail" in source
    assert "Raw Runtime Event Trail" in source
    assert "litlaunch-console" in source
    assert "Diagnostics Status Mix" in source
    assert "Runtime Event Mix" in source
    assert "Section Attention Map" in source
    assert "Diagnostics Details" in source
    assert "Runtime Governance" in source
    assert "Runtime Exposure" in source
    assert "Transport Security" in source
    assert "Browser/Platform" in source
    assert "No TLS" in source
    assert "Edge" in source


def test_generated_page_contains_expected_helper_functions():
    source = _source_for()
    functions = _function_names(source)

    assert {
        "render_litlaunch_diagnostics",
        "_collect_diagnostics",
        "_render_summary",
        "_render_posture_cards",
        "_render_operational_snapshot",
        "_render_status_mix_chart",
        "_render_event_mix_chart",
        "_render_section_attention_chart",
        "_render_artifact_actions",
        "_render_download_artifact_group",
        "_render_write_artifact_group",
        "_render_sections",
        "_render_event_trail",
        "_render_runtime_sessions",
        "_render_runtime_session_summary",
        "_render_runtime_session_timeline",
        "_render_runtime_session_console",
        "_console_event_line",
        "_console_status_label",
        "_console_phase_label",
        "_console_event_message",
        "_inject_litlaunch_styles",
        "_theme_tokens",
        "_chart_theme_tokens",
        "_chart_config",
        "_chart_axis_config",
        "_render_page_intro",
        "_render_summary_value",
        "_render_posture_card",
        "_render_diagnostic_row",
        "_render_section_spacer",
        "_status_mix_rows",
        "_section_attention_rows",
        "_event_category_counts",
        "_extract_event_category",
        "_extract_json_event_category",
        "_runtime_event_records_from_lines",
        "_parse_runtime_event_record",
        "_group_runtime_sessions",
        "_summarize_runtime_session",
        "_friendly_event_name",
        "_format_duration",
        "_safe_detail",
        "_runtime_event_log_path",
        "_item_status",
        "_compact_metric_value",
        "_status_class",
    }.issubset(functions)


def test_generated_page_places_runtime_events_after_main_sections():
    source = _source_for()

    assert source.index("_render_artifact_actions(st, report)") < source.index(
        "_render_sections(st, data)"
    )
    assert source.index("_render_sections(st, data)") < source.index(
        "_render_runtime_sessions(st)"
    )


def test_generated_page_imports_existing_litlaunch_apis():
    source = _source_for()

    assert "from litlaunch import DiagnosticCollector, load_profile" in source
    assert "HTMLDiagnosticsRenderer" in source
    assert "JSONDiagnosticsRenderer" in source
    assert "SanitizedBundleRenderer" in source
    assert "from litlaunch.artifacts import reports_dir" in source


def test_generated_page_reflects_artifact_paths_without_autowrite():
    source = _source_for()

    assert ".litlaunch/reports/" in source
    assert "Downloads are generated in memory" in source
    assert "Writes create persistent artifacts" in source
    assert "Download Artifact" in source
    assert "Write Artifact" in source
    assert "litlaunch-report.html" in source
    assert "litlaunch-report.json" in source
    assert "litlaunch-support-bundle.txt" in source
    assert "Write HTML report" not in source
    assert "Download HTML report" not in source


def test_generated_page_includes_project_and_event_options():
    source = _source_for(
        project_root="X:/apps/example",
        event_log_path=".litlaunch/events/runtime.log",
        event_log_env_var="ROLETHREAD_LAUNCHER_LOG_PATH",
    )

    assert "PROJECT_ROOT = 'X:" in source
    assert "apps" in source
    assert "example" in source
    assert "INCLUDE_EVENTS = True" in source
    assert "EVENT_LOG_PATH = '.litlaunch" in source
    assert "EVENT_LOG_ENV_VAR = 'ROLETHREAD_LAUNCHER_LOG_PATH'" in source
    assert "runtime.log" in source
    assert "_runtime_event_log_path" in source
    assert "Runtime Event Trail" in source


def test_generated_page_defaults_to_auto_theme():
    options = DiagnosticsPageOptions(output_path="diagnostics.py")
    source = _source_for()

    assert options.theme == "auto"
    assert "THEME = 'auto'" in source
    assert "_THEME_DARK" in source
    assert "_THEME_LIGHT" in source
    assert "_THEME_AUTO" in source
    assert "light_page_override" in source
    assert "st.vega_lite_chart" in source
    assert 'width="stretch"' in source
    assert "use_container_width" not in source
    assert "chart_bg" in source


@pytest.mark.parametrize("theme", ["auto", "light", "dark"])
def test_generated_page_accepts_theme_modes(theme):
    source = _source_for(theme=theme)

    assert f"THEME = '{theme}'" in source
    assert "var(--primary-color" in source


def test_generated_page_rejects_unknown_theme(tmp_path):
    with pytest.raises(ConfigurationError, match="theme"):
        DiagnosticsPageBuilder(tmp_path / "diagnostics.py", theme="neon")


def test_generated_page_rejects_invalid_event_log_env_var(tmp_path):
    with pytest.raises(ConfigurationError, match="event_log_env_var"):
        DiagnosticsPageBuilder(
            tmp_path / "diagnostics.py",
            event_log_env_var="bad-name",
        )


def test_generated_page_can_disable_event_trail():
    source = _source_for(include_events=False)

    assert "INCLUDE_EVENTS = False" in source
    assert "EVENT_LOG_PATH = None" in source


def test_generated_page_has_no_rolethread_names_unless_configured():
    source = _source_for()

    assert "RoleThread" not in source
    assert "rolethread-webapp" not in source


def test_generated_page_status_helpers_map_colors_sensibly():
    namespace: dict[str, object] = {}
    exec(_source_for(), namespace)  # noqa: S102 - generated source is under test.

    status_class = namespace["_status_class"]
    compact_metric_value = namespace["_compact_metric_value"]

    assert status_class("ok") == "litlaunch-status-ok"
    assert status_class("warning") == "litlaunch-status-warning"
    assert status_class("error") == "litlaunch-status-error"
    assert status_class("unknown") == "litlaunch-status-info"
    assert compact_metric_value("Transport Security", "not_configured") == "No TLS"
    assert (
        compact_metric_value("Browser/Platform", "Selected Microsoft Edge.") == "Edge"
    )


def test_generated_page_event_log_resolver_prefers_env_var(monkeypatch):
    namespace: dict[str, object] = {}
    source = _source_for(
        project_root="X:/project",
        event_log_path=".litlaunch/fallback.log",
        event_log_env_var="LITLAUNCH_EVENT_LOG",
    )
    exec(source, namespace)  # noqa: S102 - generated source is under test.
    monkeypatch.setenv("LITLAUNCH_EVENT_LOG", "runtime/from-env.log")

    event_log_path = namespace["_runtime_event_log_path"]()

    assert event_log_path.parts[-2:] == ("runtime", "from-env.log")


def test_generated_page_counts_jsonl_runtime_event_categories(tmp_path):
    event_path = tmp_path / ".litlaunch" / "runtime-events.log"
    event_path.parent.mkdir()
    categories = [
        "launch",
        "backend",
        "health",
        "browser",
        "monitor",
        "shutdown",
        "hook",
        "port",
    ]
    lines = [
        json.dumps(
            {
                "timestamp": "2026-05-24T12:00:00+00:00",
                "level": "info",
                "category": category,
                "name": f"{category}_event",
                "message": f"{category.title()} event.",
                "details": {"secret": "not counted or rendered"},
            },
            sort_keys=True,
        )
        for category in categories
    ]
    lines.extend(
        [
            "not json",
            "{not json",
            json.dumps(["not", "an", "object"]),
            json.dumps({"category": ""}),
            json.dumps({"category": 123}),
            json.dumps({"details": {"category": "ignored"}}),
        ]
    )
    event_path.write_text("\n".join(lines), encoding="utf-8")

    namespace: dict[str, object] = {}
    source = _source_for(
        project_root=tmp_path,
        event_log_path=".litlaunch/runtime-events.log",
    )
    exec(source, namespace)  # noqa: S102 - generated source is under test.

    event_category_counts = namespace["_event_category_counts"]

    assert event_category_counts() == {category: 1 for category in categories}


def test_generated_page_groups_runtime_sessions_newest_first():
    namespace: dict[str, object] = {}
    exec(_source_for(), namespace)  # noqa: S102 - generated source is under test.
    records_from_lines = namespace["_runtime_event_records_from_lines"]
    group_runtime_sessions = namespace["_group_runtime_sessions"]

    lines = [
        json.dumps(
            {
                "timestamp": "2026-05-24T12:00:00+00:00",
                "level": "info",
                "category": "launch",
                "name": "launch_planned",
                "message": "Runtime launch planned.",
                "details": {"mode": "browser"},
            },
        ),
        json.dumps(
            {
                "timestamp": "2026-05-24T12:00:01+00:00",
                "level": "info",
                "category": "backend",
                "name": "backend_started",
                "message": "Backend process started.",
                "details": {"host": "127.0.0.1", "port": 8501},
            },
        ),
        json.dumps(
            {
                "timestamp": "2026-05-24T12:05:00+00:00",
                "level": "info",
                "category": "launch",
                "name": "launch_planned",
                "message": "Runtime launch planned.",
                "details": {"mode": "webapp"},
            },
        ),
        json.dumps(
            {
                "timestamp": "2026-05-24T12:05:02+00:00",
                "level": "info",
                "category": "browser",
                "name": "browser_launched",
                "message": "Browser launched.",
                "details": {"browser": "Microsoft Edge", "mode": "webapp"},
            },
        ),
        "not json",
    ]

    sessions = group_runtime_sessions(records_from_lines(lines))

    assert len(sessions) == 2
    assert sessions[0][0]["details"]["mode"] == "webapp"
    assert sessions[1][0]["details"]["mode"] == "browser"


def test_generated_page_summarizes_runtime_session_duration_and_status():
    namespace: dict[str, object] = {}
    exec(_source_for(), namespace)  # noqa: S102 - generated source is under test.
    records_from_lines = namespace["_runtime_event_records_from_lines"]
    summarize_runtime_session = namespace["_summarize_runtime_session"]

    records = records_from_lines(
        [
            json.dumps(
                {
                    "timestamp": "2026-05-24T12:00:00+00:00",
                    "level": "info",
                    "category": "launch",
                    "name": "launch_planned",
                    "message": "Runtime launch planned.",
                    "details": {
                        "mode": "webapp",
                        "browser": "edge",
                        "host": "127.0.0.1",
                        "port": 8501,
                    },
                },
            ),
            json.dumps(
                {
                    "timestamp": "2026-05-24T12:00:01+00:00",
                    "level": "info",
                    "category": "backend",
                    "name": "backend_started",
                    "message": "Backend process started.",
                    "details": {"pid": 1234, "host": "127.0.0.1", "port": 8501},
                },
            ),
            json.dumps(
                {
                    "timestamp": "2026-05-24T12:00:10+00:00",
                    "level": "info",
                    "category": "monitor",
                    "name": "monitor_started",
                    "message": "Window monitoring started.",
                    "details": {"target": "RoleThread Lite", "mode": "webapp"},
                },
            ),
            json.dumps(
                {
                    "timestamp": "2026-05-24T12:00:38.800000+00:00",
                    "level": "info",
                    "category": "port",
                    "name": "port_released",
                    "message": "Backend port released.",
                    "details": {"host": "127.0.0.1", "port": 8501},
                },
            ),
        ]
    )

    summary = summarize_runtime_session(records)

    assert summary["status"] == "Clean shutdown"
    assert summary["status_level"] == "ok"
    assert summary["title"] == "Webapp launched in Edge"
    assert "Backend healthy on 127.0.0.1:8501" in summary["subtitle"]
    assert "Monitoring window: RoleThread Lite" in summary["subtitle"]
    assert summary["fields"]["Duration"] == "38.8s"
    assert summary["fields"]["Backend PID"] == "1234"


def test_generated_page_summarizes_missing_shutdown_as_running():
    namespace: dict[str, object] = {}
    exec(_source_for(), namespace)  # noqa: S102 - generated source is under test.
    records_from_lines = namespace["_runtime_event_records_from_lines"]
    summarize_runtime_session = namespace["_summarize_runtime_session"]

    records = records_from_lines(
        [
            json.dumps(
                {
                    "timestamp": "2026-05-24T12:00:00+00:00",
                    "level": "info",
                    "category": "launch",
                    "name": "launch_planned",
                    "message": "Runtime launch planned.",
                    "details": {"mode": "browser"},
                },
            ),
            json.dumps(
                {
                    "timestamp": "2026-05-24T12:00:01+00:00",
                    "level": "info",
                    "category": "health",
                    "name": "health_ready",
                    "message": "Health check passed.",
                    "details": {"host": "127.0.0.1", "port": 8501},
                },
            ),
        ]
    )

    summary = summarize_runtime_session(records)

    assert summary["status"] == "Running"
    assert summary["fields"]["Duration"] == "running"


def test_generated_page_friendly_event_labels_and_malformed_events():
    namespace: dict[str, object] = {}
    exec(_source_for(), namespace)  # noqa: S102 - generated source is under test.
    friendly_event_name = namespace["_friendly_event_name"]
    records_from_lines = namespace["_runtime_event_records_from_lines"]

    assert friendly_event_name("health_ready") == "Health check passed"
    assert friendly_event_name("custom_runtime_event") == "Custom Runtime Event"
    assert records_from_lines(["{malformed", json.dumps(["not", "object"])]) == []


def test_generated_page_formats_console_replay_lines():
    namespace: dict[str, object] = {}
    exec(_source_for(), namespace)  # noqa: S102 - generated source is under test.
    console_event_line = namespace["_console_event_line"]
    console_status_label = namespace["_console_status_label"]

    assert console_status_label("info") == "[   ok   ]"
    assert console_status_label("warning") == "[  warn  ]"
    assert console_status_label("error") == "[ error  ]"

    backend_line = console_event_line(
        {
            "name": "backend_started",
            "category": "backend",
            "level": "info",
            "details": {"pid": 1234, "host": "127.0.0.1", "port": 8501},
        }
    )
    warning_line = console_event_line(
        {
            "name": "hook_failed",
            "category": "hook",
            "level": "error",
            "details": {"label": "Cloud sync"},
        }
    )

    assert "[   ok   ]" in backend_line
    assert "Backend:" in backend_line
    assert "Started Streamlit with PID 1234 on 127.0.0.1:8501." in backend_line
    assert "[ error  ]" in warning_line
    assert "Hook:" in warning_line
    assert "Cloud sync failed." in warning_line
    assert "{'name'" not in backend_line


def test_generated_page_keeps_plain_event_line_category_parsing():
    namespace: dict[str, object] = {}
    exec(_source_for(), namespace)  # noqa: S102 - generated source is under test.
    extract_event_category = namespace["_extract_event_category"]

    assert (
        extract_event_category(
            "litlaunch_event level=info category=browser name=browser_launched"
        )
        == "browser"
    )
    assert extract_event_category("legacy category=backend name=started") == "backend"
    assert extract_event_category("{malformed") is None


def test_existing_file_requires_overwrite(tmp_path):
    output_path = tmp_path / "diagnostics.py"
    output_path.write_text("old content", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="overwrite=True"):
        create_diagnostics_page(output_path=output_path)

    assert output_path.read_text(encoding="utf-8") == "old content"


def test_overwrite_replaces_existing_file(tmp_path):
    output_path = tmp_path / "diagnostics.py"
    output_path.write_text("old content", encoding="utf-8")

    create_diagnostics_page(output_path=output_path, overwrite=True)

    assert "render_litlaunch_diagnostics" in output_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("function_name", ["not valid", "class", "1invalid", ""])
def test_invalid_function_name_is_rejected(tmp_path, function_name):
    with pytest.raises(ConfigurationError, match="function_name"):
        DiagnosticsPageBuilder(
            tmp_path / "diagnostics.py",
            function_name=function_name,
        )


def test_empty_page_title_is_rejected(tmp_path):
    with pytest.raises(ConfigurationError, match="page_title"):
        DiagnosticsPageBuilder(tmp_path / "diagnostics.py", page_title="  ")


def test_empty_output_path_is_rejected():
    with pytest.raises(ConfigurationError, match="output_path"):
        DiagnosticsPageOptions(output_path="")


def test_project_root_relative_output_path(tmp_path):
    project_root = tmp_path / "project"

    written = create_diagnostics_page(
        output_path="ui/litlaunch_diagnostics.py",
        project_root=project_root,
    )

    assert written == project_root / "ui" / "litlaunch_diagnostics.py"
    assert written.is_file()


def test_project_root_relative_escape_is_rejected(tmp_path):
    project_root = tmp_path / "project"

    with pytest.raises(ConfigurationError, match="project_root"):
        create_diagnostics_page(
            output_path="../outside.py",
            project_root=project_root,
        )


def test_output_path_directory_is_rejected(tmp_path):
    with pytest.raises(ConfigurationError, match="directory"):
        create_diagnostics_page(output_path=tmp_path, overwrite=True)


def test_generation_does_not_import_streamlit(tmp_path, monkeypatch):
    real_import = builtins.__import__

    def fail_on_streamlit(name, *args, **kwargs):
        if name == "streamlit":
            raise AssertionError("Streamlit should not be imported during generation.")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_on_streamlit)

    create_diagnostics_page(output_path=tmp_path / "diagnostics.py")


def test_generated_page_placeholder_is_not_corrupted_by_crafted_names():
    source = _source_for(
        app_name="My __PROFILE_NAME__ App",
        profile_name="real-profile",
    )

    # Single-pass substitution: the crafted app name (which contains another
    # placeholder token) is inserted verbatim and the real profile placeholder
    # still resolves, so the module stays valid Python.
    ast.parse(source)
    assert "My __PROFILE_NAME__ App" in source
    assert "real-profile" in source


def test_generated_diagnostics_page_executes_under_streamlit(tmp_path):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    page_path = tmp_path / "litlaunch_diagnostics.py"
    create_diagnostics_page(
        output_path=page_path,
        app_name="Studio <edge> & report",
        profile_name="studio-webapp",
    )
    driver = tmp_path / "driver.py"
    driver.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(tmp_path)!r})\n"
        "from litlaunch_diagnostics import render_litlaunch_diagnostics\n"
        "render_litlaunch_diagnostics()\n",
        encoding="utf-8",
    )

    # Absent event log: the page must render (not just AST-parse) with no
    # unhandled exception, exercising the real Streamlit widget/chart APIs.
    absent = AppTest.from_file(str(driver), default_timeout=60).run()
    assert not absent.exception

    # Malformed event log: a corrupt JSONL log must not crash the page.
    event_log = tmp_path / "runtime-events.log"
    event_log.write_text("not-json\n{broken\n", encoding="utf-8")
    malformed_page = tmp_path / "malformed_diag.py"
    create_diagnostics_page(
        output_path=malformed_page,
        app_name="Studio",
        profile_name="studio-webapp",
        event_log_path=event_log,
    )
    malformed_driver = tmp_path / "malformed_driver.py"
    malformed_driver.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(tmp_path)!r})\n"
        "from malformed_diag import render_litlaunch_diagnostics\n"
        "render_litlaunch_diagnostics()\n",
        encoding="utf-8",
    )
    malformed = AppTest.from_file(str(malformed_driver), default_timeout=60).run()
    assert not malformed.exception
