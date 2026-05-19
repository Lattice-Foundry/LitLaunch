import subprocess
from io import StringIO

from litlaunch._protocols import ClockProvider
from litlaunch.browsers import BrowserCapability, BrowserKind
from litlaunch.console import ConsoleRenderer, ConsoleTheme
from litlaunch.lifecycle import LaunchEvent, LaunchResult, LaunchState
from litlaunch.process import ManagedProcess
from litlaunch.session import RuntimeSession
from litlaunch.shutdown import ShutdownRequestResult


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def monotonic(self):
        self.value += 1.0
        return self.value

    def time(self):
        return self.value


class FakePopen:
    pid = 2468


class FakeProcessManager:
    def __init__(self, *, running=True, wait_return=0, wait_timeout=False):
        self.running = running
        self.wait_return = wait_return
        self.wait_timeout = wait_timeout
        self.is_running_calls = []
        self.stop_calls = []
        self.wait_calls = []

    def is_running(self, process):
        self.is_running_calls.append(process)
        return self.running

    def stop(self, process, terminate_timeout_seconds=5.0):
        self.stop_calls.append((process, terminate_timeout_seconds))
        self.running = False

    def wait(self, process, timeout_seconds=None):
        self.wait_calls.append((process, timeout_seconds))
        if self.wait_timeout:
            raise subprocess.TimeoutExpired("fake", timeout_seconds)
        self.running = False
        return self.wait_return


class FakeShutdownClient:
    def __init__(self, *, ok=True):
        self.ok = ok
        self.calls = 0

    def request_shutdown(self):
        self.calls += 1
        return ShutdownRequestResult(
            ok=self.ok,
            status_code=200 if self.ok else 500,
            message="accepted" if self.ok else "failed",
        )


def make_result(*, browser=None, browser_launched=False):
    return LaunchResult(
        ok=True,
        state=LaunchState.RUNNING,
        command=("python", "-m", "streamlit", "run", "app.py"),
        pid=2468,
        url="http://127.0.0.1:8501",
        message="running",
        events=(LaunchEvent(LaunchState.RUNNING, "running", 1.0),),
        browser=browser,
        browser_command=("browser", "--app=http://127.0.0.1:8501")
        if browser_launched
        else None,
        browser_launched=browser_launched,
    )


def make_process():
    return ManagedProcess(FakePopen(), ("python", "-m", "streamlit"))


def test_fake_clock_matches_clock_provider_protocol():
    assert isinstance(FakeClock(), ClockProvider)


def test_runtime_session_exposes_launch_result_convenience_properties():
    browser = BrowserCapability(
        kind=BrowserKind.EDGE,
        name="Edge",
        executable_path="edge.exe",
        available=True,
        supports_app_mode=True,
        supports_full_browser=True,
    )
    result = make_result(browser=browser, browser_launched=True)
    process = make_process()
    session = RuntimeSession(
        result=result,
        process=process,
        process_manager=FakeProcessManager(),
        clock=FakeClock(),
    )

    assert session.ok is True
    assert session.state == LaunchState.RUNNING
    assert session.pid == 2468
    assert session.url == "http://127.0.0.1:8501"
    assert session.command == ("python", "-m", "streamlit", "run", "app.py")
    assert session.browser == browser
    assert session.browser_command == ("browser", "--app=http://127.0.0.1:8501")
    assert session.browser_launched is True
    assert session.events == result.events


def test_runtime_session_is_running_delegates_to_process_manager():
    process = make_process()
    manager = FakeProcessManager(running=True)
    session = RuntimeSession(
        result=make_result(),
        process=process,
        process_manager=manager,
    )

    assert session.is_running() is True
    assert manager.is_running_calls == [process]


def test_runtime_session_without_process_is_not_running():
    manager = FakeProcessManager(running=True)
    session = RuntimeSession(
        result=make_result(),
        process=None,
        process_manager=manager,
    )

    assert session.is_running() is False
    assert manager.is_running_calls == []


def test_runtime_session_stop_is_idempotent_and_only_stops_owned_backend():
    process = make_process()
    manager = FakeProcessManager()
    session = RuntimeSession(
        result=make_result(),
        process=process,
        process_manager=manager,
        clock=FakeClock(),
    )

    session.stop(timeout_seconds=2.0)
    session.stop(timeout_seconds=2.0)

    assert manager.stop_calls == [(process, 2.0)]
    assert session.state == LaunchState.TERMINATED
    assert [event.state for event in session.events][-2:] == [
        LaunchState.TERMINATING,
        LaunchState.TERMINATED,
    ]


def test_runtime_session_stop_without_process_is_noop():
    manager = FakeProcessManager()
    session = RuntimeSession(
        result=make_result(),
        process=None,
        process_manager=manager,
    )

    session.stop()

    assert manager.stop_calls == []


