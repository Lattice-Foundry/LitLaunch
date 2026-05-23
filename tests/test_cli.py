from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
import tempfile
from contextlib import contextmanager
from io import StringIO
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib

from litlaunch import __version__
from litlaunch.browsers import BrowserCapability, BrowserKind, BrowserResolution
from litlaunch.cli import build_parser, main
from litlaunch.colors import THEME_COLORS, muted_amber, streamlit_blue, terminal_green
from litlaunch.config import BrowserChoice, LaunchMode, TrustMode
from litlaunch.console import strip_ansi
from litlaunch.inspect import (
    DiagnosticItem,
    DiagnosticSection,
    DiagnosticsReport,
    DiagnosticStatus,
)
from litlaunch.lifecycle import LaunchPlan, LaunchResult, LaunchState
from litlaunch.platforms import Architecture, OperatingSystem, PlatformInfo
from litlaunch.ports import PortError
from litlaunch.profiles import load_profile
from litlaunch.redaction import format_command_preview
from litlaunch.windowing import (
    NoopWindowMonitor,
    WindowInfo,
    WindowMonitorResult,
    WindowMonitorStatus,
)

EXAMPLE_APP = Path("examples/minimal_app/app.py")
CLI_MAIN_MODULE = importlib.import_module("litlaunch.cli.main")
CLI_COMMANDS_MODULE = importlib.import_module("litlaunch.cli.commands")
CLI_INSPECT_MODULE = importlib.import_module("litlaunch.cli.inspect")


@contextmanager
def temporary_output_dir():
    with tempfile.TemporaryDirectory(prefix="litlaunch-cli-output-") as path:
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


class FakeUnsupportedWindowMonitorPlatformDetector:
    def detect(self):
        return PlatformInfo(
            os=OperatingSystem.LINUX,
            architecture=Architecture.X64,
            python_version="3.14.5",
            python_executable="/usr/bin/python",
            machine="x86_64",
            system="Linux",
            release="6",
            is_windows=False,
            is_macos=False,
            is_linux=True,
            supports_chromium_app_mode=True,
            supports_window_monitoring=False,
            supports_default_browser_open=True,
            notes=(),
        )


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


def _failing_launcher_factory(*args, **kwargs):
    raise AssertionError("create profile should not launch or build runtime")


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
        self.running = ok
        self.console_renderer = None
        self.events = []
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
        self.running = False

    def is_running(self):
        return self.running

    def add_event(self, state, message, *, render=True):
        self.events.append((state, message, render))

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


class SequenceCliMonitor:
    def __init__(self, snapshots):
        self.snapshots = list(snapshots)
        self.capture_calls = []

    def capture(self, target):
        self.capture_calls.append(target)
        if self.snapshots:
            return self.snapshots.pop(0)
        return ()


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
    assert "help" in help_text
    assert "inspect" in help_text
    assert "report" in help_text
    assert "command" in help_text
    assert "run" in help_text
    assert "create" in help_text
    assert "source-checkout minimal example" in help_text
    assert "litlaunch app.py" in help_text
    assert "litlaunch --profile my-webapp" in help_text
    assert re.search(r"litlaunch\s+report --profile my-webapp", help_text)
    assert "console-preview" not in help_text


def test_cli_workflow_help_menu_lists_topics():
    stream = StringIO()

    code = main(["help"], stream=stream)

    output = strip_ansi(stream.getvalue())
    assert code == 0
    assert "LitLaunch workflow help" in output
    assert "Use --help for command reference" in output
    assert "launch" in output
    assert "diagnostics" in output
    assert "security" in output
    assert "profiles" in output
    assert "tools" in output
    assert "examples" in output
    assert "dev" in output


def test_cli_workflow_help_launch_topic():
    stream = StringIO()

    code = main(["help", "launch"], stream=stream)

    output = strip_ansi(stream.getvalue())
    assert code == 0
    assert "Launch workflows" in output
    assert "litlaunch app.py" in output
    assert "litlaunch --profile NAME" in output
    assert "litlaunch run app.py" in output
    assert "litlaunch run --profile NAME" in output
    assert "--monitor-window" in output
    assert "--no-monitor-window" in output
    assert "Bare profile names are intentionally not supported" in output
    assert "litlaunch NAME" not in output
    assert "python -m litlaunch.cli" not in output


def test_cli_workflow_help_diagnostics_topic():
    stream = StringIO()

    code = main(["help", "diagnostics"], stream=stream)

    output = strip_ansi(stream.getvalue())
    assert code == 0
    assert "Diagnostics workflows" in output
    assert "litlaunch report" in output
    assert "litlaunch report app.py" in output
    assert "litlaunch report --profile NAME" in output
    assert "litlaunch report --profile NAME --open" in output
    assert "litlaunch inspect --json" in output
    assert "litlaunch inspect --bundle" in output
    assert "litlaunch inspect --html --output report.html" in output
    assert "recommended human-readable HTML diagnostics workflow" in output
    assert "Runtime Governance" in output
    assert "--streamlit-flag" in output


def test_cli_workflow_help_security_topic():
    stream = StringIO()

    code = main(["help", "security"], stream=stream)

    output = strip_ansi(stream.getvalue())
    assert code == 0
    assert "Security and governance workflows" in output
    assert "LitLaunch does not secure Streamlit applications" in output
    assert "litlaunch app.py --trust-mode strict_local" in output
    assert "--allow-network-exposure" in output
    assert "server.sslCertFile" in output
    assert "Runtime Governance" in output
    assert "Transport Security" in output


def test_cli_workflow_help_profiles_topic():
    stream = StringIO()

    code = main(["help", "profiles"], stream=stream)

    output = strip_ansi(stream.getvalue())
    assert code == 0
    assert "Profile workflows" in output
    assert "litlaunch create profile" in output
    assert "litlaunch --profile NAME" in output
    assert "litlaunch run --profile NAME" in output
    assert "--config litlaunch.toml" in output
    assert "pyproject.toml under [tool.litlaunch]" in output
    assert "trust_mode" in output
    assert "allow_network_exposure" in output


def test_cli_workflow_help_examples_topic():
    stream = StringIO()

    code = main(["help", "examples"], stream=stream)

    output = strip_ansi(stream.getvalue())
    assert code == 0
    assert "Examples" in output
    assert "litlaunch app.py" in output
    assert "litlaunch create profile" in output
    assert "litlaunch report --profile my-webapp" in output
    assert "litlaunch command app.py" in output
    assert "litlaunch command --profile my-webapp" in output
    assert "litlaunch browsers" in output
    assert "litlaunch browsers --verbose" in output
    assert "litlaunch platform" in output
    assert "litlaunch version" in output
    assert "litlaunch example" in output


def test_cli_workflow_help_dev_topic_frames_internal_preview_tooling():
    stream = StringIO()

    code = main(["help", "dev"], stream=stream)

    output = strip_ansi(stream.getvalue())
    assert code == 0
    assert "Developer tooling" in output
    assert "internal developer-facing" in output
    assert "litlaunch console-preview --all" in output
    assert "litlaunch console-preview --normal" in output
    assert "litlaunch console-preview --verbose" in output
    assert "internal developer workflow" in output


def test_cli_workflow_help_all_includes_main_topics():
    stream = StringIO()

    code = main(["help", "all"], stream=stream)

    output = strip_ansi(stream.getvalue())
    assert code == 0
    assert "LitLaunch workflow overview" in output
    assert "litlaunch app.py" in output
    assert "litlaunch report --profile NAME --open" in output
    assert "litlaunch create profile" in output
    assert "litlaunch command --profile NAME" in output
    assert "litlaunch help security" in output
    assert "litlaunch help tools" in output
    assert "litlaunch help dev" in output
    assert "Bare profile names are intentionally not supported" in output


def test_cli_workflow_help_tools_topic():
    stream = StringIO()

    code = main(["help", "tools"], stream=stream)

    output = strip_ansi(stream.getvalue())
    assert code == 0
    assert "Tools workflows" in output
    assert "litlaunch create profile" in output
    assert "litlaunch create profile --dry-run" in output
    assert "litlaunch create shortcut --profile my-webapp" in output
    assert "Wizard shortcut integration is planned separately" not in output


