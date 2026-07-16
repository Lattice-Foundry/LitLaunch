from __future__ import annotations

import json
import re
from pathlib import Path

from litlaunch.artifacts import browser_profiles_dir, runtime_state_root_for_config
from litlaunch.browsers import BrowserCapability, BrowserKind, BrowserResolution
from litlaunch.config import BrowserChoice
from litlaunch.inspect import (
    DiagnosticCollector,
    DiagnosticItem,
    DiagnosticSection,
    DiagnosticsReport,
    DiagnosticStatus,
    HTMLDiagnosticsRenderer,
    JSONDiagnosticsRenderer,
    SanitizedBundleRenderer,
    StreamlitAvailability,
    current_utc_timestamp,
    redact_sensitive_args,
    redact_sensitive_text,
)
from litlaunch.lifecycle import LaunchPlan
from litlaunch.platforms import Architecture, OperatingSystem, PlatformInfo
from litlaunch.redaction import format_command_preview, format_env_preview
from litlaunch.version import __version__
from litlaunch.windowing import WindowMonitorConfig

EXAMPLE_APP = Path("examples/minimal_app/app.py")
MISSING_APP = Path("missing-inspect-app.py")


def fake_platform_info() -> PlatformInfo:
    return PlatformInfo(
        os=OperatingSystem.WINDOWS,
        architecture=Architecture.X64,
        python_version="3.14.5",
        python_executable="X:/Python/python.exe",
        machine="AMD64",
        system="Windows",
        release="11",
        is_windows=True,
        is_macos=False,
        is_linux=False,
        supports_chromium_app_mode=True,
        supports_window_monitoring=True,
        supports_default_browser_open=True,
        notes=("Window monitoring capability is currently Windows-first.",),
    )


class FakePlatformDetector:
    def detect(self):
        return fake_platform_info()


class FakeBrowserRegistry:
    def __init__(self, *, selected=True):
        self.selected = selected
        self.detect_calls = []
        self.resolve_calls = []

    def detect_all(self, platform_info=None):
        self.detect_calls.append(platform_info)
        return (
            BrowserCapability(
                kind=BrowserKind.EDGE,
                name="Edge",
                executable_path="C:/Edge/msedge.exe",
                available=True,
                supports_app_mode=True,
                supports_full_browser=True,
            ),
            BrowserCapability(
                kind=BrowserKind.CHROME,
                name="Chrome",
                executable_path=None,
                available=False,
                supports_app_mode=True,
                supports_full_browser=True,
                notes=("Chrome not found.",),
            ),
        )

    def resolve(
        self,
        choice,
        platform_info=None,
        *,
        prefer_app_mode=False,
        allow_fallback=True,
    ):
        self.resolve_calls.append(
            (choice, platform_info, prefer_app_mode, allow_fallback)
        )
        selected = None
        if self.selected:
            selected = BrowserCapability(
                kind=BrowserKind.EDGE,
                name="Edge",
                executable_path="C:/Edge/msedge.exe",
                available=True,
                supports_app_mode=True,
                supports_full_browser=True,
            )
        return BrowserResolution(
            requested=BrowserChoice.AUTO,
            selected=selected,
            fallback_chain=(),
            message="Selected Edge." if selected else "No browser available.",
        )


class FakeCommandBuilder:
    def __init__(self, config):
        self.config = config

    def build(self, *, port=None):
        command = (
            "python",
            "-m",
            "streamlit",
            "run",
            str(self.config.app_path),
            "--server.port",
            str(port or 8501),
            *self.config.streamlit_args,
        )
        if self.config.app_args:
            return (*command, "--", *self.config.app_args)
        return command


