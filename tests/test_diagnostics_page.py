import ast
import builtins

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
        "_item_status",
        "_compact_metric_value",
        "_status_class",
    }.issubset(functions)


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
    )

    assert "PROJECT_ROOT = 'X:" in source
    assert "apps" in source
    assert "example" in source
    assert "INCLUDE_EVENTS = True" in source
    assert "EVENT_LOG_PATH = '.litlaunch" in source
    assert "runtime.log" in source
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
    assert "chart_bg" in source


@pytest.mark.parametrize("theme", ["auto", "light", "dark"])
def test_generated_page_accepts_theme_modes(theme):
    source = _source_for(theme=theme)

    assert f"THEME = '{theme}'" in source
    assert "var(--primary-color" in source


def test_generated_page_rejects_unknown_theme(tmp_path):
    with pytest.raises(ConfigurationError, match="theme"):
        DiagnosticsPageBuilder(tmp_path / "diagnostics.py", theme="neon")


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
