import json
import os
from io import StringIO
from pathlib import Path

from litlaunch import LauncherConfig, LaunchMode, RuntimeEvent
from litlaunch.artifacts import OWNED_MARKER, cleanup_litlaunch_owned_dir
from litlaunch.backend import BackendCommand, BackendCommandContext
from litlaunch.browsers import (
    BrowserCapability,
    BrowserKind,
    BrowserLaunchResult,
    BrowserResolution,
)
from litlaunch.config import BrowserChoice
from litlaunch.console import ConsoleMode, ConsoleRenderer, ConsoleTheme
from litlaunch.exceptions import CommandBuildError
from litlaunch.health import build_streamlit_app_url, build_streamlit_health_url
from litlaunch.launcher import StreamlitLauncher
from litlaunch.lifecycle import LaunchPlan, LaunchState
from litlaunch.ports import PortError
from litlaunch.process import ManagedProcess
from litlaunch.session import RuntimeSession


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def monotonic(self):
        self.value += 1.0
        return self.value

    def time(self):
        return self.value


class FakePortManager:
    def __init__(self, port):
        self.port = port
        self.calls = []
        self.available_port_calls = []

    def resolve_port(self, config):
        self.calls.append(config)
        return self.port

    def find_available_port(self, host, start_port=8501, max_attempts=100):
        self.available_port_calls.append((host, start_port, max_attempts))
        return start_port

    def is_port_available(self, host, port):
        self.available_port_calls.append((host, port, None))
        return True


class FakePopen:
    pid = 999

    def __init__(self, returncode=None):
        self.returncode = returncode

    def poll(self):
        return self.returncode


class FakeProcessManager:
    def __init__(self, *, process_returncode=None):
        self.started = []
        self.stopped = []
        self.process_returncode = process_returncode

    def start(self, command, **kwargs):
        self.started.append((command, kwargs))
        return ManagedProcess(FakePopen(self.process_returncode), tuple(command))

    def is_running(self, process):
        return process.popen.poll() is None

    def stop(self, process, terminate_timeout_seconds=5.0):
        self.stopped.append((process, terminate_timeout_seconds))


class FakeHealthChecker:
    def __init__(self, healthy):
        self.healthy = healthy
        self.calls = []

    def wait_until_healthy(self, url, timeout_seconds, interval_seconds):
        self.calls.append((url, timeout_seconds, interval_seconds))
        return self.healthy


class FakeBrowserRegistry:
    def __init__(self, selected):
        self.selected = selected
        self.calls = []

    def resolve(self, choice, *, prefer_app_mode, allow_fallback):
        self.calls.append((choice, prefer_app_mode, allow_fallback))
        return BrowserResolution(
            requested=choice,
            selected=self.selected,
            fallback_chain=(self.selected,) if self.selected else (),
            message="browser resolved" if self.selected else "no browser",
        )


class FakeBrowserLauncher:
    def __init__(self, ok=True):
        self.ok = ok
        self.calls = []
        self.artifact_roots = []

    def launch(
        self,
        resolution,
        *,
        url,
        mode,
        title,
        extra_args,
        allow_fallback=True,
        app_icon=None,
        artifact_root=None,
    ):
        self.calls.append((resolution, url, mode, title, extra_args, allow_fallback))
        self.artifact_roots.append(artifact_root)
        command = ("browser", "--app=" + url, *extra_args) if self.ok else ("browser",)
        return BrowserLaunchResult(
            ok=self.ok,
            command=command,
            browser=resolution.selected,
            mode=mode,
            message="browser launched" if self.ok else "browser failed",
        )


class FakeBackendCommandProvider:
    def __init__(
        self,
        command=("packaged-app", "--serve"),
        *,
        description="packaged backend",
        backend_kind="packaged",
    ):
        self.command = command
        self.description = description
        self.backend_kind = backend_kind
        self.contexts = []

    def build_backend_command(self, context: BackendCommandContext):
        self.contexts.append(context)
        return BackendCommand(
            self.command,
            description=self.description,
            backend_kind=self.backend_kind,
        )


class FailingBackendCommandProvider:
    def build_backend_command(self, context):
        raise RuntimeError("provider exploded")


class BadReturnBackendCommandProvider:
    def build_backend_command(self, context):
        return ("not", "a", "backend-command")


def fake_browser(kind=BrowserKind.EDGE):
    return BrowserCapability(
        kind=kind,
        name=kind.value.title(),
        executable_path="browser.exe",
        available=True,
        supports_app_mode=kind != BrowserKind.DEFAULT,
        supports_full_browser=True,
    )


def test_launcher_accepts_app_path_string_with_event_sink():
    events = []
    sink = events.append

    launcher = StreamlitLauncher("app.py", event_sink=sink)

    assert launcher.config == LauncherConfig("app.py")
    assert launcher.event_sink is sink


def test_runtime_event_sink_receives_basic_launch_lifecycle_events():
    events: list[RuntimeEvent] = []
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py"),
        port_manager=FakePortManager(8600),
        process_manager=FakeProcessManager(),
        health_checker=FakeHealthChecker(healthy=True),
        browser_registry=FakeBrowserRegistry(fake_browser()),
        browser_launcher=FakeBrowserLauncher(ok=True),
        event_sink=events.append,
        clock=FakeClock(),
    )

    session = launcher.start()

    assert session.ok is True
    assert [event.name for event in events] == [
        "launch_planned",
        "backend_starting",
        "backend_started",
        "health_ready",
        "browser_launched",
    ]
    assert {event.level for event in events} == {"info"}
    assert events[0].category == "launch"
    assert events[0].timestamp.tzinfo is not None
    assert events[2].details["pid"] == "999"
    assert events[3].details["port"] == "8600"
    assert events[-1].category == "browser"


