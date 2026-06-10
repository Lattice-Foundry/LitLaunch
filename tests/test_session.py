import subprocess
from io import StringIO

from litlaunch._protocols import ClockProvider
from litlaunch.browsers import BrowserCapability, BrowserKind
from litlaunch.console import ConsoleMode, ConsoleRenderer, ConsoleTheme
from litlaunch.events import RuntimeEvent, RuntimeEventEmitter
from litlaunch.lifecycle import LaunchEvent, LaunchResult, LaunchState
from litlaunch.process import ManagedProcess
from litlaunch.session import RuntimeSession
from litlaunch.shutdown import ShutdownHookResult, ShutdownRequestResult
from litlaunch.windowing import (
    WindowInfo,
    WindowMonitorConfig,
    WindowMonitorResult,
    WindowMonitorStatus,
    WindowTarget,
)


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
    def __init__(self, *, ok=True, hook_results=()):
        self.ok = ok
        self.hook_results = hook_results
        self.calls = 0

    def request_shutdown(self):
        self.calls += 1
        return ShutdownRequestResult(
            ok=self.ok,
            status_code=200 if self.ok else 500,
            message="accepted" if self.ok else "failed",
            hook_results=self.hook_results,
        )


class FakeWindowMonitor:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def capture(self, target):
        return ()

    def wait_for_close(self, target, *, backend_is_running, config):
        self.calls.append((target, backend_is_running(), config))
        return self.result


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


def test_runtime_session_emits_shutdown_hook_and_stop_events():
    events: list[RuntimeEvent] = []
    process_manager = FakeProcessManager(running=True, wait_return=0)
    session = RuntimeSession(
        result=make_result(),
        process=make_process(),
        process_manager=process_manager,
        shutdown_client=FakeShutdownClient(
            ok=True,
            hook_results=(
                ShutdownHookResult(
                    label="Cloud sync",
                    ok=True,
                    message="Cloud sync complete.",
                ),
                ShutdownHookResult(
                    label="Cleanup",
                    ok=False,
                    message="Cleanup failed.",
                    error="SECRET_TOKEN=do-not-emit",
                ),
            ),
        ),
        event_emitter=RuntimeEventEmitter(events.append),
        port_release_checker=lambda host, port: True,
        clock=FakeClock(),
    )

    session.stop()

    assert [event.name for event in events] == [
        "shutdown_requested",
        "hook_succeeded",
        "hook_failed",
        "backend_stopped",
        "port_released",
    ]
    assert events[1].details == {"label": "Cloud sync"}
    assert events[2].level == "error"
    assert "SECRET_TOKEN" not in "\n".join(
        line
        for event in events
        for line in (
            event.message,
            *[f"{key}={value}" for key, value in event.details.items()],
        )
    )


def test_runtime_session_event_sink_failure_does_not_break_shutdown():
    process_manager = FakeProcessManager(running=True, wait_return=0)

    def failing_sink(event):
        raise RuntimeError("sink exploded")

    session = RuntimeSession(
        result=make_result(),
        process=make_process(),
        process_manager=process_manager,
        shutdown_client=FakeShutdownClient(ok=True),
        event_emitter=RuntimeEventEmitter(failing_sink),
        clock=FakeClock(),
    )

    session.stop()

    assert session.state == LaunchState.TERMINATED
    assert process_manager.wait_calls


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


def test_runtime_session_runs_cleanup_callbacks_once_on_stop():
    calls = []
    manager = FakeProcessManager()
    session = RuntimeSession(
        result=make_result(),
        process=make_process(),
        process_manager=manager,
        cleanup_callbacks=(lambda: calls.append("cleanup"),),
        clock=FakeClock(),
    )

    session.stop()
    session.stop()

    assert calls == ["cleanup"]