def test_cli_workflow_help_uses_approved_palette():
    stream = StringIO()

    code = main(["help", "launch"], stream=stream, env={})

    output = stream.getvalue()
    assert code == 0
    assert THEME_COLORS[streamlit_blue].ansi in output
    assert THEME_COLORS[terminal_green].ansi in output
    assert THEME_COLORS[muted_amber].ansi in output
    assert "\033[92m" not in output
    assert "\033[38;2;131;201;255m" not in output


def test_cli_workflow_help_unknown_topic_fails_cleanly():
    stream = StringIO()

    code = main(["help", "unknown"], stream=stream)

    output = stream.getvalue()
    assert code == 2
    assert "Unknown help topic: unknown" in output
    assert "launch" in output


def test_cli_create_profile_parser_exists():
    parser = build_parser()

    args = parser.parse_args(["create", "profile", "--name", "web", "--app", "app.py"])

    assert args.command == "create"
    assert args.create_command == "profile"
    assert args.name == "web"
    assert args.app_path == "app.py"


def test_cli_create_shortcut_parser_exists():
    parser = build_parser()

    args = parser.parse_args(["create", "shortcut", "--profile", "web"])

    assert args.command == "create"
    assert args.create_command == "shortcut"
    assert args.profile == "web"


def test_cli_create_help_describes_tools_namespace(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["create", "--help"])

    output = strip_ansi(capsys.readouterr().out)
    assert exc_info.value.code == 0
    assert "{profile,shortcut}" in output
    assert "profile" in output
    assert "shortcut" in output


def test_cli_create_profile_help_describes_wizard_and_shortcut_offer(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["create", "profile", "--help"])

    output = strip_ansi(capsys.readouterr().out)
    assert exc_info.value.code == 0
    assert "Simple mode" in output
    assert "Advanced mode" in output
    assert "optionally create a launch shortcut" in output
    assert "litlaunch create profile --dry-run" in output
    assert "python -m litlaunch.cli" not in output


def test_cli_create_shortcut_help_describes_profile_shortcuts(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["create", "shortcut", "--help"])

    output = strip_ansi(capsys.readouterr().out)
    assert exc_info.value.code == 0
    assert "OS-appropriate launch shortcut" in output
    assert "--profile" in output
    assert "--kind" in output
    assert "litlaunch create shortcut --profile my-webapp" in output
    assert "python -m litlaunch.cli" not in output


def test_cli_create_profile_simple_mode_writes_webapp_profile(monkeypatch):
    with temporary_output_dir() as output_dir, monkeypatch.context() as m:
        m.chdir(output_dir)
        m.setattr(
            "litlaunch.shortcut_writer._write_windows_lnk",
            lambda plan: plan.output_path.write_bytes(b"lnk"),
        )
        (output_dir / "app.py").write_text("print('hello')\n", encoding="utf-8")
        answers = iter(["", "", "", "", "", "", "", "", "", "n"])
        m.setattr("builtins.input", lambda: next(answers))
        stream = StringIO()

        code = main(
            ["create", "profile"],
            stream=stream,
            platform_detector_factory=FakePlatformDetector,
            launcher_factory=_failing_launcher_factory,
        )

        config_path = output_dir / "litlaunch.toml"
        assert code == 0
        assert config_path.is_file()
        profile = load_profile(output_dir.name, config_path)
        assert profile.config.app_path == output_dir / "app.py"
        assert profile.config.mode == LaunchMode.WEBAPP
        assert profile.config.browser == BrowserChoice.AUTO
        assert profile.monitor_window is True
        assert profile.graceful_timeout_seconds == 15.0
        assert profile.window_monitor_config.stable_poll_count == 2
        output = stream.getvalue()
        assert "App window, recommended" in output
        assert "Create Profile Wizard" in output
        assert "Step 1 of" in output
        assert "Current profile:" in output
        assert "Profile preview" in output
        assert not (
            output_dir / ".litlaunch" / "shortcuts" / f"{output_dir.name}.lnk"
        ).exists()


def test_cli_create_profile_keyboard_interrupt_cancels_cleanly(monkeypatch):
    def raise_interrupt():
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", raise_interrupt)
    stream = StringIO()

    code = main(
        ["create", "profile"],
        stream=stream,
        platform_detector_factory=FakePlatformDetector,
    )

    output = stream.getvalue()
    assert code == 130
    assert "[  warn  ] Profile creation cancelled." in strip_ansi(output)
    assert "Traceback" not in output
    assert "KeyboardInterrupt" not in output


def test_cli_create_profile_simple_mode_accepts_shortcut(monkeypatch):
    with temporary_output_dir() as output_dir, monkeypatch.context() as m:
        m.chdir(output_dir)
        m.setattr(
            "litlaunch.shortcut_writer._write_windows_lnk",
            lambda plan: plan.output_path.write_bytes(b"lnk"),
        )
        (output_dir / "app.py").write_text("print('hello')\n", encoding="utf-8")
        answers = iter(["", "web", "", "", "", "", "", "", "", "y"])
        m.setattr("builtins.input", lambda: next(answers))
        stream = StringIO()

        code = main(
            ["create", "profile"],
            stream=stream,
            platform_detector_factory=FakePlatformDetector,
            launcher_factory=_failing_launcher_factory,
        )

        shortcut = output_dir / ".litlaunch" / "shortcuts" / "web.lnk"
        assert code == 0
        assert shortcut.is_file()
        assert shortcut.stat().st_size > 0
        assert "Created shortcut" in stream.getvalue()


def test_cli_create_profile_shortcut_existing_can_be_skipped(monkeypatch):
    with temporary_output_dir() as output_dir, monkeypatch.context() as m:
        m.chdir(output_dir)
        (output_dir / "app.py").write_text("print('hello')\n", encoding="utf-8")
        shortcut = output_dir / ".litlaunch" / "shortcuts" / "web.lnk"
        shortcut.parent.mkdir(parents=True)
        shortcut.write_text("old", encoding="utf-8")
        answers = iter(["", "web", "", "", "", "", "", "", "", "y", "n"])
        m.setattr("builtins.input", lambda: next(answers))
        stream = StringIO()

        code = main(
            ["create", "profile"],
            stream=stream,
            platform_detector_factory=FakePlatformDetector,
        )

        assert code == 0
        assert shortcut.read_text(encoding="utf-8") == "old"
        assert "Shortcut creation skipped" in stream.getvalue()


def test_cli_create_profile_quit_commands_cancel_cleanly(monkeypatch):
    for command in ("quit", "exit", "cancel"):
        answers = iter([command])
        monkeypatch.setattr(
            "builtins.input",
            lambda answers=answers: next(answers),
        )
        stream = StringIO()

        code = main(
            ["create", "profile"],
            stream=stream,
            platform_detector_factory=FakePlatformDetector,
        )

        assert code == 130
        assert "[  warn  ] Profile creation cancelled." in strip_ansi(stream.getvalue())


def test_cli_create_profile_back_navigation_preserves_values(monkeypatch):
    with temporary_output_dir() as output_dir, monkeypatch.context() as m:
        m.chdir(output_dir)
        (output_dir / "app.py").write_text("print('hello')\n", encoding="utf-8")
        answers = iter(
            [
                "",
                "first-name",
                "back",
                "second-name",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "n",
            ]
        )
        m.setattr("builtins.input", lambda: next(answers))
        stream = StringIO()

        code = main(
            ["create", "profile"],
            stream=stream,
            platform_detector_factory=FakePlatformDetector,
        )

        assert code == 0
        profile = load_profile("second-name", output_dir / "litlaunch.toml")
        assert profile.config.app_path == output_dir / "app.py"
        output = stream.getvalue()
        assert "Name:" in output
        assert "first-name" in output
        assert "second-name" in output


def test_cli_create_profile_prompts_show_current_defaults(monkeypatch):
    with temporary_output_dir() as output_dir, monkeypatch.context() as m:
        m.chdir(output_dir)
        (output_dir / "app.py").write_text("print('hello')\n", encoding="utf-8")
        answers = iter(["", "", "", "", "", "", "", "", "n"])
        m.setattr("builtins.input", lambda: next(answers))
        stream = StringIO()

        code = main(
            ["create", "profile"],
            stream=stream,
            platform_detector_factory=FakePlatformDetector,
        )

        output = stream.getvalue()
        assert code == 0
        assert f"Profile name [{output_dir.name}]:" in output
        assert "App path [app.py]:" in output
        assert "Write profile [Y/n]:" in output