def test_runtime_event_sink_does_not_receive_raw_env_secrets():
    events: list[RuntimeEvent] = []
    launcher = StreamlitLauncher(
        LauncherConfig(
            app_path="app.py",
            extra_env={"APP_TOKEN": "super-secret-token"},
            streamlit_args=("--server.cookieSecret", "cookie-secret"),
        ),
        port_manager=FakePortManager(8600),
        process_manager=FakeProcessManager(),
        health_checker=FakeHealthChecker(healthy=True),
        browser_registry=FakeBrowserRegistry(fake_browser()),
        browser_launcher=FakeBrowserLauncher(ok=True),
        event_sink=events.append,
        clock=FakeClock(),
    )

    launcher.start()

    rendered = "\n".join(
        line
        for event in events
        for line in (
            event.message,
            *[f"{key}={value}" for key, value in event.details.items()],
        )
    )
    assert "super-secret-token" not in rendered
    assert "cookie-secret" not in rendered


def test_runtime_event_log_file_receives_launch_events_and_composes_sink(
    tmp_path: Path,
):
    app = tmp_path / "app.py"
    app.write_text("print('hello')\n", encoding="utf-8")
    events: list[RuntimeEvent] = []
    launcher = StreamlitLauncher(
        LauncherConfig(
            app_path=app,
            runtime_event_log=".litlaunch/runtime-events.log",
        ),
        port_manager=FakePortManager(8600),
        process_manager=FakeProcessManager(),
        health_checker=FakeHealthChecker(healthy=True),
        browser_registry=FakeBrowserRegistry(fake_browser()),
        browser_launcher=FakeBrowserLauncher(ok=True),
        event_sink=events.append,
        clock=FakeClock(),
    )

    session = launcher.start()

    assert session.ok is True
    assert [event.name for event in events] == [
        "launch_planned",
        "backend_starting",
        "backend_started",
        "health_ready",
        "browser_launched",
    ]
    event_path = tmp_path / ".litlaunch" / "runtime-events.log"
    records = [
        json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["name"] for record in records] == [event.name for event in events]
    assert all("details" in record for record in records)


def test_runtime_event_sink_exception_does_not_break_launch():
    stream = StringIO()
    console = ConsoleRenderer(
        mode=ConsoleMode.VERBOSE,
        stream=stream,
        theme=ConsoleTheme(use_color=False),
    )

    def failing_sink(event):
        raise RuntimeError("sink exploded")

    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py"),
        port_manager=FakePortManager(8600),
        process_manager=FakeProcessManager(),
        health_checker=FakeHealthChecker(healthy=True),
        browser_registry=FakeBrowserRegistry(fake_browser()),
        browser_launcher=FakeBrowserLauncher(ok=True),
        console_renderer=console,
        event_sink=failing_sink,
        clock=FakeClock(),
    )

    session = launcher.start()

    assert session.ok is True
    assert stream.getvalue().count("Runtime:  Event sink failed") == 1


def test_launcher_builds_app_and_health_urls_with_resolved_port():
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py"),
        port_manager=FakePortManager(8600),
    )

    assert launcher.build_app_url() == build_streamlit_app_url("127.0.0.1", 8600)
    assert launcher.build_health_url() == build_streamlit_health_url("127.0.0.1", 8600)


def test_launcher_uses_loopback_client_urls_for_wildcard_bind():
    launcher = StreamlitLauncher(
        LauncherConfig(
            app_path="app.py",
            host="0.0.0.0",
            allow_network_exposure=True,
        ),
        port_manager=FakePortManager(8600),
    )

    assert launcher.build_app_url() == "http://127.0.0.1:8600"
    assert launcher.build_health_url() == "http://127.0.0.1:8600/_stcore/health"


def test_with_port_preserves_injected_dependencies():
    port_manager = FakePortManager(8600)
    process_manager = FakeProcessManager()
    health_checker = FakeHealthChecker(healthy=True)
    browser_registry = FakeBrowserRegistry(fake_browser())
    browser_launcher = FakeBrowserLauncher(ok=True)
    backend_command_provider = FakeBackendCommandProvider()
    console_renderer = ConsoleRenderer()
    clock = FakeClock()
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py"),
        port_manager=port_manager,
        process_manager=process_manager,
        health_checker=health_checker,
        browser_registry=browser_registry,
        browser_launcher=browser_launcher,
        backend_command_provider=backend_command_provider,
        console_renderer=console_renderer,
        clock=clock,
    )

    updated = launcher.with_port(8700)

    assert updated.config.port == 8700
    assert updated.config.auto_port is False
    assert launcher.config.port is None
    assert launcher.config.auto_port is True
    assert updated.config.app_path == launcher.config.app_path
    assert updated.config.mode == launcher.config.mode
    assert updated.port_manager is port_manager
    assert updated.process_manager is process_manager
    assert updated.health_checker is health_checker
    assert updated.browser_registry is browser_registry
    assert updated.browser_launcher is browser_launcher
    assert updated.backend_command_provider is backend_command_provider
    assert updated.console_renderer is console_renderer
    assert updated.clock is clock


def test_start_backend_resolves_port_builds_command_and_waits_for_health():
    process_manager = FakeProcessManager()
    health_checker = FakeHealthChecker(healthy=True)
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py"),
        port_manager=FakePortManager(8600),
        process_manager=process_manager,
        health_checker=health_checker,
        clock=FakeClock(),
    )

    session = launcher.start_backend(
        health_timeout_seconds=3.0,
        health_interval_seconds=0.1,
    )
    result = session.result

    assert isinstance(session, RuntimeSession)
    assert result.ok is True
    assert result.state == LaunchState.HEALTHY
    assert session.pid == 999
    assert session.url == "http://127.0.0.1:8600"
    assert session.command is not None
    assert session.command[session.command.index("--server.port") + 1] == "8600"
    assert session.process is not None
    assert len(process_manager.started) == 1
    assert process_manager.started[0][0] == session.command
    assert process_manager.started[0][1]["env"]["LITLAUNCH_SHUTDOWN_ENABLED"] == "1"
    assert process_manager.started[0][1]["env"]["LITLAUNCH_SHUTDOWN_PORT"] == "8601"
    assert process_manager.stopped == []
    assert health_checker.calls == [("http://127.0.0.1:8600/_stcore/health", 3.0, 0.1)]
    assert [event.state for event in result.events] == [
        LaunchState.CREATED,
        LaunchState.CONFIGURED,
        LaunchState.PORT_READY,
        LaunchState.COMMAND_BUILT,
        LaunchState.PROCESS_STARTING,
        LaunchState.PROCESS_RUNNING,
        LaunchState.HEALTH_CHECKING,
        LaunchState.HEALTHY,
    ]


