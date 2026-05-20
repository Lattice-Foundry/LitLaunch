from __future__ import annotations

import json
import sys
import tempfile
from contextlib import contextmanager
from io import StringIO
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib

import litlaunch.cli as cli
from litlaunch import __version__
from litlaunch.browsers import BrowserCapability, BrowserKind, BrowserResolution
from litlaunch.cli import build_parser, main
from litlaunch.config import BrowserChoice
from litlaunch.inspect import (
    DiagnosticItem,
    DiagnosticSection,
    DiagnosticsReport,
    DiagnosticStatus,
)
from litlaunch.lifecycle import LaunchPlan, LaunchResult, LaunchState
from litlaunch.platforms import Architecture, OperatingSystem, PlatformInfo
from litlaunch.ports import PortError
from litlaunch.redaction import format_command_preview
from litlaunch.windowing import (
    NoopWindowMonitor,
    WindowMonitorResult,
    WindowMonitorStatus,
)

EXAMPLE_APP = Path("examples/minimal_app/app.py")


@contextmanager
def temporary_output_dir():
    with tempfile.TemporaryDirectory(prefix="litlaunch-test-", dir=Path.cwd()) as path:
        yield Path(path)


def fake_platform_info():
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
    def __init__(self):
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

    def resolve(self, choice, platform_info=None, *, prefer_app_mode=False):
        self.resolve_calls.append((choice, platform_info, prefer_app_mode))
        return BrowserResolution(
            requested=BrowserChoice.AUTO,
            selected=None,
            fallback_chain=(),
            message="Selected Edge.",
        )


class FakeSession:
    def __init__(
        self,
        *,
        ok=True,
        wait_return=0,
        wait_raises=False,
        monitor_result=None,
    ):
        self.ok = ok
        self.url = "http://127.0.0.1:8501"
        self.process = object() if ok else None
        self.wait_return = wait_return
        self.wait_raises = wait_raises
        self.monitor_result = monitor_result
        self.wait_calls = 0
        self.stop_calls = 0
        self.stop_args = []
        self.monitor_calls = []
        self.result = LaunchResult(
            ok=ok,
            state=LaunchState.RUNNING if ok else LaunchState.FAILED,
            command=("python", "-m", "streamlit"),
            pid=123,
            url=self.url,
            message="running" if ok else "failed cleanly",
            events=(),
        )

    def wait(self):
        self.wait_calls += 1
        if self.wait_raises:
            raise KeyboardInterrupt
        return self.wait_return

    def stop(self, *args, **kwargs):
        self.stop_calls += 1
        self.stop_args.append((args, kwargs))

    @property
    def browser(self):
        return self.result.browser

    def monitor_window(self, monitor, target, **kwargs):
        self.monitor_calls.append((monitor, target, kwargs))
        result = self.monitor_result or WindowMonitorResult(
            supported=True,
            observed=True,
            closed=True,
            status=WindowMonitorStatus.WINDOW_CLOSED,
            message="window closed",
        )
        if result.closed:
            self.stop()
        return result


class FakeCliMonitor:
    def __init__(self, windows=()):
        self.windows = tuple(windows)
        self.capture_calls = []

    def capture(self, target):
        self.capture_calls.append(target)
        return self.windows


class FakeLauncher:
    instances = []
    next_session = FakeSession()

    def __init__(self, config, *, console_renderer=None):
        self.config = config
        self.console_renderer = console_renderer
        self.run_calls = 0
        self.command_builder = FakeCommandBuilder(config)
        FakeLauncher.instances.append(self)

    def resolve_port(self):
        return self.config.port or 8501

    def build_app_url(self, port=None):
        resolved_port = port or self.resolve_port()
        return f"http://{self.config.host}:{resolved_port}"

    def resolve_browser(self):
        return BrowserResolution(
            requested=self.config.browser,
            selected=None,
            fallback_chain=(),
            message="Selected default browser.",
        )

    def build_launch_plan(self, *, include_browser_resolution=True):
        port = self.resolve_port()
        command = self.command_builder.build(port=port)
        return LaunchPlan(
            command=command,
            command_display=format_command_preview(command),
            backend_description="Streamlit backend",
            backend_kind="streamlit",
            cwd=self.config.cwd,
            app_url=self.build_app_url(port),
            health_url=f"http://{self.config.host}:{port}/_stcore/health",
            host=self.config.host,
            port=self.config.port,
            resolved_port=port,
            auto_port=self.config.auto_port,
            mode=self.config.mode,
            headless=self.config.mode.value == "webapp",
            browser_requested=self.config.browser,
            browser_resolution=(
                self.resolve_browser() if include_browser_resolution else None
            ),
            allow_browser_fallback=self.config.allow_browser_fallback,
            app_args=self.config.app_args,
            streamlit_flags=self.config.streamlit_flags,
            streamlit_args=self.config.streamlit_args,
            extra_env_preview="none",
        )

    def run(self):
        self.run_calls += 1
        return FakeLauncher.next_session


