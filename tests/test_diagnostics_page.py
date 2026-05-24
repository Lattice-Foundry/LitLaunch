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