def test_start_backend_binds_wildcard_but_health_checks_loopback():
    process_manager = FakeProcessManager()
    health_checker = FakeHealthChecker(healthy=True)
    launcher = StreamlitLauncher(
        LauncherConfig(
            app_path="app.py",
            host="0.0.0.0",
            allow_network_exposure=True,
        ),
        port_manager=FakePortManager(8600),
        process_manager=process_manager,
        health_checker=health_checker,
        clock=FakeClock(),
    )

    session = launcher.start_backend(
        health_timeout_seconds=3.0,
        health_interval_seconds=0.1,
    )

    assert session.result.ok is True
    assert session.url == "http://127.0.0.1:8600"
    assert session.command is not None
    assert session.command[session.command.index("--server.address") + 1] == "0.0.0.0"
    assert health_checker.calls == [("http://127.0.0.1:8600/_stcore/health", 3.0, 0.1)]


def test_build_launch_plan_resolves_fixed_port_without_starting_or_launching():
    process_manager = FakeProcessManager()
    browser_launcher = FakeBrowserLauncher(ok=True)
    browser_registry = FakeBrowserRegistry(fake_browser())
    launcher = StreamlitLauncher(
        LauncherConfig(
            app_path="app.py",
            port=8600,
            auto_port=False,
            cwd="workspace",
            extra_env={"APP_TOKEN": "super-secret-token", "APP_MODE": "demo"},
            streamlit_flags={"server.maxUploadSize": 20},
            streamlit_args=("--server.cookieSecret", "secret-value"),
            app_args=("--workspace", "demo"),
        ),
        port_manager=FakePortManager(8600),
        process_manager=process_manager,
        browser_registry=browser_registry,
        browser_launcher=browser_launcher,
    )

    plan = launcher.build_launch_plan()

    assert isinstance(plan, LaunchPlan)
    assert plan.command[1:4] == ("-m", "streamlit", "run")
    assert plan.backend_description == "Streamlit backend"
    assert plan.backend_kind == "streamlit"
    assert "--server.port" in plan.command
    assert plan.command[plan.command.index("--server.port") + 1] == "8600"
    assert plan.command[plan.command.index("--client.toolbarMode") + 1] == "minimal"
    assert plan.command_display
    assert "secret-value" not in plan.command_display
    assert "<redacted>" in plan.command_display
    assert str(plan.cwd) == "workspace"
    assert plan.app_url == "http://127.0.0.1:8600"
    assert plan.health_url == "http://127.0.0.1:8600/_stcore/health"
    assert plan.host == "127.0.0.1"
    assert plan.port == 8600
    assert plan.port_range is None
    assert plan.resolved_port == 8600
    assert plan.auto_port is False
    assert plan.port_selection == "requested/default port available"
    assert plan.mode == LaunchMode.BROWSER
    assert plan.headless is True
    assert plan.streamlit_chrome_policy == "hidden"
    assert plan.streamlit_output_policy == "hidden"
    assert plan.runtime_state_root is not None
    assert "litlaunch" in plan.runtime_state_root.parts
    assert plan.browser_profile_root == plan.runtime_state_root / "browser-profiles"
    assert plan.browser_profile_policy == "external/default browser profile"
    assert plan.browser_profile_cleanup == "not owned by LitLaunch"
    assert plan.browser_requested == BrowserChoice.AUTO
    assert plan.browser_resolution is not None
    assert plan.browser_resolution.selected == fake_browser()
    assert plan.allow_browser_fallback is True
    assert plan.app_args == ("--workspace", "demo")
    assert plan.streamlit_flags == {"server.maxUploadSize": 20}
    assert plan.streamlit_args == ("--server.cookieSecret", "secret-value")
    assert plan.extra_env_preview == "APP_MODE=demo, APP_TOKEN=<redacted>"
    assert process_manager.started == []
    assert browser_launcher.calls == []


def test_build_launch_plan_reports_visible_streamlit_chrome_policy():
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py", show_streamlit_chrome=True),
        port_manager=FakePortManager(8600),
    )

    plan = launcher.build_launch_plan()

    assert plan.streamlit_chrome_policy == "visible"
    assert "--client.toolbarMode" not in plan.command


def test_build_launch_plan_reports_visible_streamlit_output_policy():
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py", show_streamlit_output=True),
        port_manager=FakePortManager(8600),
    )

    plan = launcher.build_launch_plan()

    assert plan.streamlit_output_policy == "visible"
    assert "--browser.gatherUsageStats" not in plan.command


def test_build_launch_plan_reports_auto_port_selection():
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py", port=8501, auto_port=True),
        port_manager=FakePortManager(8502),
    )

    plan = launcher.build_launch_plan()

    assert plan.port == 8501
    assert plan.resolved_port == 8502
    assert plan.port_selection == (
        "auto-port selected 8502 because 8501 was unavailable"
    )
    assert plan.app_url == "http://127.0.0.1:8502"


