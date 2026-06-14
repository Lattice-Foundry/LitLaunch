import ast
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib

REPO_ROOT = Path(__file__).parents[1]
VERSION_FILE = REPO_ROOT / "src" / "litlaunch" / "version.py"
DOCS_ROOT = REPO_ROOT / "docs"
PUBLIC_DOCS_ROOT = DOCS_ROOT / "Public"
GUIDES_ROOT = PUBLIC_DOCS_ROOT / "Guides"
REFERENCE_ROOT = PUBLIC_DOCS_ROOT / "Reference"
TROUBLESHOOTING_ROOT = PUBLIC_DOCS_ROOT / "Troubleshooting"


def current_version() -> str:
    module = ast.parse(VERSION_FILE.read_text(encoding="utf-8"))
    for node in module.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "__version__"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    raise AssertionError("Could not parse LitLaunch version.")


def test_pyproject_metadata_includes_console_and_typing_classifiers():
    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    classifiers = set(pyproject["project"]["classifiers"])
    assert "Development Status :: 5 - Production/Stable" in classifiers
    assert "Development Status :: 4 - Beta" not in classifiers
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
    assert "packaging>=24" in dev_dependencies
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
    assert urls["PyPI"] == "https://pypi.org/project/litlaunch/"


def test_changelog_exists_and_mentions_current_version():
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert f"## {current_version()} - Stable" in changelog
    assert "## Current Release Highlights" in changelog
    assert "## Beta Development Era" in changelog
    assert "## Alpha Development Era" in changelog
    assert "Granular pre-release history is preserved in git" in changelog
    assert not (REPO_ROOT / "RELEASE_NOTES.md").exists()
    for milestone in (
        "Managed Chromium browser-window lifecycle",
        "`ShutdownHookStatus`",
        "Runtime event sink API",
        "Generated Streamlit-native diagnostics/support page API",
        "Runtime governance layer",
        "Streamlit-native TLS detection",
        "Native shortcut generation",
        "Release hygiene tooling",
    ):
        assert milestone in changelog


def test_docs_foundation_exists_and_links_from_readme():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    docs = [
        "Public/Guides/overview.md",
        "Public/Guides/philosophy.md",
        "Public/Guides/installation.md",
        "Public/Guides/quickstart.md",
        "Public/Guides/integration/index.md",
        "Public/Guides/integration/rolethread.md",
        "Public/Guides/integration/packaging-notes.md",
        "Public/Reference/cli.md",
        "Public/Reference/browser-support.md",
        "Public/Reference/window-monitoring.md",
        "Public/Reference/inspect.md",
        "Public/Reference/diagnostics-page.md",
        "Public/Reference/runtime-events.md",
        "Public/Reference/security.md",
        "Public/Reference/architecture.md",
        "Public/Troubleshooting/troubleshooting.md",
    ]

    for doc in docs:
        path = DOCS_ROOT / doc
        assert path.is_file()
        assert path.read_text(encoding="utf-8").strip()
        assert f"docs/{doc}" in readme


def test_docs_follow_public_structure_standard():
    assert (DOCS_ROOT / "README.md").is_file()
    assert (DOCS_ROOT / "docs_structure_standard.md").is_file()
    assert (PUBLIC_DOCS_ROOT / "FAQ" / ".gitkeep").is_file()
    assert (PUBLIC_DOCS_ROOT / "Help" / ".gitkeep").is_file()

    loose_markdown = sorted(
        path.name
        for path in DOCS_ROOT.glob("*.md")
        if path.name not in {"README.md", "docs_structure_standard.md"}
    )
    assert loose_markdown == []
    assert not (DOCS_ROOT / "integration.md").exists()
    assert not (DOCS_ROOT / "integration").exists()


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
    quickstart = (GUIDES_ROOT / "quickstart.md").read_text(encoding="utf-8")
    architecture = (REFERENCE_ROOT / "architecture.md").read_text(encoding="utf-8")
    troubleshooting = (TROUBLESHOOTING_ROOT / "troubleshooting.md").read_text(
        encoding="utf-8"
    )
    cli = (REFERENCE_ROOT / "cli.md").read_text(encoding="utf-8")

    assert "source checkout" in readme
    assert "own Streamlit app path" in readme
    assert "Package Install" in (GUIDES_ROOT / "installation.md").read_text(
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
    assert "internal developer workflow" in cli
    assert "Some values are simulated" in cli
    assert "orange `Hook:` category" in quickstart
    assert "hook message text stays unstyled" in quickstart


def test_docs_document_current_cli_tools_workflows():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    quickstart = (GUIDES_ROOT / "quickstart.md").read_text(encoding="utf-8")
    cli = (REFERENCE_ROOT / "cli.md").read_text(encoding="utf-8")

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


def test_docs_clarify_public_api_surface_policy():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (REFERENCE_ROOT / "architecture.md").read_text(encoding="utf-8")

    assert "## Public API Surface" in readme
    assert "## Public API Surface" in architecture
    assert "`LauncherConfig`" in architecture
    assert (
        "`BackendCommandProvider`, `BackendCommand`, and `BackendCommandContext`"
        in architecture
    )
    assert "`HTMLDiagnosticsRenderer`" in architecture
    assert "Window provider internals" in readme
    assert "not a packager" in architecture
    assert (
        "Packaging automation remains outside LitLaunch's runtime API" in architecture
    )
    assert "outside LitLaunch's runtime API" in architecture


def test_docs_clarify_redaction_limits_and_deferred_visual_placeholders():
    inspect_doc = (REFERENCE_ROOT / "inspect.md").read_text(encoding="utf-8")
    troubleshooting = (TROUBLESHOOTING_ROOT / "troubleshooting.md").read_text(
        encoding="utf-8"
    )

    assert "pattern-based" in inspect_doc
    assert "Encoded, base64, URL-wrapped" in inspect_doc
    assert "Review support bundles before sharing" in inspect_doc
    assert "home/user path prefixes" in troubleshooting
    screenshot_placeholder = "[screenshot" + " needed]"
    diagram_placeholder = "[diagram" + " needed]"
    public_doc_text = "\n".join(
        path.read_text(encoding="utf-8") for path in PUBLIC_DOCS_ROOT.rglob("*.md")
    )
    assert screenshot_placeholder not in public_doc_text
    assert diagram_placeholder not in public_doc_text


def test_docs_clarify_with_port_title_and_streamlit_passthrough_policy():
    quickstart = (GUIDES_ROOT / "quickstart.md").read_text(encoding="utf-8")
    architecture = (REFERENCE_ROOT / "architecture.md").read_text(encoding="utf-8")
    cli = (REFERENCE_ROOT / "cli.md").read_text(encoding="utf-8")
    rolethread = (GUIDES_ROOT / "integration" / "rolethread.md").read_text(
        encoding="utf-8"
    )

    assert "`launcher.with_port(port)`" in quickstart
    assert "preserves injected managers" in quickstart
    assert "`with_port(port)` returns a new launcher" in architecture
    assert "`LauncherConfig.title`" in quickstart
    assert "window detection" in rolethread
    assert "does not deduplicate duplicate user options" in quickstart
    assert "does not deduplicate repeated user-supplied" in cli


def test_internal_docs_are_not_tracked_in_public_source_tree():
    assert not (DOCS_ROOT / "internal").exists()

    public_paths = [REPO_ROOT / "README.md"]
    public_paths.extend(PUBLIC_DOCS_ROOT.rglob("*.md"))

    for path in public_paths:
        assert "docs/internal" not in path.read_text(encoding="utf-8")