class FakeLauncher:
    instances = []

    def __init__(self, config):
        self.config = config
        self.command_builder = FakeCommandBuilder(config)
        self.run_calls = 0
        FakeLauncher.instances.append(self)

    def resolve_port(self):
        return self.config.port or 8501

    def resolve_browser(self, *, prefer_app_mode=None):
        return BrowserResolution(
            requested=self.config.browser,
            selected=BrowserCapability(
                kind=BrowserKind.EDGE,
                name="Edge",
                executable_path="C:/Edge/msedge.exe",
                available=True,
                supports_app_mode=True,
                supports_full_browser=True,
            ),
            fallback_chain=(),
            message="Selected Edge.",
        )

    def build_launch_plan(self):
        resolved_port = self.resolve_port()
        command = self.command_builder.build(port=resolved_port)
        runtime_state_root = runtime_state_root_for_config(self.config)
        return LaunchPlan(
            command=command,
            command_display=format_command_preview(command),
            backend_description="Streamlit backend",
            backend_kind="streamlit",
            cwd=self.config.cwd,
            app_url=f"http://{self.config.host}:{resolved_port}",
            health_url=f"http://{self.config.host}:{resolved_port}/_stcore/health",
            host=self.config.host,
            port=self.config.port,
            port_range=self.config.port_range,
            resolved_port=resolved_port,
            auto_port=self.config.auto_port,
            port_selection="requested/default port available",
            mode=self.config.mode,
            headless=False,
            browser_requested=self.config.browser,
            browser_resolution=self.resolve_browser(
                prefer_app_mode=self.config.mode.value == "webapp"
            ),
            allow_browser_fallback=self.config.allow_browser_fallback,
            app_args=self.config.app_args,
            streamlit_flags=self.config.streamlit_flags,
            streamlit_args=self.config.streamlit_args,
            extra_env_preview=(
                format_env_preview(self.config.extra_env)
                if self.config.extra_env
                else "none"
            ),
            streamlit_chrome_policy=(
                "visible" if self.config.show_streamlit_chrome else "hidden"
            ),
            streamlit_output_policy=(
                "visible" if self.config.show_streamlit_output else "hidden"
            ),
            app_icon=self.config.app_icon,
            app_icon_support="native shortcuts can use this icon",
            runtime_state_root=runtime_state_root,
            browser_profile_root=browser_profiles_dir(runtime_state_root),
            browser_profile_policy="ephemeral isolated browser profile",
            browser_profile_cleanup="best-effort cleanup after runtime stops",
        )

    def run(self):
        self.run_calls += 1
        raise AssertionError("inspect must not start the backend")


def streamlit_available():
    return StreamlitAvailability(
        available=True,
        version="1.50.0",
        message="Streamlit 1.50.0 detected.",
    )


def streamlit_missing():
    return StreamlitAvailability(
        available=False,
        version=None,
        message="Streamlit is not installed.",
    )


def make_collector(*, streamlit_checker=streamlit_available, browser_selected=True):
    return DiagnosticCollector(
        platform_detector=FakePlatformDetector(),
        browser_registry=FakeBrowserRegistry(selected=browser_selected),
        streamlit_checker=streamlit_checker,
        launcher_factory=FakeLauncher,
    )


def report_item_messages(report):
    return {
        (section.title, item.name): item.message
        for section in report.sections
        for item in section.items
    }


def test_diagnostic_status_values():
    assert DiagnosticStatus.OK.value == "ok"
    assert DiagnosticStatus.WARNING.value == "warning"
    assert DiagnosticStatus.ERROR.value == "error"
    assert DiagnosticStatus.INFO.value == "info"


def test_inspect_reports_credential_free_experimental_host_sizing_state():
    report = make_collector().collect(
        EXAMPLE_APP,
        mode="webapp",
        browser="edge",
        host_sizing="initial",
    )
    messages = report_item_messages(report)
    rendered = JSONDiagnosticsRenderer().render(report)

    assert messages[("Target", "Host sizing policy")] == "initial (Experimental)"
    assert messages[("Target", "Host sizing eligibility")] == "eligible"
    assert "capability_token" not in rendered
    assert "host-sizing/report" not in rendered


def test_inspect_reports_continuous_host_sizing_policy():
    report = make_collector().collect(
        EXAMPLE_APP,
        mode="webapp",
        browser="edge",
        host_sizing="continuous",
    )
    messages = report_item_messages(report)

    assert messages[("Target", "Host sizing policy")] == ("continuous (Experimental)")
    assert messages[("Target", "Host sizing eligibility")] == "eligible"