def test_cli_create_profile_options_prefill_name_and_app(monkeypatch):
    with temporary_output_dir() as output_dir, monkeypatch.context() as m:
        m.chdir(output_dir)
        (output_dir / "custom.py").write_text("print('hello')\n", encoding="utf-8")
        answers = iter(["", "", "", "", "", "", "", "", "", "n"])
        m.setattr("builtins.input", lambda: next(answers))
        stream = StringIO()

        code = main(
            ["create", "profile", "--name", "custom", "--app", "custom.py"],
            stream=stream,
            platform_detector_factory=FakePlatformDetector,
        )

        profile = load_profile("custom", output_dir / "litlaunch.toml")
        assert code == 0
        assert profile.config.app_path == output_dir / "custom.py"


def test_cli_create_profile_browser_tab_maps_to_browser_mode(monkeypatch):
    with temporary_output_dir() as output_dir, monkeypatch.context() as m:
        m.chdir(output_dir)
        (output_dir / "app.py").write_text("print('hello')\n", encoding="utf-8")
        answers = iter(["", "browser-profile", "", "", "2", "", "", "", "n"])
        m.setattr("builtins.input", lambda: next(answers))
        stream = StringIO()

        code = main(
            ["create", "profile"],
            stream=stream,
            platform_detector_factory=FakePlatformDetector,
        )

        profile = load_profile("browser-profile", output_dir / "litlaunch.toml")
        assert code == 0
        assert profile.config.mode == LaunchMode.BROWSER
        assert profile.monitor_window is False


def test_cli_create_profile_dry_run_does_not_write(monkeypatch):
    with temporary_output_dir() as output_dir, monkeypatch.context() as m:
        m.chdir(output_dir)
        (output_dir / "app.py").write_text("print('hello')\n", encoding="utf-8")
        answers = iter(["", "dry-run", "", "", "", "", "", "", ""])
        m.setattr("builtins.input", lambda: next(answers))
        stream = StringIO()

        code = main(
            ["create", "profile", "--dry-run"],
            stream=stream,
            platform_detector_factory=FakePlatformDetector,
        )

        assert code == 0
        assert not (output_dir / "litlaunch.toml").exists()
        assert not (output_dir / ".litlaunch" / "shortcuts" / "dry-run.lnk").exists()
        assert '[profiles."dry-run"]' in stream.getvalue()
        assert "Dry run complete" in stream.getvalue()
        assert "Shortcut creation would be offered" in stream.getvalue()


def test_cli_create_profile_collision_and_force_behavior(monkeypatch):
    with temporary_output_dir() as output_dir, monkeypatch.context() as m:
        m.chdir(output_dir)
        (output_dir / "app.py").write_text("print('hello')\n", encoding="utf-8")
        (output_dir / "litlaunch.toml").write_text(
            """
[profiles.existing]
app_path = "app.py"
title = "Old"
""",
            encoding="utf-8",
        )
        blocked_answers = iter(
            ["", "existing", "new-name", "", "", "", "", "", "", "", "n"]
        )
        m.setattr("builtins.input", lambda: next(blocked_answers))
        blocked_stream = StringIO()

        blocked_code = main(
            ["create", "profile"],
            stream=blocked_stream,
            platform_detector_factory=FakePlatformDetector,
        )

        assert blocked_code == 0
        assert "already exists" in blocked_stream.getvalue()
        assert load_profile("new-name", output_dir / "litlaunch.toml")

        forced_answers = iter(["", "", "", "", "", "", "", "", "", "n"])
        m.setattr("builtins.input", lambda: next(forced_answers))
        forced_stream = StringIO()
        forced_code = main(
            ["create", "profile", "--name", "existing", "--force"],
            stream=forced_stream,
            platform_detector_factory=FakePlatformDetector,
        )

        assert forced_code == 0
        assert load_profile("existing", output_dir / "litlaunch.toml").config.mode == (
            LaunchMode.WEBAPP
        )


def test_cli_create_profile_advanced_mode_writes_full_profile(monkeypatch):
    with temporary_output_dir() as output_dir, monkeypatch.context() as m:
        m.chdir(output_dir)
        m.setattr(
            "litlaunch.shortcut_writer._write_windows_lnk",
            lambda plan: plan.output_path.write_bytes(b"lnk"),
        )
        (output_dir / "app.py").write_text("print('hello')\n", encoding="utf-8")
        answers = iter(
            [
                "2",
                "advanced-profile",
                "",
                "Advanced App",
                "",
                "chrome",
                "0.0.0.0",
                "y",
                "8502",
                "n",
                "n",
                "true",
                "--kiosk",
                "",
                "y",
                "20",
                "70",
                "2",
                "3",
                "server.maxUploadSize=200",
                "server.runOnSave=true",
                "",
                "--logger.level=debug",
                "",
                "--demo",
                "",
                ".",
                "LIT_MODE=dev",
                "",
                "",
                "",
                "y",
            ]
        )
        m.setattr("builtins.input", lambda: next(answers))
        stream = StringIO()

        code = main(
            ["create", "profile"],
            stream=stream,
            platform_detector_factory=FakePlatformDetector,
        )

        assert code == 0
        profile = load_profile("advanced-profile", output_dir / "litlaunch.toml")
        assert profile.config.title == "Advanced App"
        assert profile.config.mode == LaunchMode.WEBAPP
        assert profile.config.browser == BrowserChoice.CHROME
        assert profile.config.host == "0.0.0.0"
        assert profile.config.port == 8502
        assert profile.config.auto_port is False
        assert profile.config.allow_browser_fallback is False
        assert profile.config.headless is True
        assert profile.config.extra_browser_args == ("--kiosk",)
        assert profile.config.streamlit_flags["server.maxUploadSize"] == 200
        assert profile.config.streamlit_flags["server.runOnSave"] is True
        assert profile.config.streamlit_args == ("--logger.level=debug",)
        assert profile.config.app_args == ("--demo",)
        assert profile.config.extra_env["LIT_MODE"] == "dev"
        assert profile.monitor_window is True
        assert profile.graceful_timeout_seconds == 20
        assert profile.window_monitor_config.appear_timeout_seconds == 70
        assert profile.window_monitor_config.poll_interval_seconds == 2
        assert profile.window_monitor_config.stable_poll_count == 3
        shortcut = output_dir / ".litlaunch" / "shortcuts" / "advanced-profile.lnk"
        assert shortcut.is_file()
        assert shortcut.stat().st_size > 0
        output = stream.getvalue()
        assert "Advanced" in output
        assert "Streamlit flags: 2" in output
        assert "Created shortcut" in output