def test_runtime_session_runs_cleanup_callbacks_on_wait():
    calls = []
    process = make_process()
    manager = FakeProcessManager(wait_return=0)
    session = RuntimeSession(
        result=make_result(),
        process=process,
        process_manager=manager,
        cleanup_callbacks=(lambda: calls.append("cleanup"),),
        clock=FakeClock(),
    )

    assert session.wait() == 0

    assert calls == ["cleanup"]


def test_runtime_session_cleanup_callback_failure_is_ignored():
    calls = []

    def failing_cleanup():
        calls.append("before")
        raise RuntimeError("cleanup failed")

    session = RuntimeSession(
        result=make_result(),
        process=None,
        process_manager=FakeProcessManager(),
        cleanup_callbacks=(
            failing_cleanup,
            lambda: calls.append("after"),
        ),
        clock=FakeClock(),
    )

    session.stop()

    assert calls == ["before", "after"]


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


def test_runtime_session_wait_without_timeout_remains_blocking_delegate():
    process = make_process()
    manager = FakeProcessManager(wait_return=0)
    session = RuntimeSession(
        result=make_result(),
        process=process,
        process_manager=manager,
        clock=FakeClock(),
    )

    assert session.wait() == 0
    assert manager.wait_calls == [(process, None)]
    assert session.state == LaunchState.TERMINATED


def test_runtime_session_wait_renders_clean_backend_exit_without_exit_code_zero():
    stream = StringIO()
    process = make_process()
    manager = FakeProcessManager(wait_return=0)
    session = RuntimeSession(
        result=make_result(),
        process=process,
        process_manager=manager,
        console_renderer=ConsoleRenderer(
            theme=ConsoleTheme(use_color=False),
            stream=stream,
        ),
        clock=FakeClock(),
    )

    assert session.wait() == 0

    output = stream.getvalue()
    assert "[   ok   ] Backend: Exited cleanly." in output
    assert "exited with code 0" not in output
    assert "Exited with code" not in output


def test_runtime_session_wait_renders_nonzero_backend_exit_code():
    stream = StringIO()
    process = make_process()
    manager = FakeProcessManager(wait_return=2)
    session = RuntimeSession(
        result=make_result(),
        process=process,
        process_manager=manager,
        console_renderer=ConsoleRenderer(
            theme=ConsoleTheme(use_color=False),
            stream=stream,
        ),
        clock=FakeClock(),
    )

    assert session.wait() == 2

    output = stream.getvalue()
    assert "[ error  ] Backend: Exited with code 2." in output
    assert "[ cause  ] The backend stopped with an error status." in output
    assert output.count("[  next  ]") == 1


def test_runtime_session_timed_wait_timeout_returns_none_and_keeps_running_state():
    process = make_process()
    manager = FakeProcessManager(wait_timeout=True)
    session = RuntimeSession(
        result=make_result(),
        process=process,
        process_manager=manager,
        clock=FakeClock(),
    )

    assert session.wait(timeout_seconds=0.1) is None
    assert manager.wait_calls == [(process, 0.1)]
    assert session.state == LaunchState.RUNNING
    assert session.events[-1].message == (
        "Timed wait expired; owned backend process is still running."
    )


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
    assert "Shutdown: requested" not in output
    assert "Shutdown: requesting app cleanup" not in output
    assert "Shutdown: app cleanup request accepted" not in output
    assert "Shutdown: Backend stopped cleanly in" in output
    assert "exited with code 0" not in output


def test_runtime_session_verbose_stop_emits_shutdown_request_details():
    stream = StringIO()
    renderer = ConsoleRenderer(
        mode=ConsoleMode.VERBOSE,
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
    assert "Shutdown: Requested" in output
    assert "Shutdown: Requesting app cleanup" in output
    assert "Shutdown: App cleanup request accepted" in output
    assert "Shutdown: Backend stopped cleanly in" in output


def test_runtime_session_renders_shutdown_hook_results_from_graceful_response():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )
    process = make_process()
    manager = FakeProcessManager(wait_return=0)
    shutdown_client = FakeShutdownClient(
        ok=True,
        hook_results=(
            ShutdownHookResult(
                label="Cloud sync",
                ok=True,
                message="Cloud sync completed",
                console_visibility="normal",
            ),
            ShutdownHookResult(
                label="Verbose cleanup",
                ok=True,
                message="Verbose cleanup completed",
                console_visibility="verbose",
            ),
        ),
    )
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
    assert "[   ok   ] Hook: Cloud sync completed." in output
    assert "Verbose cleanup completed" not in output