def test_build_launch_plan_reports_ephemeral_profile_policy_for_webapp(tmp_path: Path):
    state_root = tmp_path / "runtime-state"
    launcher = StreamlitLauncher(
        LauncherConfig(
            app_path="app.py",
            mode="webapp",
            runtime_state_root=state_root,
        ),
        port_manager=FakePortManager(8600),
    )

    plan = launcher.build_launch_plan()

    assert plan.runtime_state_root == state_root
    assert plan.browser_profile_root == state_root / "browser-profiles"
    assert plan.browser_profile_policy == "ephemeral isolated browser profile"
    assert plan.browser_profile_cleanup == "best-effort cleanup after runtime stops"


def test_default_backend_provider_preserves_current_command_output():
    launcher = StreamlitLauncher(
        LauncherConfig(
            app_path="app.py",
            port=8600,
            streamlit_args=("--server.runOnSave", "true"),
            app_args=("--workspace", "demo"),
        ),
        port_manager=FakePortManager(8600),
    )

    plan = launcher.build_launch_plan()

    assert plan.command == launcher.command_builder.build(port=8600)
    assert launcher.build_command() == plan.command


def test_build_launch_plan_uses_custom_backend_provider_without_starting():
    process_manager = FakeProcessManager()
    browser_launcher = FakeBrowserLauncher(ok=True)
    provider = FakeBackendCommandProvider(
        ("packaged-app.exe", "--token", "secret-value", "--port", "8600")
    )
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py", port=8600),
        port_manager=FakePortManager(8600),
        process_manager=process_manager,
        browser_launcher=browser_launcher,
        backend_command_provider=provider,
    )

    plan = launcher.build_launch_plan()

    assert plan.command == (
        "packaged-app.exe",
        "--token",
        "secret-value",
        "--port",
        "8600",
    )
    assert plan.backend_description == "packaged backend"
    assert plan.backend_kind == "packaged"
    assert "secret-value" not in plan.command_display
    assert "<redacted>" in plan.command_display
    assert provider.contexts[0].port == 8600
    assert provider.contexts[0].app_url == "http://127.0.0.1:8600"
    assert provider.contexts[0].health_url == "http://127.0.0.1:8600/_stcore/health"
    assert process_manager.started == []
    assert browser_launcher.calls == []


def test_build_command_uses_custom_backend_provider():
    provider = FakeBackendCommandProvider(("packaged-app.exe", "--serve", "8600"))
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py", port=8600),
        port_manager=FakePortManager(8600),
        backend_command_provider=provider,
    )

    command = launcher.build_command()
    plan = launcher.build_launch_plan(include_browser_resolution=False)

    assert command == ("packaged-app.exe", "--serve", "8600")
    assert command == plan.command
    assert provider.contexts[0].port == 8600


def test_build_command_wraps_provider_errors_as_command_build_error():
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py", port=8600),
        port_manager=FakePortManager(8600),
        backend_command_provider=FailingBackendCommandProvider(),
    )

    try:
        launcher.build_command()
    except CommandBuildError as exc:
        assert "Backend command provider failed: provider exploded" in str(exc)
    else:
        raise AssertionError("expected provider failure to raise CommandBuildError")


def test_build_launch_plan_can_skip_browser_resolution():
    browser_registry = FakeBrowserRegistry(fake_browser())
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py", port=8600),
        port_manager=FakePortManager(8600),
        browser_registry=browser_registry,
    )

    plan = launcher.build_launch_plan(include_browser_resolution=False)

    assert plan.browser_resolution is None
    assert browser_registry.calls == []


def test_build_launch_plan_busy_fixed_port_raises_clear_port_error():
    class BusyPortManager(FakePortManager):
        def resolve_port(self, config):
            raise PortError("Port 8600 is already in use on 127.0.0.1.")

    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py", port=8600, auto_port=False),
        port_manager=BusyPortManager(8600),
    )

    try:
        launcher.build_launch_plan()
    except PortError as exc:
        assert "Port 8600 is already in use" in str(exc)
    else:
        raise AssertionError("expected busy fixed port to raise")


def test_build_launch_plan_wraps_provider_errors_as_command_build_error():
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py", port=8600),
        port_manager=FakePortManager(8600),
        backend_command_provider=FailingBackendCommandProvider(),
    )

    try:
        launcher.build_launch_plan()
    except CommandBuildError as exc:
        assert "Backend command provider failed: provider exploded" in str(exc)
    else:
        raise AssertionError("expected provider failure to raise CommandBuildError")


def test_build_launch_plan_rejects_invalid_provider_return_value():
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py", port=8600),
        port_manager=FakePortManager(8600),
        backend_command_provider=BadReturnBackendCommandProvider(),
    )

    try:
        launcher.build_launch_plan()
    except CommandBuildError as exc:
        assert "must return a BackendCommand" in str(exc)
    else:
        raise AssertionError("expected bad provider return to raise CommandBuildError")


def test_start_backend_reports_provider_errors_clearly():
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py", port=8600),
        port_manager=FakePortManager(8600),
        process_manager=FakeProcessManager(),
        health_checker=FakeHealthChecker(healthy=True),
        backend_command_provider=FailingBackendCommandProvider(),
    )

    session = launcher.start_backend()

    assert session.ok is False
    assert session.command is None
    assert (
        "Backend command provider failed: provider exploded" in session.result.message
    )


