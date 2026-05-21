from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib

REPO_ROOT = Path(__file__).parents[1]


def test_pyproject_metadata_includes_console_and_typing_classifiers():
    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    classifiers = set(pyproject["project"]["classifiers"])
    assert "Development Status :: 4 - Beta" in classifiers
    assert "Development Status :: 3 - Alpha" not in classifiers
    assert "Development Status :: 2 - Pre-Alpha" not in classifiers
    assert "Environment :: Console" in classifiers
    assert "Topic :: Utilities" in classifiers
    assert "Typing :: Typed" in classifiers
    assert pyproject["project"]["requires-python"] == ">=3.10"


def test_pyproject_dev_extras_include_release_tools():
    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    dev_dependencies = set(pyproject["project"]["optional-dependencies"]["dev"])
    assert "build>=1.2" in dev_dependencies
    assert "tomli>=2; python_version < '3.11'" in dev_dependencies
    assert "twine>=6" in dev_dependencies


def test_pyproject_runtime_dependencies_are_profile_toml_only():
    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert pyproject["project"]["dependencies"] == ["tomli>=2; python_version < '3.11'"]


def test_pyproject_urls_use_canonical_repository_location():
    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    urls = pyproject["project"]["urls"]
    assert urls["Homepage"] == "https://github.com/Lattice-Foundry/LitLaunch"
    assert urls["Repository"] == "https://github.com/Lattice-Foundry/LitLaunch"
    assert urls["Issues"] == "https://github.com/Lattice-Foundry/LitLaunch/issues"


def test_changelog_exists_and_mentions_current_version():
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert "## 0.91.23b1" in changelog
    assert "## 0.91.0b0" in changelog
    assert "## 0.85.0" in changelog
    assert "## 0.23.0" in changelog
    assert "## 0.22.0" in changelog
    assert "## 0.21.0" in changelog
    assert "## 0.20.0" in changelog
    assert "## 0.19.0" in changelog
    assert "## 0.16.1" in changelog
    assert "## 0.16.0" in changelog
    assert "## 0.15.0" in changelog
    assert "## 0.14.0" in changelog
    assert "## 0.13.2" in changelog
    assert "## 0.13.1" in changelog
    assert "## 0.13.0" in changelog
    assert "## 0.12.0" in changelog
    assert "## 0.11.0" in changelog
    assert "## 0.10.0" in changelog
    assert "## 0.9.1" in changelog
    assert "## 0.9.0" in changelog
    assert "## 0.8.4" in changelog
    assert "## 0.8.3" in changelog
    assert "## 0.8.2" in changelog
    assert "## 0.8.1" in changelog
    assert "## 0.8.0" in changelog


def test_docs_foundation_exists_and_links_from_readme():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    docs = [
        "overview.md",
        "philosophy.md",
        "installation.md",
        "quickstart.md",
        "cli.md",
        "browser_support.md",
        "window_monitoring.md",
        "inspect.md",
        "troubleshooting.md",
        "architecture.md",
        "integration/rolethread.md",
        "integration/packaging_notes.md",
    ]

    for doc in docs:
        path = REPO_ROOT / "docs" / doc
        assert path.is_file()
        assert path.read_text(encoding="utf-8").strip()
        assert f"docs/{doc}" in readme


def test_internal_docs_are_excluded_from_sdist_config():
    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    exclude = pyproject["tool"]["hatch"]["build"]["targets"]["sdist"]["exclude"]
    assert "/docs/internal" in exclude


def test_dead_diagnostics_module_has_been_removed():
    assert not (REPO_ROOT / "src" / "litlaunch" / "diagnostics.py").exists()


