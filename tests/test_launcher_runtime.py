from litlaunch import LauncherConfig
from litlaunch.health import build_streamlit_app_url, build_streamlit_health_url
from litlaunch.launcher import StreamlitLauncher
from litlaunch.lifecycle import LaunchState
from litlaunch.process import ManagedProcess


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

    result = launcher.start_backend(
        health_timeout_seconds=3.0,
        health_interval_seconds=0.1,
    )

    assert result.ok is True
    assert result.state == LaunchState.HEALTHY
    assert result.pid == 999
    assert result.url == "http://127.0.0.1:8600"
    assert result.command is not None
    assert result.command[result.command.index("--server.port") + 1] == "8600"
    assert process_manager.started == [result.command]
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

    result = launcher.start_backend()

    assert result.ok is False
    assert result.state == LaunchState.FAILED
    assert result.pid == 999
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

    result = launcher.start_backend(wait_for_health=False)

    assert result.ok is True
    assert result.state == LaunchState.PROCESS_RUNNING
    assert health_checker.calls == []
    assert process_manager.stopped == []