def test_runtime_session_renders_verbose_shutdown_hook_results():
    stream = StringIO()
    renderer = ConsoleRenderer(
        mode=ConsoleMode.VERBOSE,
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )
    process = make_process()
    manager = FakeProcessManager(wait_return=0)
    shutdown_client = FakeShutdownClient(
        ok=True,
        hook_results=(
            ShutdownHookResult(
                label="Verbose cleanup",
                ok=True,
                message="Verbose cleanup completed",
                console_visibility="verbose",
            ),
        ),
    )
    session = RuntimeSession(
        result=make_result(),
        process=process,
        process_manager=manager,
        shutdown_client=shutdown_client,
        console_renderer=renderer,
        clock=FakeClock(),
    )

    session.stop(graceful_timeout_seconds=0.5)

    assert "[   ok   ] Hook: Verbose cleanup completed." in stream.getvalue()


def test_runtime_session_reports_port_release_only_when_verified():
    stream = StringIO()
    calls = []
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
        port_release_checker=lambda host, port: calls.append((host, port)) or True,
        clock=FakeClock(),
    )

    session.stop(graceful_timeout_seconds=0.5)

    assert calls == [("127.0.0.1", 8501)]
    assert "[   ok   ] Backend: Port 8501 released." in stream.getvalue()


def test_runtime_session_does_not_claim_port_release_when_not_verified():
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
        port_release_checker=lambda host, port: False,
        clock=FakeClock(),
    )

    session.stop(graceful_timeout_seconds=0.5)

    assert "port 8501 released" not in stream.getvalue()


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


def test_runtime_session_stop_fallback_console_guidance():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )
    process = make_process()
    manager = FakeProcessManager()
    shutdown_client = FakeShutdownClient(ok=False)
    session = RuntimeSession(
        result=make_result(),
        process=process,
        process_manager=manager,
        shutdown_client=shutdown_client,
        console_renderer=renderer,
        clock=FakeClock(),
    )

    session.stop(timeout_seconds=2.0)

    output = stream.getvalue()
    assert "Shutdown: Graceful request failed." in output
    assert "Shutdown: Using backend termination fallback." in output
    assert "LitLaunch will stop only the backend process it started." not in output
    assert "Use verbose mode for more runtime details." in output


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


def test_runtime_session_monitor_window_closed_result_stops_owned_backend():
    process = make_process()
    manager = FakeProcessManager()
    target_window = WindowInfo("0x1", title="Streamlit App")
    monitor = FakeWindowMonitor(
        WindowMonitorResult(
            supported=True,
            observed=True,
            closed=True,
            status=WindowMonitorStatus.WINDOW_CLOSED,
            message="window closed",
            target=target_window,
        )
    )
    session = RuntimeSession(
        result=make_result(),
        process=process,
        process_manager=manager,
        clock=FakeClock(),
    )

    result = session.monitor_window(monitor, WindowTarget("Streamlit"))

    assert result.closed is True
    assert manager.stop_calls == [(process, 5.0)]
    assert monitor.calls
    assert LaunchState.WINDOW_MONITORING in {event.state for event in session.events}
    assert LaunchState.WINDOW_CLOSED in {event.state for event in session.events}
    assert session.state == LaunchState.TERMINATED