def test_docs_clarify_examples_run_start_and_shutdown_timeout_policy():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    quickstart = (REPO_ROOT / "docs" / "quickstart.md").read_text(encoding="utf-8")
    architecture = (REPO_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    troubleshooting = (REPO_ROOT / "docs" / "troubleshooting.md").read_text(
        encoding="utf-8"
    )
    cli = (REPO_ROOT / "docs" / "cli.md").read_text(encoding="utf-8")

    assert "source checkout" in readme
    assert "own Streamlit app path" in readme
    assert "beta stabilization" in (REPO_ROOT / "docs" / "installation.md").read_text(
        encoding="utf-8"
    )
    assert "source-tree fixture" in quickstart
    assert "`StreamlitLauncher.run()` is the friendly" in architecture
    assert "waits return `None`" in architecture
    assert "graceful_timeout_seconds" in troubleshooting
    assert "set_shutdown_completion_callback" in quickstart
    assert "after the endpoint response is sent" in quickstart
    assert "essential errors and failure guidance" in cli
    assert "litlaunch console-preview --all" in cli
    assert "litlaunch console-preview --normal" in cli
    assert "litlaunch console-preview --verbose" in cli
    assert "litlaunch help launch" in cli
    assert "litlaunch help diagnostics" in cli
    assert "litlaunch --help" in cli
    assert "not a stable public workflow" in cli
    assert "Some values are simulated" in cli
    assert "orange `Hook:` category" in quickstart
    assert "hook message text stays unstyled" in quickstart


def test_docs_document_current_cli_tools_workflows():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    quickstart = (REPO_ROOT / "docs" / "quickstart.md").read_text(encoding="utf-8")
    cli = (REPO_ROOT / "docs" / "cli.md").read_text(encoding="utf-8")

    for text in (readme, quickstart, cli):
        assert "litlaunch create profile" in text
        assert "litlaunch create shortcut --profile" in text
        assert "litlaunch report" in text
        assert "litlaunch --profile" in text
        assert "plain text inspect" not in text.lower()
        assert "console-preview-norm" not in text
        assert "console-preview-verb" not in text

    assert "litlaunch create shortcut --profile <profile>" in cli
    assert "can optionally create" in readme
    assert "can optionally create" in quickstart


def test_docs_clarify_beta_api_stability_policy():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (REPO_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")

    assert "## Beta API Stability" in readme
    assert "## Beta API Stability" in architecture
    assert "`LauncherConfig`" in architecture
    assert (
        "`BackendCommandProvider`, `BackendCommand`, and `BackendCommandContext`"
        in architecture
    )
    assert "`HTMLDiagnosticsRenderer`" in architecture
    assert "1.0.0-rc1" in architecture
    assert "Window provider internals" in readme
    assert "not a packager" in architecture
    assert "packaging automation is not" in architecture
    assert "part of the beta runtime API" in architecture


def test_docs_clarify_redaction_limits_and_deferred_visual_placeholders():
    inspect_doc = (REPO_ROOT / "docs" / "inspect.md").read_text(encoding="utf-8")
    troubleshooting = (REPO_ROOT / "docs" / "troubleshooting.md").read_text(
        encoding="utf-8"
    )
    beta_issues = (REPO_ROOT / "docs" / "internal" / "known_beta_issues.md").read_text(
        encoding="utf-8"
    )

    assert "pattern-based" in inspect_doc
    assert "Encoded, base64, URL-wrapped" in inspect_doc
    assert "Review support bundles before sharing" in inspect_doc
    assert "home/user path prefixes" in troubleshooting
    assert "Screenshot And Diagram Placeholders" in beta_issues
    assert "deferred until release stabilization" in beta_issues


def test_docs_clarify_with_port_title_and_streamlit_passthrough_policy():
    quickstart = (REPO_ROOT / "docs" / "quickstart.md").read_text(encoding="utf-8")
    architecture = (REPO_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    cli = (REPO_ROOT / "docs" / "cli.md").read_text(encoding="utf-8")
    rolethread = (REPO_ROOT / "docs" / "integration" / "rolethread.md").read_text(
        encoding="utf-8"
    )

    assert "`launcher.with_port(port)`" in quickstart
    assert "preserves injected managers" in quickstart
    assert "`with_port(port)` returns a new launcher" in architecture
    assert "`LauncherConfig.title`" in quickstart
    assert "window detection" in rolethread
    assert "does not deduplicate duplicate user options" in quickstart
    assert "does not deduplicate repeated user-supplied" in cli


def test_internal_docs_exist_but_are_not_linked_from_public_docs():
    internal_docs = [
        "README.md",
        "rolethread_integration_plan.md",
        "rolethread_handoff_checklist.md",
        "rolethread_runtime_mapping.md",
        "rolethread_test_matrix.md",
        "known_beta_issues.md",
    ]

    for doc in internal_docs:
        path = REPO_ROOT / "docs" / "internal" / doc
        text = path.read_text(encoding="utf-8")
        assert path.is_file()
        assert "INTERNAL / TEMPORARY INTEGRATION DOCUMENTATION" in text
        assert text.strip()

    public_paths = [REPO_ROOT / "README.md"]
    public_paths.extend((REPO_ROOT / "docs").glob("*.md"))
    public_paths.extend((REPO_ROOT / "docs" / "integration").glob("*.md"))

    for path in public_paths:
        assert "docs/internal" not in path.read_text(encoding="utf-8")