def test_diagnostics_report_counts_and_ok_behavior():
    report = DiagnosticsReport(
        "Report",
        (
            DiagnosticSection(
                "Section",
                (
                    DiagnosticItem("a", DiagnosticStatus.OK, "ok"),
                    DiagnosticItem("b", DiagnosticStatus.WARNING, "warn"),
                    DiagnosticItem("c", DiagnosticStatus.ERROR, "error"),
                ),
            ),
        ),
    )

    assert report.ok is False
    assert report.warnings == 1
    assert report.errors == 1


def test_diagnostic_item_to_dict_shape_and_redaction():
    item = DiagnosticItem(
        "API key",
        DiagnosticStatus.INFO,
        "token: abc123secret",
        detail="password hunter2",
    )

    data = item.to_dict()

    assert data == {
        "name": "API key",
        "status": "info",
        "message": "token: <redacted>",
        "detail": "password <redacted>",
    }


def test_diagnostic_section_to_dict_shape():
    section = DiagnosticSection(
        "Section",
        (DiagnosticItem("Name", DiagnosticStatus.OK, "message"),),
    )

    assert section.to_dict() == {
        "title": "Section",
        "items": [
            {"name": "Name", "status": "ok", "message": "message", "detail": None}
        ],
    }


def test_diagnostics_report_to_dict_shape():
    report = DiagnosticsReport(
        "Report",
        (
            DiagnosticSection(
                "Section",
                (DiagnosticItem("Name", DiagnosticStatus.WARNING, "message"),),
            ),
        ),
        generated_at_utc="2026-05-18T12:00:00Z",
    )

    data = report.to_dict()

    assert data["schema_version"] == 1
    assert data["generated_by"] == "litlaunch"
    assert data["litlaunch_version"] == __version__
    assert data["generated_at_utc"] == "2026-05-18T12:00:00Z"
    assert data["title"] == "Report"
    assert data["ok"] is True
    assert data["warnings"] == 1
    assert data["errors"] == 0
    assert data["sections"] == [
        {
            "title": "Section",
            "items": [
                {
                    "name": "Name",
                    "status": "warning",
                    "message": "message",
                    "detail": None,
                }
            ],
        }
    ]


def test_diagnostics_report_generates_utc_metadata_shape():
    timestamp = current_utc_timestamp()
    report = DiagnosticsReport("Report")

    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", timestamp)
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
        report.generated_at_utc,
    )
    assert report.to_dict()["generated_at_utc"] == report.generated_at_utc


def test_report_without_errors_is_ok_with_warnings_allowed():
    report = DiagnosticsReport(
        "Report",
        (
            DiagnosticSection(
                "Section",
                (DiagnosticItem("warning", DiagnosticStatus.WARNING, "warn"),),
            ),
        ),
    )

    assert report.ok is True
    assert report.warnings == 1
    assert report.errors == 0


def test_collector_without_app_path_reports_environment_only():
    report = make_collector().collect()

    assert report.ok is True
    assert [section.title for section in report.sections] == [
        "LitLaunch",
        "Platform",
        "Streamlit",
        "Browsers",
        "Runtime Governance",
        "Runtime Exposure",
        "Transport Security",
    ]
    assert "LitLaunch" in report.sections[0].items[0].message
    assert report.errors == 0


def test_collector_with_valid_app_path_builds_previews():
    FakeLauncher.instances = []

    report = make_collector().collect(app_path=EXAMPLE_APP, port=8600)
    messages = report_item_messages(report)

    assert report.ok is True
    assert "Target" in [section.title for section in report.sections]
    assert ("Target", "Command preview") in messages
    assert messages[("Target", "Requested port")] == "8600"
    assert messages[("Target", "Selected port")] == "8600"
    assert messages[("Target", "Auto-port")] == "enabled"
    assert messages[("Target", "Port range")] == "default"
    assert messages[("Target", "Streamlit chrome policy")] == "hidden"
    assert messages[("Target", "Streamlit console output policy")] == "hidden"
    assert messages[("Target", "Trust mode")] == "development"
    assert messages[("Target", "App URL preview")] == "http://127.0.0.1:8600"
    assert (
        messages[("Target", "Health URL preview")]
        == "http://127.0.0.1:8600/_stcore/health"
    )
    assert FakeLauncher.instances
    assert FakeLauncher.instances[0].run_calls == 0