def test_runtime_session_monitor_window_passes_custom_graceful_timeout_to_stop():
    process = make_process()
    manager = FakeProcessManager(wait_return=0)
    shutdown_client = FakeShutdownClient(ok=True)
    monitor = FakeWindowMonitor(
        WindowMonitorResult(
            supported=True,
            observed=True,
            closed=True,
            status=WindowMonitorStatus.WINDOW_CLOSED,
            message="window closed",
        )
    )
    session = RuntimeSession(
        result=make_result(),
        process=process,
        process_manager=manager,
        shutdown_client=shutdown_client,
        clock=FakeClock(),
    )

    result = session.monitor_window(
        monitor,
        WindowTarget("Streamlit"),
        graceful_timeout_seconds=12.5,
    )

    assert result.closed is True
    assert shutdown_client.calls == 1
    assert manager.wait_calls == [(process, 12.5)]
    assert manager.stop_calls == []


def test_runtime_session_monitor_window_passes_custom_monitor_config():
    process = make_process()
    manager = FakeProcessManager(wait_return=0)
    monitor = FakeWindowMonitor(
        WindowMonitorResult(
            supported=True,
            observed=True,
            closed=False,
            status=WindowMonitorStatus.BACKEND_EXITED,
            message="backend exited",
        )
    )
    session = RuntimeSession(
        result=make_result(),
        process=process,
        process_manager=manager,
        clock=FakeClock(),
    )
    monitor_config = WindowMonitorConfig(
        appear_timeout_seconds=12.5,
        poll_interval_seconds=0.25,
        stable_poll_count=3,
    )

    result = session.monitor_window(
        monitor,
        WindowTarget("Streamlit"),
        config=monitor_config,
    )

    assert result.status == WindowMonitorStatus.BACKEND_EXITED
    assert monitor.calls[0][2] is monitor_config
    assert manager.stop_calls == []


def test_runtime_session_monitor_window_unsupported_does_not_stop_backend():
    process = make_process()
    manager = FakeProcessManager()
    monitor = FakeWindowMonitor(
        WindowMonitorResult(
            supported=False,
            observed=False,
            closed=False,
            status=WindowMonitorStatus.UNSUPPORTED,
            message="unsupported",
        )
    )
    session = RuntimeSession(
        result=make_result(),
        process=process,
        process_manager=manager,
        clock=FakeClock(),
    )

    result = session.monitor_window(monitor, WindowTarget("Streamlit"))

    assert result.status == WindowMonitorStatus.UNSUPPORTED
    assert manager.stop_calls == []
    assert session.state == LaunchState.RUNNING


def test_runtime_session_monitor_window_timeout_does_not_stop_backend():
    process = make_process()
    manager = FakeProcessManager()
    monitor = FakeWindowMonitor(
        WindowMonitorResult(
            supported=True,
            observed=False,
            closed=False,
            status=WindowMonitorStatus.TIMEOUT,
            message="timeout",
        )
    )
    session = RuntimeSession(
        result=make_result(),
        process=process,
        process_manager=manager,
        clock=FakeClock(),
    )

    result = session.monitor_window(monitor, WindowTarget("Streamlit"))

    assert result.status == WindowMonitorStatus.TIMEOUT
    assert manager.stop_calls == []
    assert session.state == LaunchState.RUNNING


def test_runtime_session_monitor_window_backend_exited_does_not_stop_backend():
    process = make_process()
    manager = FakeProcessManager(running=False)
    monitor = FakeWindowMonitor(
        WindowMonitorResult(
            supported=True,
            observed=True,
            closed=False,
            status=WindowMonitorStatus.BACKEND_EXITED,
            message="backend exited",
        )
    )
    session = RuntimeSession(
        result=make_result(),
        process=process,
        process_manager=manager,
        clock=FakeClock(),
    )

    result = session.monitor_window(monitor, WindowTarget("Streamlit"))

    assert result.status == WindowMonitorStatus.BACKEND_EXITED
    assert manager.stop_calls == []
    assert session.state == LaunchState.TERMINATED