def test_runtime_session_wait_delegates_to_owned_backend_process():
    process = make_process()
    manager = FakeProcessManager(wait_return=17)
    session = RuntimeSession(
        result=make_result(),
        process=process,
        process_manager=manager,
        clock=FakeClock(),
    )

    assert session.wait(timeout_seconds=3.0) == 17
    assert manager.wait_calls == [(process, 3.0)]
    assert session.state == LaunchState.TERMINATED
    assert session.events[-1].state == LaunchState.TERMINATED


def test_runtime_session_wait_without_process_returns_none():
    manager = FakeProcessManager(wait_return=17)
    session = RuntimeSession(
        result=make_result(),
        process=None,
        process_manager=manager,
    )

    assert session.wait() is None
    assert manager.wait_calls == []


def test_runtime_session_events_are_returned_as_tuple_copy():
    session = RuntimeSession(
        result=make_result(),
        process=make_process(),
        process_manager=FakeProcessManager(),
        clock=FakeClock(),
    )

    events = session.events
    session.add_event(LaunchState.HEALTHY, "extra")

    assert isinstance(events, tuple)
    assert len(events) == 1
    assert len(session.events) == 2


def test_runtime_session_context_manager_stops_on_exit():
    process = make_process()
    manager = FakeProcessManager()
    session = RuntimeSession(
        result=make_result(),
        process=process,
        process_manager=manager,
        clock=FakeClock(),
    )

    with session as active:
        assert active is session

    assert manager.stop_calls == [(process, 5.0)]


def test_runtime_session_stop_requests_graceful_shutdown_before_fallback():
    process = make_process()
    manager = FakeProcessManager(wait_return=0)
    shutdown_client = FakeShutdownClient(ok=True)
    session = RuntimeSession(
        result=make_result(),
        process=process,
        process_manager=manager,
        shutdown_client=shutdown_client,
        clock=FakeClock(),
    )

    session.stop(timeout_seconds=2.0, graceful_timeout_seconds=0.5)

    assert shutdown_client.calls == 1
    assert manager.wait_calls == [(process, 0.5)]
    assert manager.stop_calls == []
    assert session.state == LaunchState.TERMINATED
    assert "Graceful shutdown request accepted." in {
        event.message for event in session.events
    }
    assert not hasattr(session, "shutdown_client")
    assert hasattr(session, "_shutdown_client")


def test_runtime_session_stop_emits_console_shutdown_messages():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )
    process = make_process()
    manager = FakeProcessManager(wait_return=0)
    shutdown_client = FakeShutdownClient(ok=True)
    session = RuntimeSession(
        result=make_result(),
        process=process,
        process_manager=manager,
        shutdown_client=shutdown_client,
        console_renderer=renderer,
        clock=FakeClock(),
    )

    session.stop(graceful_timeout_seconds=0.5)

    output = stream.getvalue()
    assert "Requesting graceful shutdown." in output
    assert "Graceful shutdown request accepted." in output
    assert "Owned backend process exited with code 0." in output


def test_runtime_session_stop_uses_fallback_when_graceful_request_fails():
    process = make_process()
    manager = FakeProcessManager()
    shutdown_client = FakeShutdownClient(ok=False)
    session = RuntimeSession(
        result=make_result(),
        process=process,
        process_manager=manager,
        shutdown_client=shutdown_client,
        clock=FakeClock(),
    )

    session.stop(timeout_seconds=2.0)

    assert shutdown_client.calls == 1
    assert manager.wait_calls == []
    assert manager.stop_calls == [(process, 2.0)]
    assert session.state == LaunchState.TERMINATED


def test_runtime_session_stop_uses_fallback_when_graceful_wait_times_out():
    process = make_process()
    manager = FakeProcessManager(wait_timeout=True)
    shutdown_client = FakeShutdownClient(ok=True)
    session = RuntimeSession(
        result=make_result(),
        process=process,
        process_manager=manager,
        shutdown_client=shutdown_client,
        clock=FakeClock(),
    )

    session.stop(timeout_seconds=2.0, graceful_timeout_seconds=0.5)

    assert shutdown_client.calls == 1
    assert manager.wait_calls == [(process, 0.5)]
    assert manager.stop_calls == [(process, 2.0)]
    assert session.state == LaunchState.TERMINATED


def test_runtime_session_has_no_browser_process_ownership_surface():
    session = RuntimeSession(
        result=make_result(),
        process=make_process(),
        process_manager=FakeProcessManager(),
    )

    assert not hasattr(session, "browser_process")
    assert not hasattr(session, "kill_browser")
    assert not hasattr(session, "stop_browser")