def test_start_backend_uses_custom_provider_command_and_litlaunch_runtime_contract(
    monkeypatch,
):
    monkeypatch.setenv("LITLAUNCH_SHUTDOWN_TOKEN", "global-token")
    provider = FakeBackendCommandProvider(("packaged-app.exe", "--port", "8600"))
    process_manager = FakeProcessManager()
    health_checker = FakeHealthChecker(healthy=True)
    launcher = StreamlitLauncher(
        LauncherConfig(
            app_path="app.py",
            port=8600,
            cwd="workspace",
            extra_env={"APP_SECRET": "secret", "LITLAUNCH_SHUTDOWN_TOKEN": "app"},
        ),
        port_manager=FakePortManager(8600),
        process_manager=process_manager,
        health_checker=health_checker,
        backend_command_provider=provider,
        clock=FakeClock(),
    )

    session = launcher.start_backend(health_timeout_seconds=3.0)
    started_command, start_kwargs = process_manager.started[0]
    env = start_kwargs["env"]

    assert session.ok is True
    assert started_command == ("packaged-app.exe", "--port", "8600")
    assert session.command == ("packaged-app.exe", "--port", "8600")
    assert start_kwargs["cwd"] == launcher.config.cwd
    assert env["APP_SECRET"] == "secret"
    assert env["LITLAUNCH_SHUTDOWN_TOKEN"] != "app"
    assert env["LITLAUNCH_SHUTDOWN_TOKEN"] != "global-token"
    assert health_checker.calls == [("http://127.0.0.1:8600/_stcore/health", 3.0, 0.25)]
    assert provider.contexts[0].host == "127.0.0.1"
    assert provider.contexts[0].port == 8600


def test_start_backend_passes_cwd_and_extra_env_without_mutating_global_env(
    monkeypatch,
):
    monkeypatch.setenv("APP_SETTING", "global")
    monkeypatch.setenv("LITLAUNCH_SHUTDOWN_TOKEN", "global-token")
    process_manager = FakeProcessManager()
    launcher = StreamlitLauncher(
        LauncherConfig(
            app_path="app.py",
            cwd="workspace",
            extra_env={
                "APP_SETTING": "child",
                "APP_SECRET": "super-secret",
                "LITLAUNCH_SHUTDOWN_TOKEN": "app-token",
            },
        ),
        port_manager=FakePortManager(8600),
        process_manager=process_manager,
        health_checker=FakeHealthChecker(healthy=True),
        clock=FakeClock(),
    )

    session = launcher.start_backend()
    env = process_manager.started[0][1]["env"]

    assert session.ok is True
    assert process_manager.started[0][1]["cwd"] == launcher.config.cwd
    assert env["APP_SETTING"] == "child"
    assert env["APP_SECRET"] == "super-secret"
    assert env["LITLAUNCH_SHUTDOWN_ENABLED"] == "1"
    assert env["LITLAUNCH_SHUTDOWN_TOKEN"] != "app-token"
    assert env["LITLAUNCH_SHUTDOWN_TOKEN"] != "global-token"
    assert os.environ["APP_SETTING"] == "global"
    assert os.environ["LITLAUNCH_SHUTDOWN_TOKEN"] == "global-token"


def test_verbose_backend_command_detail_redacts_sensitive_values():
    stream = StringIO()
    renderer = ConsoleRenderer(
        mode="verbose",
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )
    launcher = StreamlitLauncher(
        LauncherConfig(
            app_path="app.py",
            streamlit_args=("--server.cookieSecret", "super-secret-token"),
        ),
        port_manager=FakePortManager(8600),
        process_manager=FakeProcessManager(),
        health_checker=FakeHealthChecker(healthy=True),
        console_renderer=renderer,
        clock=FakeClock(),
    )

    launcher.start_backend()
    output = stream.getvalue()

    assert "Command:" in output
    assert "super-secret-token" not in output
    assert "<redacted>" in output


def test_start_backend_stops_owned_process_when_health_fails():
    process_manager = FakeProcessManager()
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py"),
        port_manager=FakePortManager(8601),
        process_manager=process_manager,
        health_checker=FakeHealthChecker(healthy=False),
        clock=FakeClock(),
    )

    session = launcher.start_backend()
    result = session.result

    assert result.ok is False
    assert result.state == LaunchState.FAILED
    assert result.pid == 999
    assert session.process is None
    assert len(process_manager.stopped) == 1
    assert "health check timed out" in result.message
    assert LaunchState.TERMINATING in {event.state for event in result.events}


def test_health_timeout_console_guidance_is_actionable():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )
    process_manager = FakeProcessManager()
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py"),
        port_manager=FakePortManager(8601),
        process_manager=process_manager,
        health_checker=FakeHealthChecker(healthy=False),
        console_renderer=renderer,
        clock=FakeClock(),
    )

    session = launcher.start_backend()

    output = stream.getvalue()
    assert session.ok is False
    assert "Health:   Backend did not become healthy before timeout." in output
    assert "[ cause  ] The app started but did not report ready in time." in output
    assert output.count("[  next  ]") == 1
    assert "Run Streamlit directly to see any app traceback." not in output
    assert 'Run "litlaunch inspect" for local diagnostics.' not in output


def test_start_backend_reports_process_exit_before_health_as_startup_failure():
    process_manager = FakeProcessManager(process_returncode=1)
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py"),
        port_manager=FakePortManager(8601),
        process_manager=process_manager,
        health_checker=FakeHealthChecker(healthy=False),
        clock=FakeClock(),
    )

    session = launcher.start_backend()
    result = session.result

    assert result.ok is False
    assert "exited before becoming healthy" in result.message
    assert "Streamlit is not installed" in result.message
    assert "app crashes during startup" in result.message
    assert len(process_manager.stopped) == 1


def test_backend_early_exit_console_guidance_is_actionable():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py"),
        port_manager=FakePortManager(8601),
        process_manager=FakeProcessManager(process_returncode=1),
        health_checker=FakeHealthChecker(healthy=False),
        console_renderer=renderer,
        clock=FakeClock(),
    )

    session = launcher.start_backend()

    output = stream.getvalue()
    assert session.ok is False
    assert "Backend:  Exited before becoming healthy." in output
    assert (
        "Streamlit may be missing or the app may have crashed during startup." in output
    )
    assert output.count("[  next  ]") == 1
    assert "Verify Streamlit is installed in this Python environment." not in output
    assert "Run the app directly with streamlit run" not in output