def test_collector_reports_visible_streamlit_chrome_policy():
    report = make_collector().collect(
        app_path=EXAMPLE_APP,
        show_streamlit_chrome=True,
    )
    messages = report_item_messages(report)

    assert messages[("Target", "Streamlit chrome policy")] == "visible"


def test_collector_reports_visible_streamlit_output_policy():
    report = make_collector().collect(
        app_path=EXAMPLE_APP,
        show_streamlit_output=True,
    )
    messages = report_item_messages(report)

    assert messages[("Target", "Streamlit console output policy")] == "visible"


def test_collector_reports_app_icon_metadata(tmp_path):
    icon = tmp_path / "app.ico"
    icon.write_bytes(b"icon")

    report = make_collector().collect(app_path=EXAMPLE_APP, app_icon=icon)
    messages = report_item_messages(report)

    assert messages[("Target", "App icon")] == str(icon)


def test_collector_reports_runtime_state_paths(tmp_path):
    state_root = tmp_path / "runtime-state"

    report = make_collector().collect(
        app_path=EXAMPLE_APP,
        runtime_state_root=state_root,
    )
    messages = report_item_messages(report)

    assert messages[("Target", "Runtime state root")] == str(state_root)
    assert messages[("Target", "Browser profile root")] == str(
        state_root / "browser-profiles"
    )
    assert (
        messages[("Target", "Browser profile policy")]
        == "ephemeral isolated browser profile"
    )


def test_collector_reports_port_range():
    report = make_collector().collect(
        app_path=EXAMPLE_APP,
        port=8501,
        port_range=(8501, 8599),
    )
    messages = report_item_messages(report)

    assert messages[("Target", "Requested port")] == "8501"
    assert messages[("Target", "Selected port")] == "8501"
    assert messages[("Target", "Port range")] == "8501-8599"


def test_collector_reports_configured_trust_mode():
    report = make_collector().collect(
        app_path=EXAMPLE_APP,
        port=8600,
        trust_mode="internal_network",
    )
    messages = report_item_messages(report)

    assert messages[("Target", "Trust mode")] == "internal_network"


def test_posture_diagnostics_render_to_json_html_and_bundle():
    report = make_collector().collect(
        app_path=EXAMPLE_APP,
        host="0.0.0.0",
        trust_mode="internal_network",
        allow_network_exposure=True,
    )
    outputs = (
        JSONDiagnosticsRenderer().render(report),
        HTMLDiagnosticsRenderer().render(report),
        SanitizedBundleRenderer().render(report),
    )

    for output in outputs:
        assert "Runtime Governance" in output
        assert "Runtime Exposure" in output
        assert "Transport Security" in output
        assert "wildcard_bind" in output
        assert "internal_network" in output
        assert "LitLaunch does not secure Streamlit" in output


def test_governance_summary_reports_allowed_with_warnings():
    report = make_collector().collect(
        app_path=EXAMPLE_APP,
        host="0.0.0.0",
        trust_mode="internal_network",
        allow_network_exposure=True,
    )
    messages = report_item_messages(report)

    assert messages[("Runtime Governance", "Launch posture")] == (
        "allowed with warnings"
    )
    assert messages[("Runtime Governance", "Trust mode")] == "internal_network"
    assert (
        messages[("Runtime Governance", "Top recommendation")]
        == "Use internal_network only when the app is intentionally exposed."
    )


def test_governance_summary_reports_blocked_posture():
    report = make_collector().collect(
        app_path=EXAMPLE_APP,
        host="0.0.0.0",
        trust_mode="strict_local",
        allow_network_exposure=True,
    )
    messages = report_item_messages(report)

    assert messages[("Runtime Governance", "Launch posture")] == "blocked"
    assert "loopback" in messages[("Runtime Governance", "Top recommendation")]