def test_cli_create_profile_advanced_mode_dry_run_does_not_write(monkeypatch):
    with temporary_output_dir() as output_dir, monkeypatch.context() as m:
        m.chdir(output_dir)
        (output_dir / "app.py").write_text("print('hello')\n", encoding="utf-8")
        answers = iter(
            [
                "2",
                "advanced-dry-run",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        )
        m.setattr("builtins.input", lambda: next(answers))
        stream = StringIO()

        code = main(
            ["create", "profile", "--dry-run"],
            stream=stream,
            platform_detector_factory=FakePlatformDetector,
        )

        assert code == 0
        assert not (output_dir / "litlaunch.toml").exists()
        assert '[profiles."advanced-dry-run"]' in stream.getvalue()


def test_cli_create_shortcut_dry_run_does_not_write(monkeypatch):
    with temporary_output_dir() as output_dir, monkeypatch.context() as m:
        m.chdir(output_dir)
        (output_dir / "app.py").write_text("print('hello')\n", encoding="utf-8")
        (output_dir / "litlaunch.toml").write_text(
            """
[profiles.web]
app_path = "app.py"
title = "Web"
""",
            encoding="utf-8",
        )
        stream = StringIO()

        code = main(
            ["create", "shortcut", "--profile", "web", "--dry-run"],
            stream=stream,
            platform_detector_factory=FakePlatformDetector,
        )

        assert code == 0
        assert not (output_dir / ".litlaunch" / "shortcuts" / "web.lnk").exists()
        output = stream.getvalue()
        assert "Shortcut dry run" in output
        assert "web.lnk" in output
        assert "Target: X:/Python/python.exe" in output
        assert "litlaunch.cli" in output


def test_cli_create_shortcut_writes_and_respects_force(monkeypatch):
    with temporary_output_dir() as output_dir, monkeypatch.context() as m:
        m.chdir(output_dir)
        m.setattr(
            "litlaunch.shortcut_writer._write_windows_lnk",
            lambda plan: plan.output_path.write_bytes(b"lnk"),
        )
        (output_dir / "app.py").write_text("print('hello')\n", encoding="utf-8")
        (output_dir / "litlaunch.toml").write_text(
            """
[profiles.web]
app_path = "app.py"
title = "Web"
""",
            encoding="utf-8",
        )
        stream = StringIO()

        code = main(
            ["create", "shortcut", "--profile", "web"],
            stream=stream,
            platform_detector_factory=FakePlatformDetector,
        )

        shortcut = output_dir / ".litlaunch" / "shortcuts" / "web.lnk"
        assert code == 0
        assert shortcut.is_file()
        assert "Created shortcut" in stream.getvalue()

        blocked_stream = StringIO()
        blocked_code = main(
            ["create", "shortcut", "--profile", "web"],
            stream=blocked_stream,
            platform_detector_factory=FakePlatformDetector,
        )
        assert blocked_code == 2
        assert "already exists" in blocked_stream.getvalue()

        forced_stream = StringIO()
        forced_code = main(
            ["create", "shortcut", "--profile", "web", "--force"],
            stream=forced_stream,
            platform_detector_factory=FakePlatformDetector,
        )
        assert forced_code == 0


def test_cli_create_shortcut_explicit_output_and_config(monkeypatch):
    with temporary_output_dir() as output_dir, monkeypatch.context() as m:
        m.chdir(output_dir)
        app_root = output_dir / "app root"
        app_root.mkdir()
        (app_root / "app.py").write_text("print('hello')\n", encoding="utf-8")
        config_path = output_dir / "litlaunch.toml"
        output_path = output_dir / "custom.bat"
        app_path = str(app_root / "app.py").replace("\\", "\\\\")
        config_path.write_text(
            f"""
[profiles.web]
app_path = "{app_path}"
title = "Web"
""",
            encoding="utf-8",
        )
        stream = StringIO()

        code = main(
            [
                "create",
                "shortcut",
                "--profile",
                "web",
                "--config",
                str(config_path),
                "--output",
                str(output_path),
                "--kind",
                "script",
            ],
            stream=stream,
            platform_detector_factory=FakePlatformDetector,
        )

        assert code == 0
        content = output_path.read_text(encoding="utf-8")
        assert f'"{config_path.resolve()}"' in content


def test_cli_create_shortcut_requires_profile():
    stream = StringIO()

    code = main(["create", "shortcut"], stream=stream)

    assert code == 2
    assert "requires --profile" in stream.getvalue()


def test_cli_create_shortcut_missing_profile_fails_cleanly(monkeypatch):
    with temporary_output_dir() as output_dir, monkeypatch.context() as m:
        m.chdir(output_dir)
        stream = StringIO()

        code = main(
            ["create", "shortcut", "--profile", "missing"],
            stream=stream,
            platform_detector_factory=FakePlatformDetector,
        )

        assert code == 2
        assert "was not found" in stream.getvalue()


def test_cli_console_preview_command_exists_and_exits_zero():
    parser = CLI_MAIN_MODULE.build_console_preview_parser()
    args = parser.parse_args(["console-preview"])
    all_args = parser.parse_args(["console-preview", "--all"])
    normal_args = parser.parse_args(["console-preview", "--normal"])
    verbose_args = parser.parse_args(["console-preview", "--verbose"])

    assert args.command == "console-preview"
    assert args.preview_mode == "all"
    assert callable(args.handler)
    assert all_args.command == "console-preview"
    assert all_args.preview_mode == "all"
    assert callable(all_args.handler)
    assert normal_args.command == "console-preview"
    assert normal_args.preview_mode == "normal"
    assert callable(normal_args.handler)
    assert verbose_args.command == "console-preview"
    assert verbose_args.preview_mode == "verbose"
    assert callable(verbose_args.handler)


def test_cli_console_preview_removes_obsolete_subcommands_and_local_no_color():
    parser = CLI_MAIN_MODULE.build_console_preview_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["console-preview-norm"])
    with pytest.raises(SystemExit):
        parser.parse_args(["console-preview-verb"])
    with pytest.raises(SystemExit):
        parser.parse_args(["console-preview", "--no-color"])


def test_cli_console_preview_outputs_representative_normal_messages():
    stream = StringIO()

    code = main(["console-preview", "--normal"], stream=stream)

    output = strip_ansi(stream.getvalue())
    assert code == 0
    assert "== Normal mode ==" in output
    assert "[   ok   ] LitLaunch Starting runtime..." in output
    assert "== Backend ==" in output
    assert "[   ok   ] Backend: Starting Streamlit..." not in output
    assert "[   ok   ] Backend: Started Streamlit in 0.3s." in output
    assert "[ error  ] Backend: Startup failed." in output
    assert "Backend PID: 12345" not in output
    assert "[   ok   ] Health: Waiting for Streamlit..." in output
    assert "[ error  ] Health: Backend did not become healthy before timeout." in output
    assert "Health: Backend did not become healthy before timeout." in output
    assert "[   ok   ] Browser: Opening Microsoft Edge app window..." not in output
    assert "[ error  ] Browser: Launch failed; stopping backend." in output
    assert "[  warn  ] Browser: Microsoft Edge unavailable." in output
    assert "[  next  ] Using Chrome app-mode instead." in output
    assert "[  next  ] Use --browser to select a different browser." in output
    assert "Runtime: Ready locally at http://127.0.0.1:8501" in output
    assert "[   ok   ] Monitor: Watching app window..." in output
    assert "[ error  ] Monitor: Window monitoring is unavailable." in output
    assert "Monitor: Timed out before app window was observed." in output
    assert "[   ok   ] Shutdown: Requesting app cleanup..." not in output
    assert "[   ok   ] Shutdown: app cleanup request accepted." not in output
    assert "Stopping backend: terminating owned backend process" not in output
    assert "Stopping backend:" not in output
    assert "Runtime launch failed." not in output
    assert "Monitor: Window monitoring failed." in output
    assert "[   ok   ] Hook: Closing database connections..." in output
    assert "[   ok   ] Hook: Closed database connections." in output
    assert "[   ok   ] Hook: Saving app state..." in output
    assert "[ error  ] Hook: Saving app state failed." in output
    assert "Shutdown: Using backend termination fallback." in output
    assert "[   ok   ] Backend: Port 8501 released." in output
    assert "Backend: Exited with code 1." in output
    assert "exited with code 0" not in output
    assert "Likely cause" not in output
    assert "[ cause  ] " in output
    assert "[  next  ] " in output
    assert "[   ok   ] cause " not in output
    assert "[   ok   ] next " not in output
    assert "Run the app directly with streamlit run to see the traceback." not in output
    assert "cause:" not in output
    assert "next:" not in output


def test_cli_console_preview_verbose_keeps_detailed_guidance():
    stream = StringIO()

    code = main(["console-preview", "--verbose"], stream=stream)

    output = strip_ansi(stream.getvalue())
    assert code == 0
    assert "== Verbose mode ==" in output
    assert "[   ok   ] Backend: Starting Streamlit..." in output
    assert "[   ok   ] Browser: Opening Microsoft Edge app window..." in output
    assert "[   ok   ] Shutdown: Requested." in output
    assert "[   ok   ] Shutdown: Requesting app cleanup..." in output
    assert "[   ok   ] Shutdown: App cleanup request accepted." in output
    assert "Backend PID: 12345" in output
    assert "Run the app directly with streamlit run to see the traceback." in output
    assert 'Run "litlaunch inspect" for local diagnostics.' in output
    assert "Stopping backend:" not in output
    assert "[  warn  ] Backend: Terminating owned process." in output
    assert "- Failure detail: disk write failed" in output