def test_backend_failure_verbose_guidance_keeps_detailed_steps():
    stream = StringIO()
    renderer = ConsoleRenderer(
        mode=ConsoleMode.VERBOSE,
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py"),
        port_manager=FakePortManager(8601),
        process_manager=FakeProcessManager(process_returncode=1),
        health_checker=FakeHealthChecker(healthy=False),
        console_renderer=renderer,
        clock=FakeClock(),
    )

    session = launcher.start_backend()

    output = stream.getvalue()
    assert session.ok is False
    assert "Verify Streamlit is installed in this Python environment." in output
    assert "Run the app directly with streamlit run" in output


def test_start_backend_can_skip_health_check():
    process_manager = FakeProcessManager()
    health_checker = FakeHealthChecker(healthy=False)
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py"),
        port_manager=FakePortManager(8602),
        process_manager=process_manager,
        health_checker=health_checker,
        clock=FakeClock(),
    )

    session = launcher.start_backend(wait_for_health=False)
    result = session.result

    assert result.ok is True
    assert result.state == LaunchState.PROCESS_RUNNING
    assert session.process is not None
    assert health_checker.calls == []
    assert process_manager.stopped == []


def test_run_starts_backend_waits_health_resolves_and_launches_browser(
    tmp_path: Path,
):
    app = tmp_path / "app.py"
    app.write_text("print('hello')\n", encoding="utf-8")
    process_manager = FakeProcessManager()
    browser_registry = FakeBrowserRegistry(fake_browser())
    browser_launcher = FakeBrowserLauncher(ok=True)
    launcher = StreamlitLauncher(
        LauncherConfig(app_path=app, mode="webapp", extra_browser_args=["--x"]),
        port_manager=FakePortManager(8603),
        process_manager=process_manager,
        health_checker=FakeHealthChecker(healthy=True),
        browser_registry=browser_registry,
        browser_launcher=browser_launcher,
        clock=FakeClock(),
    )

    session = launcher.run(health_timeout_seconds=2.0, health_interval_seconds=0.2)
    result = session.result

    assert isinstance(session, RuntimeSession)
    assert session.ok is True
    assert result.ok is True
    assert result.state == LaunchState.RUNNING
    assert session.state == LaunchState.RUNNING
    assert session.url == "http://127.0.0.1:8603"
    assert session.pid == 999
    assert session.command is not None
    assert session.command[session.command.index("--server.port") + 1] == "8603"
    assert session.browser is not None
    assert session.browser.kind == BrowserKind.EDGE
    assert session.browser_launched is True
    assert session.browser_command is not None
    assert session.browser_command[:2] == ("browser", "--app=http://127.0.0.1:8603")
    assert session.process is not None
    assert process_manager.started[0][1]["suppress_output"] is True
    assert browser_registry.calls == [(BrowserChoice.AUTO, True, True)]
    extra_args = browser_launcher.calls[0][4]
    profile_arg = next(
        arg for arg in extra_args if str(arg).startswith("--user-data-dir=")
    )
    profile_path = Path(profile_arg.split("=", 1)[1])
    assert browser_launcher.calls[0][2:4] == (LaunchMode.WEBAPP, "Streamlit App")
    assert "--x" in extra_args
    assert "--no-first-run" in extra_args
    assert "--no-default-browser-check" in extra_args
    assert profile_path.exists()
    assert tmp_path not in profile_path.parents
    assert "browser-profiles" in profile_path.parts
    assert (profile_path / OWNED_MARKER).is_file()
    assert browser_launcher.calls[0][-1] is True
    assert browser_launcher.artifact_roots[0] == profile_path.parents[1]
    assert process_manager.stopped == []
    session.stop()
    assert not profile_path.exists()


def test_run_can_show_raw_streamlit_backend_output(tmp_path: Path):
    app = tmp_path / "app.py"
    app.write_text("print('hello')\n", encoding="utf-8")
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )
    process_manager = FakeProcessManager()
    launcher = StreamlitLauncher(
        LauncherConfig(app_path=app, show_streamlit_output=True),
        port_manager=FakePortManager(8603),
        process_manager=process_manager,
        health_checker=FakeHealthChecker(healthy=True),
        browser_registry=FakeBrowserRegistry(fake_browser()),
        browser_launcher=FakeBrowserLauncher(ok=True),
        console_renderer=renderer,
        clock=FakeClock(),
    )

    session = launcher.run()

    assert session.ok is True
    assert process_manager.started[0][1]["suppress_output"] is False
    assert "[   ok   ] Health:   Waiting for Streamlit...\n\n" in stream.getvalue()
    session.stop()


def test_run_auto_port_uses_selected_port_for_browser_url(tmp_path: Path):
    app = tmp_path / "app.py"
    app.write_text("print('hello')\n", encoding="utf-8")
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )
    browser_launcher = FakeBrowserLauncher(ok=True)
    launcher = StreamlitLauncher(
        LauncherConfig(app_path=app, port=8501, auto_port=True, mode="webapp"),
        port_manager=FakePortManager(8502),
        process_manager=FakeProcessManager(),
        health_checker=FakeHealthChecker(healthy=True),
        browser_registry=FakeBrowserRegistry(fake_browser()),
        browser_launcher=browser_launcher,
        console_renderer=renderer,
        clock=FakeClock(),
    )

    session = launcher.run()

    assert session.ok is True
    assert session.url == "http://127.0.0.1:8502"
    assert browser_launcher.calls[0][1] == "http://127.0.0.1:8502"
    assert "Backend:  Port 8501 is in use; selected 8502." in stream.getvalue()
    session.stop()