def test_transport_diagnostics_render_to_json_html_and_bundle():
    report = make_collector().collect(
        app_path=EXAMPLE_APP,
        host="0.0.0.0",
        trust_mode="internal_network",
        allow_network_exposure=True,
        streamlit_flags={
            "server.sslCertFile": "C:/private/internal.pem",
            "server.sslKeyFile": "C:/private/internal-key.pem",
        },
    )
    outputs = (
        JSONDiagnosticsRenderer().render(report),
        HTMLDiagnosticsRenderer().render(report),
        SanitizedBundleRenderer().render(report),
    )

    for output in outputs:
        assert "Transport Security" in output
        assert "configured" in output
        assert "Streamlit TLS settings detected" in output
        assert "C:/private/internal.pem" not in output


def test_collector_with_profile_metadata_adds_profile_section():
    report = make_collector().collect(
        app_path=EXAMPLE_APP,
        profile_name="webapp",
        monitor_window=True,
        graceful_timeout_seconds=15,
        window_monitor_config=WindowMonitorConfig(
            appear_timeout_seconds=90,
            poll_interval_seconds=0.5,
            stable_poll_count=3,
        ),
    )
    messages = report_item_messages(report)

    assert "Profile" in [section.title for section in report.sections]
    assert messages[("Profile", "Profile")] == "webapp"
    assert messages[("Profile", "Window monitoring")] == "enabled"
    assert messages[("Profile", "Graceful timeout")] == "15 seconds"
    assert messages[("Profile", "Monitor appear timeout")] == "90 seconds"
    assert messages[("Profile", "Monitor poll interval")] == "0.5 seconds"
    assert messages[("Profile", "Monitor stable polls")] == "3"


def test_collector_target_section_redacts_sensitive_extra_env():
    report = make_collector().collect(
        app_path=EXAMPLE_APP,
        cwd="workspace",
        extra_env={"APP_TOKEN": "super-secret-token", "APP_MODE": "demo"},
    )
    rendered = JSONDiagnosticsRenderer().render(report)

    assert "Working directory" in rendered
    assert "workspace" in rendered
    assert "Environment overrides" in rendered
    assert "APP_MODE=demo" in rendered
    assert "APP_TOKEN=<redacted>" in rendered
    assert "super-secret-token" not in rendered


def test_collector_with_missing_app_path_reports_error():
    report = make_collector().collect(app_path=MISSING_APP)
    rendered = JSONDiagnosticsRenderer().render(report)

    assert report.ok is False
    assert report.errors == 2
    assert "does not exist" in rendered
    assert "is not a file" in rendered


def test_collector_reports_streamlit_missing_with_fake_checker():
    report = make_collector(streamlit_checker=streamlit_missing).collect()
    rendered = JSONDiagnosticsRenderer().render(report)

    assert report.ok is False
    assert "Streamlit is not installed." in rendered


def test_collector_reports_browser_capabilities_with_fake_registry():
    report = make_collector(browser_selected=False).collect()
    messages = report_item_messages(report)

    assert report.ok is True
    assert report.warnings >= 1
    assert messages[("Browsers", "Edge")] == "available, app-mode, full-browser"
    assert messages[("Browsers", "Chrome")] == "unavailable, app-mode, full-browser"
    assert messages[("Browsers", "Browser resolution")] == "No browser available."


def test_json_renderer_outputs_parseable_sanitized_json():
    report = DiagnosticsReport(
        "LitLaunch Inspect",
        (
            DiagnosticSection(
                "Target",
                (
                    DiagnosticItem(
                        "Command preview",
                        DiagnosticStatus.OK,
                        "token=abc123secret",
                        detail="--api_key=value",
                    ),
                ),
            ),
        ),
    )

    rendered = JSONDiagnosticsRenderer().render(report)
    data = json.loads(rendered)

    assert data["title"] == "LitLaunch Inspect"
    assert data["schema_version"] == 1
    assert data["generated_by"] == "litlaunch"
    assert data["litlaunch_version"] == __version__
    assert "generated_at_utc" in data
    assert data["sections"][0]["items"][0]["message"] == "token=<redacted>"
    assert data["sections"][0]["items"][0]["detail"] == "--api_key=<redacted>"
    assert "\033[" not in rendered
    assert "abc123secret" not in rendered
    assert "value" not in rendered