def test_cli_console_preview_all_shows_normal_and_verbose_modes():
    stream = StringIO()

    code = main(["console-preview", "--all"], stream=stream)

    output = strip_ansi(stream.getvalue())
    assert code == 0
    assert "== Normal mode ==" in output
    assert "== Verbose mode ==" in output


def test_cli_console_preview_status_labels_are_fixed_width():
    stream = StringIO()

    code = main(["console-preview", "--normal"], stream=stream)

    assert code == 0
    labels = re.findall(
        r"^\[[^\]]+\]",
        strip_ansi(stream.getvalue()),
        flags=re.MULTILINE,
    )
    assert {
        "[   ok   ]",
        "[  warn  ]",
        "[ error  ]",
        "[ cause  ]",
        "[  next  ]",
    } <= set(labels)
    assert {len(label) for label in labels} == {10}


def test_cli_console_preview_defaults_to_all_and_respects_no_color_env():
    color_stream = StringIO()
    plain_stream = StringIO()

    color_code = main(["console-preview"], stream=color_stream, env={})
    plain_code = main(["console-preview"], stream=plain_stream, env={"NO_COLOR": "1"})

    assert color_code == 0
    assert plain_code == 0
    assert "== Normal mode ==" in strip_ansi(color_stream.getvalue())
    assert "== Verbose mode ==" in strip_ansi(color_stream.getvalue())
    assert "\033[" in color_stream.getvalue()
    assert "\033[" not in plain_stream.getvalue()
    assert strip_ansi(color_stream.getvalue()) == plain_stream.getvalue()


def test_cli_console_preview_respects_global_no_color_flag():
    stream = StringIO()

    code = main(["--no-color", "console-preview", "--normal"], stream=stream, env={})

    assert code == 0
    assert "\033[" not in stream.getvalue()


def test_cli_console_preview_does_not_call_runtime_factories():
    def fail_factory(*args, **kwargs):
        raise AssertionError("console-preview should not touch runtime factories")

    stream = StringIO()

    code = main(
        ["console-preview", "--normal"],
        stream=stream,
        env={"NO_COLOR": "1"},
        platform_detector_factory=fail_factory,
        browser_registry_factory=fail_factory,
        launcher_factory=fail_factory,
        diagnostic_collector_factory=fail_factory,
        window_monitor_factory=fail_factory,
    )

    assert code == 0
    assert "[   ok   ] LitLaunch Starting runtime..." in stream.getvalue()


def test_cli_version_returns_zero_and_prints_version():
    stream = StringIO()

    code = main(["version"], stream=stream)

    assert code == 0
    assert f"LitLaunch {__version__}" in stream.getvalue()


def test_cli_platform_outputs_summary_and_verbose_details():
    stream = StringIO()

    code = main(
        ["platform", "--verbose", "--no-color"],
        stream=stream,
        platform_detector_factory=FakePlatformDetector,
    )

    output = stream.getvalue()
    assert code == 0
    assert "Windows x64 / Python 3.14.5" in output
    assert "[   ok   ] Platform: Chromium app mode supported." in output
    assert "[   ok   ] Platform: default browser open supported." in output
    assert "[   ok   ] Platform: window monitoring supported." in output
    assert "[  info  ] OS: windows." in output
    assert "[  info  ] Python executable: X:/Python/python.exe." in output
    assert (
        "[  info  ] Note: Window monitoring capability is currently Windows-first."
        in output
    )
    assert "supports_chromium_app_mode: True" not in output
    assert "is_linux: False" not in output
    assert "notes: (" not in output


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
    assert "[   ok   ] Browser: Edge available; app-mode supported." in output
    assert "[  warn  ] Browser: Chrome unavailable; app-mode supported." in output
    assert "[   ok   ] Browser: Selected Edge for app-mode." in output
    assert ">" not in output
    assert "Auto app-mode strategy" not in output
    assert registry.detect_calls
    assert "\033[" not in output


def test_cli_browsers_verbose_outputs_readable_metadata():
    stream = StringIO()
    registry = FakeBrowserRegistry()

    code = main(
        ["browsers", "--verbose", "--no-color"],
        stream=stream,
        platform_detector_factory=FakePlatformDetector,
        browser_registry_factory=lambda: registry,
    )

    output = stream.getvalue()
    assert code == 0
    assert "[  info  ] Kind: edge." in output
    assert "[  info  ] Executable: C:/Edge/msedge.exe." in output
    assert "[  info  ] Kind: chrome." in output
    assert "[  info  ] Executable: not reported." in output
    assert "- kind:" not in output
    assert "executable_path:" not in output


def test_cli_inspect_without_format_outputs_guidance_without_collecting():
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

    output = stream.getvalue()
    assert code == 0
    assert "Inspect reports are available as HTML, JSON, or support bundle." in output
    assert "litlaunch report" in output
    assert "litlaunch inspect --json" in output
    assert "litlaunch inspect --bundle" in output
    assert FakeDiagnosticCollector.instances == []


def test_cli_inspect_no_auto_port_maps_to_false():
    code, _output, collector = run_fake_inspect(
        ["inspect", str(EXAMPLE_APP), "--json", "--port", "8600", "--no-auto-port"]
    )

    assert code == 0
    assert collector.collect_calls[0]["port"] == 8600
    assert collector.collect_calls[0]["auto_port"] is False


def test_cli_inspect_trust_mode_maps_to_diagnostics():
    code, _output, collector = run_fake_inspect(
        [
            "inspect",
            str(EXAMPLE_APP),
            "--json",
            "--trust-mode",
            "internal_network",
        ]
    )

    assert code == 0
    assert collector.collect_calls[0]["trust_mode"] == "internal_network"


def test_cli_inspect_returns_nonzero_for_report_errors():
    code, output, _collector = run_fake_inspect(["inspect", "missing.py", "--json"])

    assert code == 1
    assert '"status": "error"' in output
    assert "missing.py does not exist;" in output
    assert "abc123shutdown" not in output


def test_cli_inspect_json_returns_parseable_json():
    code, output, collector = run_fake_inspect(["inspect", "--json"])
    data = json.loads(output)

    assert code == 0
    assert data["title"] == "LitLaunch Inspect"
    assert data["schema_version"] == 1
    assert data["generated_by"] == "litlaunch"
    assert data["litlaunch_version"] == "0.91.44b0"
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


def test_cli_inspect_html_returns_sanitized_html():
    code, output, collector = run_fake_inspect(["inspect", "--html", "--quiet"])

    assert code == 0
    assert output.startswith("<!doctype html>")
    assert "<html" in output
    assert "LitLaunch Inspect" in output
    assert "This report is sanitized" in output
    assert collector.collect_calls[0]["app_path"] is None
    assert "\033[" not in output


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


def test_cli_inspect_html_output_writes_file():
    with temporary_output_dir() as output_dir:
        output_path = output_dir / "litlaunch-report.html"
        code, output, _collector = run_fake_inspect(
            ["inspect", "--html", "--output", str(output_path)]
        )
        content = output_path.read_text(encoding="utf-8")

    assert code == 0
    assert content.startswith("<!doctype html>")
    assert "LitLaunch Inspect" in content
    assert "This report is sanitized" in content
    assert output.startswith("Wrote inspect report to ")


def test_cli_report_writes_default_html_report(monkeypatch):
    with temporary_output_dir() as output_dir:
        cwd = Path.cwd()
        monkeypatch.chdir(output_dir)
        output_path = output_dir / ".litlaunch" / "reports" / "litlaunch-report.html"
        stream = StringIO()
        try:
            code = main(
                ["report", "--no-color"],
                stream=stream,
                diagnostic_collector_factory=FakeDiagnosticCollector,
                platform_detector_factory=FakePlatformDetector,
                browser_registry_factory=FakeBrowserRegistry,
                env={"NO_COLOR": "1"},
            )
            content = output_path.read_text(encoding="utf-8")
        finally:
            monkeypatch.chdir(cwd)

    assert code == 0
    assert content.startswith("<!doctype html>")
    assert "LitLaunch Inspect" in content
    output = stream.getvalue()
    assert "Report: wrote HTML diagnostics report to" in output
    assert ".litlaunch" in output
    assert "litlaunch-report.html" in output