def test_run_webapp_does_not_create_runtime_state_under_package_source(
    tmp_path: Path,
):
    package_dir = tmp_path / "src" / "litpack"
    package_dir.mkdir(parents=True)
    app = package_dir / "app.py"
    app.write_text("print('hello')\n", encoding="utf-8")
    browser_launcher = FakeBrowserLauncher(ok=True)
    launcher = StreamlitLauncher(
        LauncherConfig(app_path=app, mode="webapp", cwd=package_dir),
        port_manager=FakePortManager(8603),
        process_manager=FakeProcessManager(),
        health_checker=FakeHealthChecker(healthy=True),
        browser_registry=FakeBrowserRegistry(fake_browser()),
        browser_launcher=browser_launcher,
        clock=FakeClock(),
    )

    session = launcher.run()
    profile_arg = next(
        arg
        for arg in browser_launcher.calls[0][4]
        if str(arg).startswith("--user-data-dir=")
    )
    profile_path = Path(profile_arg.split("=", 1)[1])

    assert session.ok is True
    assert not (package_dir / ".litlaunch").exists()
    assert package_dir not in profile_path.parents
    session.stop()
    assert not profile_path.exists()


def test_run_webapp_honors_explicit_runtime_state_root(tmp_path: Path):
    app = tmp_path / "app.py"
    state_root = tmp_path / "runtime-state"
    app.write_text("print('hello')\n", encoding="utf-8")
    browser_launcher = FakeBrowserLauncher(ok=True)
    launcher = StreamlitLauncher(
        LauncherConfig(
            app_path=app,
            mode="webapp",
            runtime_state_root=state_root,
        ),
        port_manager=FakePortManager(8603),
        process_manager=FakeProcessManager(),
        health_checker=FakeHealthChecker(healthy=True),
        browser_registry=FakeBrowserRegistry(fake_browser()),
        browser_launcher=browser_launcher,
        clock=FakeClock(),
    )

    session = launcher.run()
    profile_arg = next(
        arg
        for arg in browser_launcher.calls[0][4]
        if str(arg).startswith("--user-data-dir=")
    )
    profile_path = Path(profile_arg.split("=", 1)[1])

    assert profile_path.is_relative_to(state_root)
    assert browser_launcher.artifact_roots == [state_root]
    session.stop()
    assert not profile_path.exists()


def test_cleanup_litlaunch_owned_dir_requires_marker(tmp_path: Path):
    arbitrary = tmp_path / "arbitrary"
    arbitrary.mkdir()
    (arbitrary / "data.txt").write_text("keep", encoding="utf-8")

    cleanup_litlaunch_owned_dir(arbitrary)

    assert arbitrary.exists()
    owned = tmp_path / "owned"
    owned.mkdir()
    (owned / OWNED_MARKER).write_text("owned", encoding="utf-8")

    cleanup_litlaunch_owned_dir(owned)
    cleanup_litlaunch_owned_dir(owned)

    assert not owned.exists()


def test_run_webapp_respects_explicit_browser_profile(tmp_path: Path):
    app = tmp_path / "app.py"
    app.write_text("print('hello')\n", encoding="utf-8")
    browser_launcher = FakeBrowserLauncher(ok=True)
    launcher = StreamlitLauncher(
        LauncherConfig(
            app_path=app,
            mode="webapp",
            extra_browser_args=("--user-data-dir=C:/custom-profile",),
        ),
        port_manager=FakePortManager(8603),
        process_manager=FakeProcessManager(),
        health_checker=FakeHealthChecker(healthy=True),
        browser_registry=FakeBrowserRegistry(fake_browser()),
        browser_launcher=browser_launcher,
        clock=FakeClock(),
    )

    session = launcher.run()

    assert session.ok is True
    assert browser_launcher.calls[0][4] == ("--user-data-dir=C:/custom-profile",)
    session.stop()


def test_run_browser_mode_does_not_create_managed_browser_profile(tmp_path: Path):
    app = tmp_path / "app.py"
    app.write_text("print('hello')\n", encoding="utf-8")
    browser_launcher = FakeBrowserLauncher(ok=True)
    launcher = StreamlitLauncher(
        LauncherConfig(app_path=app, mode="browser"),
        port_manager=FakePortManager(8603),
        process_manager=FakeProcessManager(),
        health_checker=FakeHealthChecker(healthy=True),
        browser_registry=FakeBrowserRegistry(fake_browser()),
        browser_launcher=browser_launcher,
        clock=FakeClock(),
    )

    session = launcher.run()

    assert session.ok is True
    assert browser_launcher.calls[0][4] == ()
    session.stop()


def test_start_backend_injects_shutdown_env_with_distinct_port_and_private_token():
    process_manager = FakeProcessManager()
    port_manager = FakePortManager(8610)
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py"),
        port_manager=port_manager,
        process_manager=process_manager,
        health_checker=FakeHealthChecker(healthy=True),
        clock=FakeClock(),
    )

    session = launcher.start_backend()

    env = process_manager.started[0][1]["env"]
    token = env["LITLAUNCH_SHUTDOWN_TOKEN"]
    assert session.process is not None
    assert not hasattr(session, "shutdown_client")
    assert session._shutdown_client is not None
    assert env["LITLAUNCH_SHUTDOWN_HOST"] == "127.0.0.1"
    assert env["LITLAUNCH_SHUTDOWN_PORT"] == "8611"
    assert env["LITLAUNCH_SHUTDOWN_PORT"] != "8610"
    assert token
    assert session._shutdown_client.port == 8611
    assert all(token not in event.message for event in session.events)


def test_run_health_failure_stops_only_backend_before_browser_resolution():
    process_manager = FakeProcessManager()
    browser_registry = FakeBrowserRegistry(fake_browser())
    browser_launcher = FakeBrowserLauncher(ok=True)
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py"),
        port_manager=FakePortManager(8604),
        process_manager=process_manager,
        health_checker=FakeHealthChecker(healthy=False),
        browser_registry=browser_registry,
        browser_launcher=browser_launcher,
        clock=FakeClock(),
    )

    session = launcher.run()

    assert session.ok is False
    assert session.state == LaunchState.FAILED
    assert session.process is None
    assert len(process_manager.stopped) == 1
    assert browser_registry.calls == []
    assert browser_launcher.calls == []