class FakeCommandBuilder:
    def __init__(self, config):
        self.config = config

    def build(self, *, port=None):
        command = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(self.config.app_path),
            "--server.port",
            str(port or self.config.port or 8501),
        ]
        command.extend(self.config.streamlit_args)
        if self.config.app_args:
            command.append("--")
            command.extend(self.config.app_args)
        return tuple(command)


def reset_fake_launcher(session):
    FakeLauncher.instances = []
    FakeLauncher.next_session = session
    return FakeLauncher


class FakeDiagnosticCollector:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.collect_calls = []
        FakeDiagnosticCollector.instances.append(self)

    def collect(self, **kwargs):
        self.collect_calls.append(kwargs)
        if kwargs.get("app_path") == "missing.py":
            return DiagnosticsReport(
                "LitLaunch Inspect",
                (
                    DiagnosticSection(
                        "Target",
                        (
                            DiagnosticItem(
                                "App path exists",
                                DiagnosticStatus.ERROR,
                                "missing.py does not exist; token abc123shutdown",
                            ),
                        ),
                    ),
                ),
            )
        return DiagnosticsReport(
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


def run_fake_inspect(args):
    stream = StringIO()
    FakeDiagnosticCollector.instances = []
    code = main(
        args,
        stream=stream,
        platform_detector_factory=FakePlatformDetector,
        browser_registry_factory=FakeBrowserRegistry,
        diagnostic_collector_factory=FakeDiagnosticCollector,
    )
    collector = (
        FakeDiagnosticCollector.instances[0]
        if FakeDiagnosticCollector.instances
        else None
    )
    return code, stream.getvalue(), collector


def test_cli_parser_builds_and_help_lists_commands():
    parser = build_parser()
    help_text = parser.format_help()

    assert "version" in help_text
    assert "platform" in help_text
    assert "browsers" in help_text
    assert "inspect" in help_text
    assert "command" in help_text
    assert "run" in help_text
    assert "source-checkout minimal example" in help_text


def test_cli_version_returns_zero_and_prints_version():
    stream = StringIO()

    code = main(["version"], stream=stream)

    assert code == 0
    assert f"LitLaunch {__version__}" in stream.getvalue()


def test_cli_platform_outputs_summary_and_verbose_details():
    stream = StringIO()

    code = main(
        ["platform", "--verbose"],
        stream=stream,
        platform_detector_factory=FakePlatformDetector,
    )

    output = stream.getvalue()
    assert code == 0
    assert "Windows x64 / Python 3.14.5" in output
    assert "python_executable: X:/Python/python.exe" in output
    assert "supports_chromium_app_mode: True" in output


def test_cli_browsers_outputs_capabilities_without_launching():
    stream = StringIO()
    registry = FakeBrowserRegistry()

    code = main(
        ["browsers", "--no-color"],
        stream=stream,
        platform_detector_factory=FakePlatformDetector,
        browser_registry_factory=lambda: registry,
    )

    output = stream.getvalue()
    assert code == 0
    assert "Browser capabilities" in output
    assert "Edge: available, app-mode" in output
    assert "Chrome: unavailable, app-mode" in output
    assert "Auto app-mode strategy: Selected Edge." in output
    assert registry.detect_calls
    assert "\033[" not in output


def test_cli_inspect_outputs_report_and_returns_zero_without_launching():
    stream = StringIO()
    FakeDiagnosticCollector.instances = []

    def launcher_factory(*args, **kwargs):
        raise AssertionError("inspect should not construct or run launcher directly")

    code = main(
        ["inspect", "--mode", "webapp", "--browser", "edge", "--port", "8600"],
        stream=stream,
        platform_detector_factory=FakePlatformDetector,
        browser_registry_factory=FakeBrowserRegistry,
        launcher_factory=launcher_factory,
        diagnostic_collector_factory=FakeDiagnosticCollector,
    )

    collector = FakeDiagnosticCollector.instances[0]
    output = stream.getvalue()
    assert code == 0
    assert "LitLaunch Inspect" in output
    assert "[OK] Platform: Windows x64 / Python 3.14.5" in output
    assert collector.collect_calls[0]["app_path"] is None
    assert collector.collect_calls[0]["mode"] == "webapp"
    assert collector.collect_calls[0]["browser"] == "edge"
    assert collector.collect_calls[0]["port"] == 8600
    assert collector.collect_calls[0]["auto_port"] is True


def test_cli_inspect_no_auto_port_maps_to_false():
    code, _output, collector = run_fake_inspect(
        ["inspect", str(EXAMPLE_APP), "--port", "8600", "--no-auto-port"]
    )

    assert code == 0
    assert collector.collect_calls[0]["port"] == 8600
    assert collector.collect_calls[0]["auto_port"] is False


def test_cli_inspect_returns_nonzero_for_report_errors():
    code, output, _collector = run_fake_inspect(["inspect", "missing.py"])

    assert code == 1
    assert "[ERROR] App path exists: missing.py does not exist;" in output
    assert "abc123shutdown" not in output


def test_cli_inspect_json_returns_parseable_json():
    code, output, collector = run_fake_inspect(["inspect", "--json"])
    data = json.loads(output)

    assert code == 0
    assert data["title"] == "LitLaunch Inspect"
    assert data["schema_version"] == 1
    assert data["generated_by"] == "litlaunch"
    assert data["litlaunch_version"] == "0.30.0"
    assert "generated_at_utc" in data
    assert data["sections"][0]["title"] == "Platform"
    assert collector.collect_calls[0]["app_path"] is None
    assert "\033[" not in output


def test_cli_inspect_app_json_passes_app_path():
    code, output, collector = run_fake_inspect(
        ["inspect", str(EXAMPLE_APP), "--json", "--quiet"]
    )
    data = json.loads(output)

    assert code == 0
    assert data["ok"] is True
    assert collector.collect_calls[0]["app_path"] == str(EXAMPLE_APP)
    assert "LitLaunch Inspect" in output


def test_cli_inspect_bundle_returns_sanitized_bundle():
    code, output, _collector = run_fake_inspect(["inspect", "--bundle"])

    assert code == 0
    assert "LitLaunch Support Bundle" in output
    assert "This report is sanitized" in output
    assert "[OK] Platform: Windows x64 / Python 3.14.5" in output
    assert "PATH=" not in output


def test_cli_inspect_app_bundle_quiet_still_outputs_bundle():
    code, output, collector = run_fake_inspect(
        ["inspect", str(EXAMPLE_APP), "--bundle", "--quiet", "--no-color"]
    )

    assert code == 0
    assert collector.collect_calls[0]["app_path"] == str(EXAMPLE_APP)
    assert "LitLaunch Support Bundle" in output
    assert "\033[" not in output


def test_cli_inspect_json_output_writes_utf8_file_without_dumping_stdout():
    with temporary_output_dir() as output_dir:
        output_path = output_dir / "report.json"
        code, output, _collector = run_fake_inspect(
            ["inspect", "--json", "--output", str(output_path)]
        )

        data = json.loads(output_path.read_text(encoding="utf-8"))

    assert code == 0
    assert data["title"] == "LitLaunch Inspect"
    assert data["schema_version"] == 1
    assert output.startswith("Wrote inspect report to ")
    assert '"sections"' not in output


def test_cli_inspect_app_json_output_writes_target_report():
    with temporary_output_dir() as output_dir:
        output_path = output_dir / "target-report.json"
        code, output, collector = run_fake_inspect(
            [
                "inspect",
                str(EXAMPLE_APP),
                "--json",
                "--output",
                str(output_path),
            ]
        )
        data = json.loads(output_path.read_text(encoding="utf-8"))

    assert code == 0
    assert data["ok"] is True
    assert collector.collect_calls[0]["app_path"] == str(EXAMPLE_APP)
    assert "Wrote inspect report to" in output


def test_cli_inspect_bundle_output_writes_file():
    with temporary_output_dir() as output_dir:
        output_path = output_dir / "litlaunch-report.txt"
        code, output, _collector = run_fake_inspect(
            ["inspect", "--bundle", "--output", str(output_path)]
        )
        content = output_path.read_text(encoding="utf-8")

    assert code == 0
    assert "LitLaunch Support Bundle" in content
    assert "Generated at:" in content
    assert "This report is sanitized" in content
    assert output.startswith("Wrote inspect report to ")


def test_cli_inspect_app_bundle_output_writes_file():
    with temporary_output_dir() as output_dir:
        output_path = output_dir / "target-report.txt"
        code, output, collector = run_fake_inspect(
            [
                "inspect",
                str(EXAMPLE_APP),
                "--bundle",
                "--output",
                str(output_path),
            ]
        )
        content = output_path.read_text(encoding="utf-8")

    assert code == 0
    assert collector.collect_calls[0]["app_path"] == str(EXAMPLE_APP)
    assert "LitLaunch Support Bundle" in content
    assert "Wrote inspect report to" in output


def test_cli_inspect_output_existing_file_requires_force():
    with temporary_output_dir() as output_dir:
        output_path = output_dir / "report.json"
        output_path.write_text("existing", encoding="utf-8")
        code, output, _collector = run_fake_inspect(
            ["inspect", "--json", "--output", str(output_path)]
        )

        assert output_path.read_text(encoding="utf-8") == "existing"

    assert code == 2
    assert "already exists" in output
    assert "--force" in output


def test_cli_inspect_output_force_overwrites_existing_file():
    with temporary_output_dir() as output_dir:
        output_path = output_dir / "report.json"
        output_path.write_text("existing", encoding="utf-8")
        code, output, _collector = run_fake_inspect(
            ["inspect", "--json", "--output", str(output_path), "--force"]
        )
        data = json.loads(output_path.read_text(encoding="utf-8"))

    assert code == 0
    assert data["title"] == "LitLaunch Inspect"
    assert "Wrote inspect report to" in output


def test_cli_inspect_output_path_as_directory_fails():
    with temporary_output_dir() as output_dir:
        code, output, _collector = run_fake_inspect(
            ["inspect", "--json", "--output", str(output_dir)]
        )

    assert code == 2
    assert "directory" in output


def test_cli_inspect_output_missing_parent_fails():
    with temporary_output_dir() as output_dir:
        output_path = output_dir / "missing" / "report.json"
        code, output, _collector = run_fake_inspect(
            ["inspect", "--json", "--output", str(output_path)]
        )

    assert code == 2
    assert "parent directory does not exist" in output.lower()


def test_cli_inspect_output_without_json_or_bundle_fails_clearly():
    with temporary_output_dir() as output_dir:
        output_path = output_dir / "report.txt"
        code, output, _collector = run_fake_inspect(
            ["inspect", "--output", str(output_path)]
        )

    assert code == 2
    assert "--output requires --json or --bundle" in output


def test_cli_inspect_force_without_output_fails_clearly():
    code, output, _collector = run_fake_inspect(["inspect", "--bundle", "--force"])

    assert code == 2
    assert "--force requires --output" in output


def test_cli_inspect_output_file_does_not_leak_tokens_on_error_report():
    with temporary_output_dir() as output_dir:
        output_path = output_dir / "report.json"
        code, output, _collector = run_fake_inspect(
            ["inspect", "missing.py", "--json", "--output", str(output_path)]
        )
        content = output_path.read_text(encoding="utf-8")

    assert code == 1
    assert "Wrote inspect report to" in output
    assert "abc123shutdown" not in content
    assert "<redacted>" in content


def test_cli_run_builds_config_and_waits_for_backend():
    stream = StringIO()
    session = FakeSession(ok=True, wait_return=0)

    code = main(
        [
            "run",
            str(EXAMPLE_APP),
            "--mode",
            "webapp",
            "--browser",
            "edge",
            "--title",
            "Example Runtime",
            "--port",
            "8600",
            "--host",
            "127.0.0.1",
            "--no-browser-fallback",
            "--streamlit-flag",
            "server.maxUploadSize=20",
            "--app-arg",
            "dataset.json",
        ],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
    )

    launcher = FakeLauncher.instances[0]
    assert code == 0
    assert launcher.config.app_path == EXAMPLE_APP
    assert launcher.config.mode.value == "webapp"
    assert launcher.config.browser.value == "edge"
    assert launcher.config.title == "Example Runtime"
    assert launcher.config.port == 8600
    assert launcher.config.auto_port is True
    assert launcher.config.allow_browser_fallback is False
    assert launcher.config.streamlit_flags["server.maxUploadSize"] == "20"
    assert launcher.config.app_args == ("dataset.json",)
    assert launcher.config.streamlit_args == ()
    assert launcher.console_renderer is not None
    assert session.wait_calls == 1
    assert "Runtime active at http://127.0.0.1:8501" in stream.getvalue()


def test_cli_run_no_auto_port_maps_to_config_false():
    stream = StringIO()
    session = FakeSession(ok=True, wait_return=0)

    code = main(
        ["run", str(EXAMPLE_APP), "--port", "8600", "--no-auto-port"],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
    )

    launcher = FakeLauncher.instances[0]
    assert code == 0
    assert launcher.config.port == 8600
    assert launcher.config.auto_port is False


def test_cli_command_no_auto_port_maps_to_config_false():
    stream = StringIO()

    code = main(
        ["command", str(EXAMPLE_APP), "--port", "8600", "--no-auto-port"],
        stream=stream,
        launcher_factory=reset_fake_launcher(FakeSession(ok=True)),
    )

    launcher = FakeLauncher.instances[0]
    assert code == 0
    assert launcher.config.port == 8600
    assert launcher.config.auto_port is False


def test_cli_command_no_auto_port_busy_port_fails_clearly():
    stream = StringIO()

    class BusyPortLauncher(FakeLauncher):
        def resolve_port(self):
            raise PortError("Port 8600 is already in use on 127.0.0.1.")

    code = main(
        ["command", str(EXAMPLE_APP), "--port", "8600", "--no-auto-port"],
        stream=stream,
        launcher_factory=BusyPortLauncher,
    )

    assert code == 2
    assert "Port 8600 is already in use on 127.0.0.1." in stream.getvalue()


def test_cli_run_returns_nonzero_on_failed_session():
    stream = StringIO()

    code = main(
        ["run", str(EXAMPLE_APP)],
        stream=stream,
        launcher_factory=reset_fake_launcher(FakeSession(ok=False)),
    )

    assert code == 1
    assert "failed cleanly" in stream.getvalue()


def test_cli_run_rejects_missing_app_path_before_launching():
    stream = StringIO()

    def launcher_factory(*args, **kwargs):
        raise AssertionError("launcher should not be constructed for a missing app")

    code = main(
        ["run", "does-not-exist.py"],
        stream=stream,
        launcher_factory=launcher_factory,
    )

    assert code == 2
    assert "Streamlit app path does not exist" in stream.getvalue()


def test_cli_run_rejects_invalid_host_before_launching():
    stream = StringIO()

    def launcher_factory(*args, **kwargs):
        raise AssertionError("launcher should not be constructed for invalid host")

    code = main(
        ["run", str(EXAMPLE_APP), "--host", "bad host"],
        stream=stream,
        launcher_factory=launcher_factory,
    )

    assert code == 2
    assert "host must be a valid IP address or plausible hostname" in stream.getvalue()


def test_cli_run_dry_run_prints_command_without_starting_backend():
    stream = StringIO()
    session = FakeSession(ok=True)

    code = main(
        [
            "run",
            str(EXAMPLE_APP),
            "--port",
            "8600",
            "--dry-run",
            "--server.runOnSave",
            "true",
            "--",
            "--workspace",
            "demo",
        ],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
    )

    launcher = FakeLauncher.instances[0]
    output = stream.getvalue()
    assert code == 0
    assert launcher.run_calls == 0
    assert launcher.config.streamlit_args == ("--server.runOnSave", "true")
    assert launcher.config.app_args == ("--workspace", "demo")
    assert "Dry run" in output
    assert "App URL: http://127.0.0.1:8600" in output
    assert "Mode: browser" in output
    assert "Browser: Selected default browser." in output
    assert "--server.runOnSave true -- --workspace demo" in output


def test_cli_run_dry_run_redacts_sensitive_streamlit_args():
    stream = StringIO()
    session = FakeSession(ok=True)

    code = main(
        [
            "run",
            str(EXAMPLE_APP),
            "--dry-run",
            "--server.cookieSecret",
            "super-secret-token",
        ],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
    )

    output = stream.getvalue()
    assert code == 0
    assert "super-secret-token" not in output
    assert "<redacted>" in output


def test_cli_command_prints_resolved_streamlit_command():
    stream = StringIO()

    code = main(
        [
            "command",
            str(EXAMPLE_APP),
            "--port",
            "8600",
            "--theme.base=dark",
            "--logger.enableRich",
            "--",
            "--workspace",
            "demo",
        ],
        stream=stream,
        launcher_factory=reset_fake_launcher(FakeSession(ok=True)),
    )

    launcher = FakeLauncher.instances[0]
    output = stream.getvalue()
    assert code == 0
    assert launcher.run_calls == 0
    assert launcher.config.streamlit_args == (
        "--theme.base=dark",
        "--logger.enableRich",
    )
    assert launcher.config.app_args == ("--workspace", "demo")
    assert sys.executable in output
    assert "streamlit run" in output
    assert "--theme.base=dark --logger.enableRich -- --workspace demo" in output


def test_cli_command_redacts_sensitive_streamlit_args():
    stream = StringIO()

    code = main(
        [
            "command",
            str(EXAMPLE_APP),
            "--server.cookieSecret",
            "super-secret-token",
        ],
        stream=stream,
        launcher_factory=reset_fake_launcher(FakeSession(ok=True)),
    )

    output = stream.getvalue()
    assert code == 0
    assert "super-secret-token" not in output
    assert "<redacted>" in output


def test_cli_run_keyboard_interrupt_stops_session():
    stream = StringIO()
    session = FakeSession(ok=True, wait_raises=True)

    code = main(
        ["run", str(EXAMPLE_APP)],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
    )

    assert code == 0
    assert session.stop_calls == 1
    assert "Interrupt received; stopping runtime." in stream.getvalue()


def test_cli_run_monitor_window_requires_webapp_mode():
    stream = StringIO()

    def launcher_factory(*args, **kwargs):
        raise AssertionError("launcher should not be constructed for invalid mode")

    code = main(
        ["run", str(EXAMPLE_APP), "--monitor-window"],
        stream=stream,
        launcher_factory=launcher_factory,
    )

    assert code == 2
    assert "--monitor-window is only valid with --mode webapp" in stream.getvalue()


def test_cli_run_monitor_window_closure_stops_runtime():
    stream = StringIO()
    session = FakeSession(
        ok=True,
        monitor_result=WindowMonitorResult(
            supported=True,
            observed=True,
            closed=True,
            status=WindowMonitorStatus.WINDOW_CLOSED,
            message="window closed",
        ),
    )
    monitor = FakeCliMonitor()

    code = main(
        ["run", str(EXAMPLE_APP), "--mode", "webapp", "--monitor-window"],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
        platform_detector_factory=FakePlatformDetector,
        window_monitor_factory=lambda platform_info: monitor,
    )

    output = stream.getvalue()
    assert code == 0
    assert session.wait_calls == 0
    assert session.stop_calls == 1
    assert session.monitor_calls[0][0] is monitor
    assert session.monitor_calls[0][2]["graceful_timeout_seconds"] == 3.0
    assert monitor.capture_calls[0].title == "Streamlit App"
    assert session.monitor_calls[0][1].title == "Streamlit App"
    assert session.monitor_calls[0][1].app_mode is True
    assert "window closed" in output


def test_cli_run_monitor_window_uses_configured_title():
    stream = StringIO()
    session = FakeSession(ok=True)
    monitor = FakeCliMonitor(windows=[type("Window", (), {"handle": "old"})()])

    code = main(
        [
            "run",
            str(EXAMPLE_APP),
            "--mode",
            "webapp",
            "--monitor-window",
            "--title",
            "LitLaunch Example App",
        ],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
        platform_detector_factory=FakePlatformDetector,
        window_monitor_factory=lambda platform_info: monitor,
    )

    assert code == 0
    assert FakeLauncher.instances[0].config.title == "LitLaunch Example App"
    assert session.monitor_calls[0][1].title == "LitLaunch Example App"
    assert session.monitor_calls[0][1].baseline_handles == ("old",)


def test_cli_run_monitor_window_passes_custom_graceful_timeout():
    stream = StringIO()
    session = FakeSession(ok=True)

    code = main(
        [
            "run",
            str(EXAMPLE_APP),
            "--mode",
            "webapp",
            "--monitor-window",
            "--graceful-timeout",
            "14.5",
        ],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
        platform_detector_factory=FakePlatformDetector,
        window_monitor_factory=lambda platform_info: FakeCliMonitor(),
    )

    assert code == 0
    assert session.monitor_calls[0][2]["graceful_timeout_seconds"] == 14.5


def test_cli_run_rejects_nonpositive_graceful_timeout():
    stream = StringIO()

    code = main(
        [
            "run",
            str(EXAMPLE_APP),
            "--mode",
            "webapp",
            "--monitor-window",
            "--graceful-timeout",
            "0",
        ],
        stream=stream,
        launcher_factory=reset_fake_launcher(FakeSession(ok=True)),
    )

    assert code == 2
    assert "--graceful-timeout must be positive" in stream.getvalue()


def test_cli_run_monitor_window_unsupported_returns_nonzero_and_stops_runtime():
    stream = StringIO()
    session = FakeSession(
        ok=True,
        monitor_result=WindowMonitorResult(
            supported=False,
            observed=False,
            closed=False,
            status=WindowMonitorStatus.UNSUPPORTED,
            message="window monitoring unsupported",
        ),
    )

    code = main(
        ["run", str(EXAMPLE_APP), "--mode", "webapp", "--monitor-window"],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
        platform_detector_factory=FakePlatformDetector,
        window_monitor_factory=lambda platform_info: FakeCliMonitor(),
    )

    assert code == 1
    assert session.stop_calls == 1
    assert "window monitoring unsupported" in stream.getvalue()


def test_cli_run_monitor_window_noop_monitor_fails_before_launch():
    stream = StringIO()

    code = main(
        ["run", str(EXAMPLE_APP), "--mode", "webapp", "--monitor-window"],
        stream=stream,
        launcher_factory=reset_fake_launcher(FakeSession(ok=True)),
        platform_detector_factory=FakePlatformDetector,
        window_monitor_factory=lambda platform_info: NoopWindowMonitor(),
    )

    assert code == 1
    assert FakeLauncher.instances[0].run_calls == 0
    assert "Window monitoring is unavailable" in stream.getvalue()
    assert "Omit --monitor-window" in stream.getvalue()


def test_cli_run_monitor_window_backend_exit_returns_zero_without_extra_stop():
    stream = StringIO()
    session = FakeSession(
        ok=True,
        monitor_result=WindowMonitorResult(
            supported=True,
            observed=True,
            closed=False,
            status=WindowMonitorStatus.BACKEND_EXITED,
            message="backend exited",
        ),
    )

    code = main(
        ["run", str(EXAMPLE_APP), "--mode", "webapp", "--monitor-window"],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
        platform_detector_factory=FakePlatformDetector,
        window_monitor_factory=lambda platform_info: FakeCliMonitor(),
    )

    assert code == 0
    assert session.wait_calls == 0
    assert session.stop_calls == 0
    assert "backend exited" in stream.getvalue()


def test_cli_run_monitor_window_timeout_returns_nonzero_and_stops_runtime():
    stream = StringIO()
    session = FakeSession(
        ok=True,
        monitor_result=WindowMonitorResult(
            supported=True,
            observed=False,
            closed=False,
            status=WindowMonitorStatus.TIMEOUT,
            message="timed out",
        ),
    )

    code = main(
        ["run", str(EXAMPLE_APP), "--mode", "webapp", "--monitor-window"],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
        platform_detector_factory=FakePlatformDetector,
        window_monitor_factory=lambda platform_info: FakeCliMonitor(),
    )

    assert code == 1
    assert session.stop_calls == 1
    assert "timed out" in stream.getvalue()


def test_cli_quiet_suppresses_run_success_message():
    stream = StringIO()
    session = FakeSession(ok=True, wait_return=0)

    code = main(
        ["run", str(EXAMPLE_APP), "--quiet"],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
    )

    assert code == 0
    assert "Runtime active" not in stream.getvalue()


def test_cli_example_prints_example_path():
    stream = StringIO()

    code = main(["example"], stream=stream)

    output = stream.getvalue()
    assert code == 0
    assert "examples" in output
    assert "minimal_app" in output
    assert output.strip().endswith("app.py")


def test_cli_example_fails_clearly_when_source_example_is_missing(monkeypatch):
    stream = StringIO()
    monkeypatch.setattr(
        cli,
        "_source_checkout_example_path",
        lambda module_path: Path("X:/missing/examples/minimal_app/app.py"),
    )

    code = main(["example"], stream=stream)

    output = stream.getvalue()
    assert code == 1
    assert "source checkout" in output
    assert "X:/missing" not in output


def test_cli_console_script_entrypoint_exists():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["litlaunch"] == "litlaunch.cli:main"