def test_cli_report_custom_output_and_force():
    with temporary_output_dir() as output_dir:
        output_path = output_dir / "custom-report.html"
        output_path.write_text("existing", encoding="utf-8")
        blocked_stream = StringIO()
        blocked_code = main(
            ["report", "--output", str(output_path), "--no-color"],
            stream=blocked_stream,
            diagnostic_collector_factory=FakeDiagnosticCollector,
            platform_detector_factory=FakePlatformDetector,
            browser_registry_factory=FakeBrowserRegistry,
        )
        forced_stream = StringIO()
        forced_code = main(
            ["report", "--output", str(output_path), "--force", "--no-color"],
            stream=forced_stream,
            diagnostic_collector_factory=FakeDiagnosticCollector,
            platform_detector_factory=FakePlatformDetector,
            browser_registry_factory=FakeBrowserRegistry,
        )
        content = output_path.read_text(encoding="utf-8")

    assert blocked_code == 2
    assert "already exists" in blocked_stream.getvalue()
    assert forced_code == 0
    assert content.startswith("<!doctype html>")
    assert "Report: wrote HTML diagnostics report to" in forced_stream.getvalue()


def test_cli_report_profile_passes_profile_values():
    with temporary_output_dir() as output_dir:
        app = output_dir / "app.py"
        app.write_text("print('hello')\n", encoding="utf-8")
        config_path = output_dir / "litlaunch.toml"
        output_path = output_dir / "profile-report.html"
        config_path.write_text(
            """
[profiles.web]
app_path = "app.py"
title = "Profile App"
mode = "webapp"
browser = "edge"
trust_mode = "internal_network"
port = 8501
auto_port = false
""",
            encoding="utf-8",
        )

        code, _output, collector = run_fake_inspect(
            [
                "report",
                "--config",
                str(config_path),
                "--profile",
                "web",
                "--output",
                str(output_path),
            ]
        )

    call = collector.collect_calls[0]
    assert code == 0
    assert call["app_path"] == app
    assert call["profile_name"] == "web"
    assert call["mode"] == LaunchMode.WEBAPP
    assert call["browser"] == BrowserChoice.EDGE
    assert call["port"] == 8501
    assert call["auto_port"] is False


def test_cli_report_passes_streamlit_flags_for_tls_diagnostics():
    with temporary_output_dir() as output_dir:
        output_path = output_dir / "tls-report.html"
        code, _output, collector = run_fake_inspect(
            [
                "report",
                "--output",
                str(output_path),
                "--streamlit-flag",
                "server.sslCertFile=cert.pem",
                "--streamlit-flag",
                "server.sslKeyFile=key.pem",
            ]
        )

    call = collector.collect_calls[0]
    assert code == 0
    assert call["streamlit_flags"] == {
        "server.sslCertFile": "cert.pem",
        "server.sslKeyFile": "key.pem",
    }


def test_cli_report_open_warns_without_failing(monkeypatch):
    with temporary_output_dir() as output_dir:
        output_path = output_dir / "litlaunch-report.html"
        stream = StringIO()
        calls = []

        def fake_open(path, *, console):
            calls.append((path, console))
            console.warning("Report: could not open generated report.")
            return False

        monkeypatch.setattr(CLI_INSPECT_MODULE, "open_report_path", fake_open)

        code = main(
            ["report", "--output", str(output_path), "--open", "--no-color"],
            stream=stream,
            diagnostic_collector_factory=FakeDiagnosticCollector,
            platform_detector_factory=FakePlatformDetector,
            browser_registry_factory=FakeBrowserRegistry,
        )

    assert code == 0
    assert calls and calls[0][0] == output_path
    assert "Report: could not open generated report." in stream.getvalue()


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
    assert "--output requires --json, --bundle, or --html" in output