def test_run_browser_failure_stops_only_backend(tmp_path: Path):
    app = tmp_path / "app.py"
    app.write_text("print('hello')\n", encoding="utf-8")
    browser_launcher = FakeBrowserLauncher(ok=False)
    process_manager = FakeProcessManager()
    launcher = StreamlitLauncher(
        LauncherConfig(app_path=app, mode="webapp"),
        port_manager=FakePortManager(8605),
        process_manager=process_manager,
        health_checker=FakeHealthChecker(healthy=True),
        browser_registry=FakeBrowserRegistry(fake_browser(BrowserKind.DEFAULT)),
        browser_launcher=browser_launcher,
        clock=FakeClock(),
    )

    session = launcher.run()
    profile_arg = next(
        arg
        for arg in browser_launcher.calls[0][4]
        if str(arg).startswith("--user-data-dir=")
    )
    profile_path = Path(profile_arg.split("=", 1)[1])

    assert session.ok is False
    assert session.state == LaunchState.FAILED
    assert session.browser_launched is False
    assert session.browser_command == ("browser",)
    assert session.process is None
    assert len(process_manager.stopped) == 1
    assert not profile_path.exists()
    assert LaunchState.TERMINATING in {event.state for event in session.events}


def test_browser_failure_console_guidance_is_actionable():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py", mode="webapp", browser="edge"),
        port_manager=FakePortManager(8605),
        process_manager=FakeProcessManager(),
        health_checker=FakeHealthChecker(healthy=True),
        browser_registry=FakeBrowserRegistry(fake_browser(BrowserKind.EDGE)),
        browser_launcher=FakeBrowserLauncher(ok=False),
        console_renderer=renderer,
        clock=FakeClock(),
    )

    session = launcher.run()

    output = stream.getvalue()
    assert session.ok is False
    assert "Browser:  Launch failed; stopping backend." in output
    assert "Check that the requested browser is installed and launchable." not in output
    assert "--browser default" not in output
    assert output.count("[ error  ]") == 1
    assert "[   ok   ] Backend:  Port 8605 released." in output


def test_run_browser_mode_can_use_default_browser_path():
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py", mode="browser", browser="default"),
        port_manager=FakePortManager(8606),
        process_manager=FakeProcessManager(),
        health_checker=FakeHealthChecker(healthy=True),
        browser_registry=FakeBrowserRegistry(fake_browser(BrowserKind.DEFAULT)),
        browser_launcher=FakeBrowserLauncher(ok=True),
        clock=FakeClock(),
    )

    session = launcher.run()

    assert session.ok is True
    assert session.browser is not None
    assert session.browser.kind == BrowserKind.DEFAULT
    assert session.state == LaunchState.RUNNING


def test_run_respects_allow_browser_fallback_config():
    browser_registry = FakeBrowserRegistry(fake_browser())
    browser_launcher = FakeBrowserLauncher(ok=True)
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py", allow_browser_fallback=False),
        port_manager=FakePortManager(8607),
        process_manager=FakeProcessManager(),
        health_checker=FakeHealthChecker(healthy=True),
        browser_registry=browser_registry,
        browser_launcher=browser_launcher,
        clock=FakeClock(),
    )

    session = launcher.run()

    assert session.ok is True
    assert browser_registry.calls == [(BrowserChoice.AUTO, False, False)]
    assert browser_launcher.calls[0][-1] is False


def test_start_returns_runtime_session_without_blocking():
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py"),
        port_manager=FakePortManager(8608),
        process_manager=FakeProcessManager(),
        health_checker=FakeHealthChecker(healthy=True),
        browser_registry=FakeBrowserRegistry(fake_browser()),
        browser_launcher=FakeBrowserLauncher(ok=True),
        clock=FakeClock(),
    )

    session = launcher.start(health_timeout_seconds=1.0, health_interval_seconds=0.1)

    assert isinstance(session, RuntimeSession)
    assert session.ok is True
    assert session.state == LaunchState.RUNNING
    assert session.url == "http://127.0.0.1:8608"


def test_launcher_emits_high_level_console_messages_without_tokens():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )
    process_manager = FakeProcessManager()
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py", mode="webapp"),
        port_manager=FakePortManager(8609),
        process_manager=process_manager,
        health_checker=FakeHealthChecker(healthy=True),
        browser_registry=FakeBrowserRegistry(fake_browser()),
        browser_launcher=FakeBrowserLauncher(ok=True),
        console_renderer=renderer,
        clock=FakeClock(),
    )

    session = launcher.run()

    output = stream.getvalue()
    token = process_manager.started[0][1]["env"]["LITLAUNCH_SHUTDOWN_TOKEN"]
    assert session.ok is True
    assert "[   ok   ] LitLaunch Starting runtime..." in output
    assert "[LitLaunch]" not in output
    assert "[   ok   ] Backend: Starting Streamlit..." not in output
    assert "Backend:  Started Streamlit in" in output
    assert "Backend PID: 999" not in output
    assert "[   ok   ] Health:   Waiting for Streamlit..." in output
    assert "[   ok   ] Health:   Waiting for Streamlit...\n\n" not in output
    assert "Health:   Ready in" in output
    assert "Browser: opening Edge app window" not in output
    assert "Browser:  Browser launched in" in output
    assert "Runtime:  Ready locally at http://127.0.0.1:8609" in output
    assert token not in output


def test_launcher_verbose_console_emits_command_detail():
    stream = StringIO()
    renderer = ConsoleRenderer(
        mode="verbose",
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py"),
        port_manager=FakePortManager(8612),
        process_manager=FakeProcessManager(),
        health_checker=FakeHealthChecker(healthy=True),
        console_renderer=renderer,
        clock=FakeClock(),
    )

    session = launcher.start_backend()

    output = stream.getvalue()
    assert session.ok is True
    assert "Command:" in output
    assert "[   ok   ] Backend:  Starting Streamlit..." in output
    assert "--server.port 8612" in output
