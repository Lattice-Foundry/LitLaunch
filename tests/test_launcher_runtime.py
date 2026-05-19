from litlaunch import LauncherConfig, LaunchMode
from litlaunch.browsers import (
    BrowserCapability,
    BrowserKind,
    BrowserLaunchResult,
    BrowserResolution,
)
from litlaunch.config import BrowserChoice
from litlaunch.health import build_streamlit_app_url, build_streamlit_health_url
from litlaunch.launcher import StreamlitLauncher
from litlaunch.lifecycle import LaunchState
from litlaunch.process import ManagedProcess
from litlaunch.session import RuntimeSession


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def monotonic(self):
        self.value += 1.0
        return self.value


class FakePortManager:
    def __init__(self, port):
        self.port = port
        self.calls = []

    def resolve_port(self, config):
        self.calls.append(config)
        return self.port


class FakePopen:
    pid = 999

    def poll(self):
        return None


class FakeProcessManager:
    def __init__(self):
        self.started = []
        self.stopped = []

    def start(self, command):
        self.started.append(command)
        return ManagedProcess(FakePopen(), tuple(command))

    def stop(self, process):
        self.stopped.append(process)


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

    def launch(self, resolution, *, url, mode, title, extra_args):
        self.calls.append((resolution, url, mode, title, extra_args))
        return BrowserLaunchResult(
            ok=self.ok,
            command=("browser", "--app=" + url) if self.ok else ("browser",),
            browser=resolution.selected,
            mode=mode,
            message="browser launched" if self.ok else "browser failed",
        )


def fake_browser(kind=BrowserKind.EDGE):
    return BrowserCapability(
        kind=kind,
        name=kind.value.title(),
        executable_path="browser.exe",
        available=True,
        supports_app_mode=kind != BrowserKind.DEFAULT,
        supports_full_browser=True,
    )


def test_launcher_builds_app_and_health_urls_with_resolved_port():
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py"),
        port_manager=FakePortManager(8600),
    )

    assert launcher.build_app_url() == build_streamlit_app_url("127.0.0.1", 8600)
    assert launcher.build_health_url() == build_streamlit_health_url("127.0.0.1", 8600)


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
    assert process_manager.started == [session.command]
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
    assert LaunchState.TERMINATING in {event.state for event in result.events}


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


def test_run_starts_backend_waits_health_resolves_and_launches_browser():
    process_manager = FakeProcessManager()
    browser_registry = FakeBrowserRegistry(fake_browser())
    browser_launcher = FakeBrowserLauncher(ok=True)
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py", mode="webapp", extra_browser_args=["--x"]),
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
    assert session.browser_command == ("browser", "--app=http://127.0.0.1:8603")
    assert session.process is not None
    assert browser_registry.calls == [(BrowserChoice.AUTO, True, True)]
    assert browser_launcher.calls[0][2:] == (
        LaunchMode.WEBAPP,
        "Streamlit App",
        ("--x",),
    )
    assert process_manager.stopped == []


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


def test_run_browser_failure_stops_only_backend():
    process_manager = FakeProcessManager()
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py"),
        port_manager=FakePortManager(8605),
        process_manager=process_manager,
        health_checker=FakeHealthChecker(healthy=True),
        browser_registry=FakeBrowserRegistry(fake_browser(BrowserKind.DEFAULT)),
        browser_launcher=FakeBrowserLauncher(ok=False),
        clock=FakeClock(),
    )

    session = launcher.run()

    assert session.ok is False
    assert session.state == LaunchState.FAILED
    assert session.browser_launched is False
    assert session.browser_command == ("browser",)
    assert session.process is None
    assert len(process_manager.stopped) == 1
    assert LaunchState.TERMINATING in {event.state for event in session.events}


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
    launcher = StreamlitLauncher(
        LauncherConfig(app_path="app.py", allow_browser_fallback=False),
        port_manager=FakePortManager(8607),
        process_manager=FakeProcessManager(),
        health_checker=FakeHealthChecker(healthy=True),
        browser_registry=browser_registry,
        browser_launcher=FakeBrowserLauncher(ok=True),
        clock=FakeClock(),
    )

    session = launcher.run()

    assert session.ok is True
    assert browser_registry.calls == [(BrowserChoice.AUTO, False, False)]


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