def test_html_renderer_outputs_sanitized_standalone_html():
    report = DiagnosticsReport(
        "LitLaunch Inspect",
        (
            DiagnosticSection(
                "Profile",
                (
                    DiagnosticItem(
                        "Profile",
                        DiagnosticStatus.INFO,
                        "rolethread-webapp",
                    ),
                ),
            ),
            DiagnosticSection(
                "Target",
                (
                    DiagnosticItem(
                        "Command preview",
                        DiagnosticStatus.OK,
                        "token=abc123secret",
                        detail='--api_key=value --name "<demo>"',
                    ),
                    DiagnosticItem(
                        "Python executable",
                        DiagnosticStatus.WARNING,
                        r"X:\very\long\path\with\many\segments\app.py",
                    ),
                ),
            ),
        ),
        generated_at_utc="2026-05-18T12:00:00Z",
    )

    rendered = HTMLDiagnosticsRenderer().render(report)

    assert rendered.startswith("<!doctype html>")
    assert "<html" in rendered
    assert "<script" not in rendered.lower()
    assert "https://" not in rendered
    assert "LitLaunch Inspect" in rendered
    assert __version__ in rendered
    assert "This report is sanitized" in rendered
    assert "raw environment variables" in rendered
    assert "Pattern-based redaction" in rendered
    assert "abc123secret" not in rendered
    assert "--api_key=value" not in rendered
    assert 'class="summary"' in rendered
    assert 'class="note-card"' in rendered
    assert 'class="table-wrap"' in rendered
    assert 'class="status status-ok"' in rendered
    assert 'class="status status-warning"' in rendered
    assert ">WARNING<" in rendered
    assert "--warning: #8a7700" in rendered
    assert "--warning: #f9f1a5" in rendered
    assert "<code></code>" not in rendered
    assert (
        '<span class="empty-detail" aria-label="No detail">&mdash;</span>' in rendered
    )
    assert '<span class="summary-label">Profile</span>' in rendered
    assert '<span class="summary-value">rolethread-webapp</span>' in rendered
    assert '<code class="value-code">X:\\very\\long\\path' in rendered
    assert "overflow-wrap: anywhere" in rendered
    assert "&lt;redacted&gt;" in rendered
    assert "&lt;demo&gt;" in rendered
    assert "\033[" not in rendered


def test_html_renderer_omits_top_profile_summary_without_profile_section():
    report = DiagnosticsReport(
        "LitLaunch Inspect",
        (
            DiagnosticSection(
                "Target",
                (
                    DiagnosticItem(
                        "Working directory",
                        DiagnosticStatus.INFO,
                        "not set",
                    ),
                ),
            ),
        ),
        generated_at_utc="2026-05-18T12:00:00Z",
    )

    rendered = HTMLDiagnosticsRenderer().render(report)

    assert '<span class="summary-label">Profile</span>' not in rendered
    assert "<td>not set</td>" in rendered


def test_html_renderer_can_omit_details():
    report = DiagnosticsReport(
        "Report",
        (
            DiagnosticSection(
                "Section",
                (
                    DiagnosticItem(
                        "Name",
                        DiagnosticStatus.INFO,
                        "message",
                        "hidden-detail",
                    ),
                ),
            ),
        ),
    )

    rendered = HTMLDiagnosticsRenderer(include_details=False).render(report)

    assert "Name" in rendered
    assert "message" in rendered
    assert "hidden-detail" not in rendered