def test_cli_inspect_output_help_mentions_html_bundle_and_json():
    parser = build_parser()
    stream = StringIO()

    inspect_parser = next(
        action.choices["inspect"]
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    inspect_parser.print_help(stream)
    inspect_help = stream.getvalue()
    assert "Write inspect output to a UTF-8 file" in inspect_help
    assert "Supports JSON," in inspect_help
    assert "HTML, and bundle output" in inspect_help


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
            "--trust-mode",
            "strict_local",
            "--no-browser-fallback",
            "--no-monitor-window",
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
    assert launcher.config.trust_mode == TrustMode.STRICT_LOCAL
    assert launcher.config.streamlit_flags["server.maxUploadSize"] == "20"
    assert launcher.config.app_args == ("dataset.json",)
    assert launcher.config.streamlit_args == ()
    assert launcher.console_renderer is not None
    assert session.wait_calls == 1
    output = stream.getvalue()
    assert "Runtime active at http://127.0.0.1:8501" not in output
    assert "No monitor mode requires manual stop." in output
    assert "Press Ctrl+C to stop this session." in output


def test_cli_root_app_path_shorthand_uses_run_pipeline():
    stream = StringIO()
    session = FakeSession(ok=True, wait_return=0)

    code = main(
        [
            str(EXAMPLE_APP),
            "--mode",
            "webapp",
            "--browser",
            "edge",
            "--port",
            "8600",
            "--no-monitor-window",
        ],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
    )

    launcher = FakeLauncher.instances[0]
    assert code == 0
    assert launcher.config.app_path == EXAMPLE_APP
    assert launcher.config.mode == LaunchMode.WEBAPP
    assert launcher.config.browser == BrowserChoice.EDGE
    assert launcher.config.port == 8600
    assert launcher.run_calls == 1
    assert session.wait_calls == 1


def test_cli_root_profile_shorthand_uses_profile_runtime_path():
    with temporary_output_dir() as output_dir:
        app = output_dir / "app.py"
        app.write_text("print('hello')\n", encoding="utf-8")
        config_path = output_dir / "litlaunch.toml"
        config_path.write_text(
            """
[profiles.web]
app_path = "app.py"
title = "Profile App"
mode = "browser"
port = 8501
""",
            encoding="utf-8",
        )
        stream = StringIO()
        session = FakeSession(ok=True, wait_return=0)

        code = main(
            ["--config", str(config_path), "--profile", "web", "--port", "8502"],
            stream=stream,
            launcher_factory=reset_fake_launcher(session),
            platform_detector_factory=FakePlatformDetector,
            window_monitor_factory=lambda platform_info: FakeCliMonitor(),
        )

    launcher = FakeLauncher.instances[0]
    assert code == 0
    assert launcher.config.app_path == app
    assert launcher.config.title == "Profile App"
    assert launcher.config.port == 8502
    assert launcher.run_calls == 1
    assert session.wait_calls == 1


def test_cli_root_shorthand_supports_dry_run_and_passthrough_args():
    stream = StringIO()
    session = FakeSession(ok=True)

    code = main(
        [
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
    assert "--server.runOnSave true -- --workspace demo" in output


def test_cli_bare_profile_name_is_not_root_shorthand():
    assert CLI_MAIN_MODULE._normalize_launch_shorthand(["rolethread-webapp"]) == [
        "rolethread-webapp"
    ]


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


def test_cli_command_loads_profile_and_cli_overrides_port():
    with temporary_output_dir() as output_dir:
        app = output_dir / "app.py"
        app.write_text("print('hello')\n", encoding="utf-8")
        config_path = output_dir / "litlaunch.toml"
        config_path.write_text(
            """
[profiles.web]
app_path = "app.py"
title = "Profile App"
mode = "webapp"
browser = "edge"
trust_mode = "internal_network"
port = 8501
auto_port = false
headless = true
streamlit_args = ["--server.runOnSave", "true"]
app_args = ["--workspace", "demo"]
""",
            encoding="utf-8",
        )
        stream = StringIO()

        code = main(
            [
                "command",
                "--config",
                str(config_path),
                "--profile",
                "web",
                "--port",
                "8502",
            ],
            stream=stream,
            launcher_factory=reset_fake_launcher(FakeSession(ok=True)),
        )

    launcher = FakeLauncher.instances[0]
    assert code == 0
    assert launcher.config.app_path == app
    assert launcher.config.title == "Profile App"
    assert launcher.config.mode == LaunchMode.WEBAPP
    assert launcher.config.browser == BrowserChoice.EDGE
    assert launcher.config.trust_mode == TrustMode.INTERNAL_NETWORK
    assert launcher.config.port == 8502
    assert launcher.config.auto_port is False
    assert launcher.config.streamlit_args == ("--server.runOnSave", "true")
    assert launcher.config.app_args == ("--workspace", "demo")
    assert "--server.port 8502" in stream.getvalue()


def test_cli_run_profile_uses_monitor_runtime_settings():
    with temporary_output_dir() as output_dir:
        app = output_dir / "app.py"
        app.write_text("print('hello')\n", encoding="utf-8")
        config_path = output_dir / "litlaunch.toml"
        config_path.write_text(
            """
[profiles.web]
app_path = "app.py"
title = "Profile App"
mode = "webapp"
headless = true
graceful_timeout = 12

[profiles.web.window_monitor]
enabled = true
appear_timeout = 22
poll_interval = 0.5
stable_polls = 3
""",
            encoding="utf-8",
        )
        stream = StringIO()
        session = FakeSession(ok=True)
        monitor = FakeCliMonitor()

        code = main(
            ["run", "--config", str(config_path), "--profile", "web"],
            stream=stream,
            launcher_factory=reset_fake_launcher(session),
            platform_detector_factory=FakePlatformDetector,
            window_monitor_factory=lambda platform_info: monitor,
        )

    monitor_config = session.monitor_calls[0][2]["config"]
    assert code == 0
    assert FakeLauncher.instances[0].config.title == "Profile App"
    assert session.monitor_calls[0][1].title == "Profile App"
    assert session.monitor_calls[0][2]["graceful_timeout_seconds"] == 12.0
    assert monitor_config.appear_timeout_seconds == 22.0
    assert monitor_config.poll_interval_seconds == 0.5
    assert monitor_config.stable_poll_count == 3


def test_cli_run_profile_without_monitor_uses_normal_runtime_path():
    with temporary_output_dir() as output_dir:
        app = output_dir / "app.py"
        app.write_text("print('hello')\n", encoding="utf-8")
        config_path = output_dir / "litlaunch.toml"
        config_path.write_text(
            """
[profiles.browser]
app_path = "app.py"
title = "Profile Browser"
mode = "browser"
""",
            encoding="utf-8",
        )
        stream = StringIO()
        session = FakeSession(ok=True, wait_return=7)

        code = main(
            ["run", "--config", str(config_path), "--profile", "browser"],
            stream=stream,
            launcher_factory=reset_fake_launcher(session),
            platform_detector_factory=FakePlatformDetector,
            window_monitor_factory=lambda platform_info: FakeCliMonitor(),
        )

    assert code == 7
    assert FakeLauncher.instances[0].config.title == "Profile Browser"
    assert FakeLauncher.instances[0].run_calls == 1
    assert session.wait_calls == 1
    assert session.monitor_calls == []


def test_cli_inspect_profile_passes_profile_values_without_launching():
    with temporary_output_dir() as output_dir:
        app = output_dir / "app.py"
        app.write_text("print('hello')\n", encoding="utf-8")
        config_path = output_dir / "pyproject.toml"
        config_path.write_text(
            """
[tool.litlaunch.profiles.default]
app_path = "app.py"
title = "Profile App"
mode = "webapp"
browser = "chrome"
port = 8501
auto_port = false
allow_browser_fallback = false
headless = true
streamlit_args = ["--theme.base=dark"]
""",
            encoding="utf-8",
        )

        code, _output, collector = run_fake_inspect(
            [
                "inspect",
                "--config",
                str(config_path),
                "--profile",
                "default",
                "--json",
            ]
        )

    call = collector.collect_calls[0]
    assert code == 0
    assert call["app_path"] == app
    assert call["mode"] == LaunchMode.WEBAPP
    assert call["browser"] == BrowserChoice.CHROME
    assert call["port"] == 8501
    assert call["auto_port"] is False
    assert call["allow_browser_fallback"] is False
    assert call["streamlit_args"] == ("--theme.base=dark",)
    assert call["profile_name"] == "default"
    assert call["monitor_window"] is False


def test_cli_config_requires_profile():
    stream = StringIO()

    code = main(
        ["command", "--config", "litlaunch.toml"],
        stream=stream,
        launcher_factory=reset_fake_launcher(FakeSession(ok=True)),
    )

    assert code == 2
    assert "--config requires --profile" in stream.getvalue()


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
    assert "App path does not exist" in stream.getvalue()


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
    plain_output = strip_ansi(output)
    assert code == 0
    assert launcher.run_calls == 0
    assert launcher.config.streamlit_args == ("--server.runOnSave", "true")
    assert launcher.config.app_args == ("--workspace", "demo")
    assert "Runtime: Dry run; backend and browser were not started." in plain_output
    assert "Runtime: App URL: http://127.0.0.1:8600" in plain_output
    assert "Runtime: Mode: browser" in plain_output
    assert "Browser: Selected default browser." in plain_output
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
    assert "Runtime: Interrupt received; stopping runtime." in strip_ansi(
        stream.getvalue()
    )


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


def test_cli_run_webapp_monitors_window_by_default():
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
        ["run", str(EXAMPLE_APP), "--mode", "webapp"],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
        platform_detector_factory=FakePlatformDetector,
        window_monitor_factory=lambda platform_info: monitor,
    )

    assert code == 0
    assert session.wait_calls == 0
    assert session.stop_calls == 1
    assert session.monitor_calls[0][0] is monitor
    assert "Window closed; requesting shutdown" in stream.getvalue()
    assert "Runtime active at http://127.0.0.1:8501" not in stream.getvalue()
    assert "Press Ctrl+C to stop this session." not in stream.getvalue()


def test_cli_run_webapp_no_monitor_window_opt_out_waits_for_backend():
    stream = StringIO()
    session = FakeSession(ok=True, wait_return=0)

    code = main(
        ["run", str(EXAMPLE_APP), "--mode", "webapp", "--no-monitor-window"],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
        platform_detector_factory=FakePlatformDetector,
        window_monitor_factory=lambda platform_info: FakeCliMonitor(),
    )

    assert code == 0
    assert session.wait_calls == 1
    assert session.monitor_calls == []
    output = stream.getvalue()
    assert "Runtime active at http://127.0.0.1:8501" not in output
    assert "No monitor mode requires manual stop." in output
    assert "Press Ctrl+C to stop this session." in output


def test_cli_run_webapp_default_monitoring_skips_unsupported_platform():
    stream = StringIO()
    session = FakeSession(ok=True, wait_return=0)

    code = main(
        ["run", str(EXAMPLE_APP), "--mode", "webapp"],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
        platform_detector_factory=FakeUnsupportedWindowMonitorPlatformDetector,
        window_monitor_factory=lambda platform_info: NoopWindowMonitor(),
    )

    assert code == 0
    assert session.wait_calls == 1
    assert session.monitor_calls == []


def test_cli_run_browser_mode_attempts_browser_window_monitor_by_default():
    stream = StringIO()
    session = FakeSession(ok=True, wait_return=0)
    monitor = FakeCliMonitor()

    code = main(
        ["run", str(EXAMPLE_APP)],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
        platform_detector_factory=FakePlatformDetector,
        window_monitor_factory=lambda platform_info: monitor,
    )

    assert code == 0
    assert session.wait_calls == 1
    assert session.monitor_calls == []
    assert monitor.capture_calls
    assert FakeLauncher.instances[0].config.browser == BrowserChoice.EDGE
    browser_args = FakeLauncher.instances[0].config.extra_browser_args
    assert "--new-window" in browser_args
    assert "--no-first-run" in browser_args
    assert "--disable-first-run-ui" in browser_args
    assert "--no-default-browser-check" in browser_args
    assert "--disable-default-browser-promo" in browser_args
    assert "--disable-default-apps" in browser_args
    assert "--disable-sync" in browser_args
    assert "--disable-background-networking" in browser_args
    assert "--disable-component-update" in browser_args
    assert "--disable-features=msEdgeEnableNurturingFramework" in browser_args
    assert "--window-name=LitLaunch - Streamlit App" in browser_args
    user_data_arg = next(
        arg for arg in browser_args if arg.startswith("--user-data-dir=")
    )
    user_data_path = Path(user_data_arg.split("=", 1)[1])
    assert ".litlaunch" in user_data_path.parts
    assert "browser-profiles" in user_data_path.parts
    assert not user_data_path.exists()


def test_cli_run_default_browser_uses_detected_chromium_for_browser_monitor(
    monkeypatch,
):
    monkeypatch.setattr(
        CLI_COMMANDS_MODULE,
        "detect_default_chromium_browser",
        lambda platform_info: BrowserKind.EDGE,
    )
    stream = StringIO()
    session = FakeSession(ok=True, wait_return=0)
    monitor = FakeCliMonitor()

    code = main(
        ["run", str(EXAMPLE_APP), "--browser", "default"],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
        platform_detector_factory=FakePlatformDetector,
        window_monitor_factory=lambda platform_info: monitor,
    )

    assert code == 0
    assert session.wait_calls == 1
    launcher = FakeLauncher.instances[0]
    assert launcher.config.browser == BrowserChoice.EDGE
    browser_args = launcher.config.extra_browser_args
    assert "--new-window" in browser_args
    assert any(arg.startswith("--user-data-dir=") for arg in browser_args)


def test_cli_run_browser_mode_hidden_monitor_opt_out_preserves_plain_wait():
    stream = StringIO()
    session = FakeSession(ok=True, wait_return=0)
    monitor = FakeCliMonitor()

    code = main(
        [
            "run",
            str(EXAMPLE_APP),
            "--no-monitor-browser-window",
        ],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
        platform_detector_factory=FakePlatformDetector,
        window_monitor_factory=lambda platform_info: monitor,
    )

    assert code == 0
    assert session.wait_calls == 1
    assert session.monitor_calls == []
    assert monitor.capture_calls == []
    assert FakeLauncher.instances[0].config.browser == BrowserChoice.AUTO


def test_cli_run_browser_window_monitor_stops_on_window_close():
    stream = StringIO()
    session = FakeSession(ok=True)
    old = WindowInfo("old", title="Other - Microsoft Edge", process_name="msedge")
    new = WindowInfo(
        "new", title="Streamlit App - Microsoft Edge", process_name="msedge"
    )
    monitor = SequenceCliMonitor(((old,), (old, new), (old, new), (old,)))

    code = main(
        [
            "run",
            str(EXAMPLE_APP),
            "--mode",
            "browser",
            "--browser",
            "edge",
            "--browser-arg=--new-window",
            "--monitor-browser-window",
            "--monitor-appear-timeout",
            "0.01",
            "--monitor-poll-interval",
            "0.001",
        ],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
        platform_detector_factory=FakePlatformDetector,
        window_monitor_factory=lambda platform_info: monitor,
    )

    output = strip_ansi(stream.getvalue())
    assert code == 0
    assert session.stop_calls == 1
    assert session.wait_calls == 0
    assert "--new-window" in FakeLauncher.instances[0].config.extra_browser_args
    assert "Monitor: Scanning for browser instance" in output
    assert "Monitor: Success! Tracking browser window" in output
    assert "Monitor: Browser window closed; requesting shutdown." in output


def test_cli_run_browser_window_monitor_falls_back_without_hwnd():
    stream = StringIO()
    session = FakeSession(ok=True, wait_return=0)
    old = WindowInfo("old", title="Other - Microsoft Edge", process_name="msedge")
    monitor = SequenceCliMonitor(((old,), (old,), (old,)))

    code = main(
        [
            "run",
            str(EXAMPLE_APP),
            "--mode",
            "browser",
            "--browser",
            "edge",
            "--monitor-browser-window",
            "--monitor-appear-timeout",
            "0.01",
            "--monitor-poll-interval",
            "0.001",
        ],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
        platform_detector_factory=FakePlatformDetector,
        window_monitor_factory=lambda platform_info: monitor,
    )

    output = stream.getvalue()
    assert code == 0
    assert session.stop_calls == 0
    assert session.wait_calls == 1
    assert "No new browser window was observed" in output
    assert "Press Ctrl+C to stop this session." in output


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
    monitor_config = session.monitor_calls[0][2]["config"]
    assert monitor_config.appear_timeout_seconds == 60.0
    assert monitor_config.poll_interval_seconds == 1.0
    assert monitor_config.stable_poll_count == 2
    assert monitor.capture_calls[0].title == "Streamlit App"
    assert session.monitor_calls[0][1].title == "Streamlit App"
    assert session.monitor_calls[0][1].app_mode is True
    assert "Window closed; requesting shutdown" in output


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


def test_cli_run_monitor_window_passes_custom_monitor_config():
    stream = StringIO()
    session = FakeSession(ok=True)

    code = main(
        [
            "run",
            str(EXAMPLE_APP),
            "--mode",
            "webapp",
            "--monitor-window",
            "--monitor-appear-timeout",
            "12.5",
            "--monitor-poll-interval",
            "0.25",
            "--monitor-stable-polls",
            "3",
        ],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
        platform_detector_factory=FakePlatformDetector,
        window_monitor_factory=lambda platform_info: FakeCliMonitor(),
    )

    monitor_config = session.monitor_calls[0][2]["config"]
    assert code == 0
    assert monitor_config.appear_timeout_seconds == 12.5
    assert monitor_config.poll_interval_seconds == 0.25
    assert monitor_config.stable_poll_count == 3


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


def test_cli_run_rejects_invalid_monitor_tuning():
    invalid_cases = (
        ("--monitor-appear-timeout", "0", "--monitor-appear-timeout must be positive"),
        ("--monitor-poll-interval", "0", "--monitor-poll-interval must be positive"),
        ("--monitor-stable-polls", "0", "--monitor-stable-polls must be at least 1"),
    )
    for flag, value, message in invalid_cases:
        stream = StringIO()

        code = main(
            [
                "run",
                str(EXAMPLE_APP),
                "--mode",
                "webapp",
                "--monitor-window",
                flag,
                value,
            ],
            stream=stream,
            launcher_factory=reset_fake_launcher(FakeSession(ok=True)),
        )

        assert code == 2
        assert message in stream.getvalue()


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
        [
            "run",
            str(EXAMPLE_APP),
            "--mode",
            "webapp",
            "--monitor-window",
            "--graceful-timeout",
            "9.5",
        ],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
        platform_detector_factory=FakePlatformDetector,
        window_monitor_factory=lambda platform_info: FakeCliMonitor(),
    )

    assert code == 1
    assert session.stop_calls == 1
    assert session.stop_args == [((), {"graceful_timeout_seconds": 9.5})]
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
    assert "Monitor: Window monitoring is unavailable" in strip_ansi(stream.getvalue())
    assert "Use verbose mode for more runtime details." in stream.getvalue()
    assert "Omit --monitor-window" not in stream.getvalue()


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
    assert "Backend exited before monitored window closed" in stream.getvalue()


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
        [
            "run",
            str(EXAMPLE_APP),
            "--mode",
            "webapp",
            "--monitor-window",
            "--graceful-timeout",
            "8.0",
        ],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
        platform_detector_factory=FakePlatformDetector,
        window_monitor_factory=lambda platform_info: FakeCliMonitor(),
    )

    assert code == 1
    assert session.stop_calls == 1
    assert session.stop_args == [((), {"graceful_timeout_seconds": 8.0})]
    assert "timed out" in stream.getvalue()


def test_cli_run_monitor_window_error_uses_configured_graceful_timeout():
    stream = StringIO()
    session = FakeSession(
        ok=True,
        monitor_result=WindowMonitorResult(
            supported=True,
            observed=False,
            closed=False,
            status=WindowMonitorStatus.ERROR,
            message="monitor failed",
        ),
    )

    code = main(
        [
            "run",
            str(EXAMPLE_APP),
            "--mode",
            "webapp",
            "--monitor-window",
            "--graceful-timeout",
            "7.0",
        ],
        stream=stream,
        launcher_factory=reset_fake_launcher(session),
        platform_detector_factory=FakePlatformDetector,
        window_monitor_factory=lambda platform_info: FakeCliMonitor(),
    )

    assert code == 1
    assert session.stop_calls == 1
    assert session.stop_args == [((), {"graceful_timeout_seconds": 7.0})]
    assert "monitor failed" in stream.getvalue()


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
    assert "Press Ctrl+C to stop this session." not in stream.getvalue()


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
        CLI_MAIN_MODULE,
        "source_checkout_example_path",
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