def test_bundle_renderer_includes_summary_sections_and_sanitization_note():
    report = DiagnosticsReport(
        "LitLaunch Inspect",
        (
            DiagnosticSection(
                "Platform",
                (
                    DiagnosticItem(
                        "Platform",
                        DiagnosticStatus.OK,
                        "Windows x64 / Python 3.14.5",
                    ),
                ),
            ),
        ),
    )

    rendered = SanitizedBundleRenderer().render(report)

    assert "LitLaunch Support Bundle" in rendered
    assert f"Version: {__version__}" in rendered
    assert "Generated at:" in rendered
    assert "Summary: ok; 0 errors; 0 warnings" in rendered
    assert "This report is sanitized" in rendered
    assert "Platform" in rendered
    assert "[OK] Platform: Windows x64 / Python 3.14.5" in rendered
    assert "\033[" not in rendered


def test_redact_sensitive_args():
    redacted = redact_sensitive_args(
        (
            "--server.cookieSecret",
            "super-secret",
            "--api_key=value",
            "--passwd",
            "abc123password",
            "--regular-keyboard-option",
            "plain",
            "--theme.base=dark",
        )
    )

    assert "super-secret" not in redacted
    assert "abc123password" not in redacted
    assert "--server.cookieSecret" in redacted
    assert "<redacted>" in redacted
    assert "--api_key=<redacted>" in redacted
    assert "--passwd" in redacted
    assert "--regular-keyboard-option" in redacted
    assert "plain" in redacted
    assert "--theme.base=dark" in redacted


def test_redact_sensitive_text_patterns():
    text = (
        "token abc123secret secret=hidden password: hunter2 "
        "passwd abc123 api_key=value key abcd1234"
    )

    redacted = redact_sensitive_text(text)

    assert "abc123secret" not in redacted
    assert "hidden" not in redacted
    assert "hunter2" not in redacted
    assert "value" not in redacted
    assert "abcd1234" not in redacted
    assert redacted.count("<redacted>") == 6


def test_redact_sensitive_text_hides_common_home_path_prefixes(monkeypatch):
    monkeypatch.setenv("USERPROFILE", r"C:\Users\Ada")
    monkeypatch.setenv("HOME", "/home/ada")

    redacted = redact_sensitive_text(
        r"C:\Users\Ada\Projects\app.py and /home/ada/projects/app.py"
    )

    assert r"C:\Users\Ada" not in redacted
    assert "/home/ada" not in redacted
    assert r"<user-home>\Projects\app.py" in redacted
    assert "<user-home>/projects/app.py" in redacted


def test_bundle_renderer_redacts_home_path_details(monkeypatch):
    monkeypatch.setenv("USERPROFILE", r"C:\Users\Ada")

    report = DiagnosticsReport(
        "LitLaunch Inspect",
        (
            DiagnosticSection(
                "Platform",
                (
                    DiagnosticItem(
                        "Python executable",
                        DiagnosticStatus.INFO,
                        r"C:\Users\Ada\.venv\Scripts\python.exe",
                    ),
                ),
            ),
        ),
    )

    rendered = SanitizedBundleRenderer().render(report)

    assert r"C:\Users\Ada" not in rendered
    assert r"<user-home>\.venv\Scripts\python.exe" in rendered


def test_report_output_does_not_include_sensitive_command_values():
    report = make_collector().collect(
        app_path=EXAMPLE_APP,
        streamlit_args=("--server.cookieSecret", "super-secret-token"),
    )
    rendered = HTMLDiagnosticsRenderer().render(report)

    assert "super-secret-token" not in rendered
    assert "&lt;redacted&gt;" in rendered


def test_all_renderers_hide_fake_shutdown_token():
    report = DiagnosticsReport(
        "LitLaunch Inspect",
        (
            DiagnosticSection(
                "Shutdown",
                (
                    DiagnosticItem(
                        "Shutdown token",
                        DiagnosticStatus.INFO,
                        "shutdown token abc123shutdown",
                        detail="secret=abc123shutdown",
                    ),
                ),
            ),
        ),
    )

    outputs = (
        JSONDiagnosticsRenderer().render(report),
        HTMLDiagnosticsRenderer().render(report),
        SanitizedBundleRenderer().render(report),
    )

    for output in outputs:
        assert "abc123shutdown" not in output
        assert "<redacted>" in output or "&lt;redacted&gt;" in output
        assert "PATH=" not in output
