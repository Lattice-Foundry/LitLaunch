import threading

import pytest

from litlaunch import LauncherConfig, LaunchMode, LaunchProfile
from litlaunch.browsers import BrowserCapability, BrowserKind
from litlaunch.exceptions import ConfigurationError
from litlaunch.monitored import MonitoredRunResult, run_monitored_webapp, run_profile
from litlaunch.windowing import (
    NoopWindowMonitor,
    WindowInfo,
    WindowMonitorConfig,
    WindowMonitorResult,
    WindowMonitorStatus,
)


class FakePlatformDetector:
    def __init__(self):
        self.calls = 0
        self.info = object()

    def detect(self):
        self.calls += 1
        return self.info


class FakeMonitor:
    def __init__(self, *, baseline=()):
        self.baseline = tuple(baseline)
        self.capture_calls = []

    def capture(self, target):
        self.capture_calls.append(target)
        return self.baseline

    def wait_for_close(self, target, *, backend_is_running, config):
        raise AssertionError("RuntimeSession owns wait_for_close delegation")


class StartupCloseMonitor:
    def __init__(self):
        self.baseline_seen = False
        self.visible = True
        self.seen = threading.Event()

    def capture(self, target):
        if not self.baseline_seen:
            self.baseline_seen = True
            return ()
        if not self.visible:
            return ()
        window = WindowInfo("new", title="127.0.0.1_/", process_name="msedge")
        self.seen.set()
        return (window,)

    def wait_for_close(self, target, *, backend_is_running, config):
        raise AssertionError("startup close should be handled before monitor wait")


class FakeSession:
    def __init__(self, *, monitor_result, ok=True, raises_keyboard=False):
        self.ok = ok
        self.url = "http://127.0.0.1:8501"
        self.process = object() if ok else None
        self.result = type("Result", (), {"message": "launch failed"})()
        self.browser = BrowserCapability(
            kind=BrowserKind.EDGE,
            name="Edge",
            executable_path="edge.exe",
            available=True,
            supports_app_mode=True,
            supports_full_browser=True,
        )
        self.monitor_result = monitor_result
        self.raises_keyboard = raises_keyboard
        self.monitor_calls = []
        self.stop_calls = []
        self.running = ok
        self.console_renderer = None
        self.events = []

    def monitor_window(self, monitor, target, **kwargs):
        self.monitor_calls.append((monitor, target, kwargs))
        if self.raises_keyboard:
            raise KeyboardInterrupt
        if self.monitor_result.closed:
            self.running = False
        return self.monitor_result

    def stop(self, *args, **kwargs):
        self.stop_calls.append((args, kwargs))
        self.running = False

    def is_running(self):
        return self.running

    def add_event(self, state, message, *, render=True):
        self.events.append((state, message, render))


class FakeLauncher:
    def __init__(self, config, session):
        self.config = config
        self.session = session
        self.run_calls = 0

    def run(self):
        self.run_calls += 1
        return self.session


class StartupCloseLauncher(FakeLauncher):
    def __init__(self, config, session, monitor):
        super().__init__(config, session)
        self.monitor = monitor

    def run(self):
        self.run_calls += 1
        assert self.monitor.seen.wait(timeout=1.0)
        self.monitor.visible = False
        return self.session


def closed_result():
    return WindowMonitorResult(
        supported=True,
        observed=True,
        closed=True,
        status=WindowMonitorStatus.WINDOW_CLOSED,
        message="window closed",
    )


def test_run_monitored_webapp_starts_launcher_and_monitors_target():
    session = FakeSession(monitor_result=closed_result())
    launcher = FakeLauncher(
        LauncherConfig(app_path="app.py", mode=LaunchMode.WEBAPP),
        session,
    )
    monitor = FakeMonitor(baseline=(WindowInfo("old"),))
    config = WindowMonitorConfig(
        appear_timeout_seconds=12.0,
        poll_interval_seconds=0.5,
        stable_poll_count=3,
    )

    result = run_monitored_webapp(
        launcher,
        monitor=monitor,
        window_monitor_config=config,
        graceful_timeout_seconds=9.0,
    )

    assert isinstance(result, MonitoredRunResult)
    assert result.exit_code == 0
    assert result.session is session
    assert result.monitor_result is session.monitor_result
    assert result.launched is True
    assert result.stopped_cleanly is True
    assert launcher.run_calls == 1
    assert monitor.capture_calls[0].title == "Streamlit App"
    assert session.monitor_calls[0][0] is monitor
    assert session.monitor_calls[0][1].baseline_handles == ("old",)
    assert session.monitor_calls[0][1].browser_kind == BrowserKind.EDGE
    assert session.monitor_calls[0][2]["config"] == config
    assert session.monitor_calls[0][2]["graceful_timeout_seconds"] == 9.0


def test_run_monitored_webapp_can_create_launcher_from_config():
    session = FakeSession(monitor_result=closed_result())

    class LauncherFactory(FakeLauncher):
        def __init__(self, config):
            super().__init__(config, session)

    result = run_monitored_webapp(
        LauncherConfig(app_path="app.py", mode="webapp"),
        monitor=FakeMonitor(),
        launcher_factory=LauncherFactory,
    )

    assert result.exit_code == 0
    assert result.session is session


def test_run_monitored_webapp_creates_monitor_from_platform():
    session = FakeSession(monitor_result=closed_result())
    launcher = FakeLauncher(LauncherConfig(app_path="app.py", mode="webapp"), session)
    detector = FakePlatformDetector()
    monitor = FakeMonitor()
    factory_calls = []

    def factory(platform_info):
        factory_calls.append(platform_info)
        return monitor

    result = run_monitored_webapp(
        launcher,
        platform_detector=detector,
        window_monitor_factory=factory,
    )

    assert result.exit_code == 0
    assert detector.calls == 1
    assert factory_calls == [detector.info]
    assert monitor.capture_calls


def test_run_monitored_webapp_unsupported_provider_does_not_launch():
    session = FakeSession(monitor_result=closed_result())
    launcher = FakeLauncher(LauncherConfig(app_path="app.py", mode="webapp"), session)

    result = run_monitored_webapp(launcher, monitor=NoopWindowMonitor())

    assert result.exit_code == 1
    assert result.session is None
    assert result.launched is False
    assert result.monitor_result is not None
    assert result.monitor_result.status == WindowMonitorStatus.UNSUPPORTED
    assert launcher.run_calls == 0


@pytest.mark.parametrize(
    "status",
    [
        WindowMonitorStatus.UNSUPPORTED,
        WindowMonitorStatus.TIMEOUT,
        WindowMonitorStatus.ERROR,
    ],
)
def test_run_monitored_webapp_nonideal_monitor_result_stops_backend(status):
    monitor_result = WindowMonitorResult(
        supported=status != WindowMonitorStatus.UNSUPPORTED,
        observed=False,
        closed=False,
        status=status,
        message=status.value,
    )
    session = FakeSession(monitor_result=monitor_result)
    launcher = FakeLauncher(LauncherConfig(app_path="app.py", mode="webapp"), session)

    result = run_monitored_webapp(
        launcher,
        monitor=FakeMonitor(),
        graceful_timeout_seconds=8.0,
    )

    assert result.exit_code == 1
    assert result.launched is True
    assert result.stopped_cleanly is True
    assert session.stop_calls == [((), {"graceful_timeout_seconds": 8.0})]


def test_run_monitored_webapp_backend_exited_maps_cleanly_without_stop():
    monitor_result = WindowMonitorResult(
        supported=True,
        observed=True,
        closed=False,
        status=WindowMonitorStatus.BACKEND_EXITED,
        message="backend exited",
    )
    session = FakeSession(monitor_result=monitor_result)
    launcher = FakeLauncher(LauncherConfig(app_path="app.py", mode="webapp"), session)

    result = run_monitored_webapp(launcher, monitor=FakeMonitor())

    assert result.exit_code == 0
    assert result.message == "backend exited"
    assert session.stop_calls == []


def test_run_monitored_webapp_launch_failure_does_not_monitor():
    session = FakeSession(monitor_result=closed_result(), ok=False)
    launcher = FakeLauncher(LauncherConfig(app_path="app.py", mode="webapp"), session)
    monitor = FakeMonitor()

    result = run_monitored_webapp(launcher, monitor=monitor)

    assert result.exit_code == 1
    assert result.launched is False
    assert result.monitor_result is None
    assert monitor.capture_calls
    assert session.monitor_calls == []


def test_run_monitored_webapp_keyboard_interrupt_stops_backend():
    session = FakeSession(monitor_result=closed_result(), raises_keyboard=True)
    launcher = FakeLauncher(LauncherConfig(app_path="app.py", mode="webapp"), session)

    result = run_monitored_webapp(
        launcher,
        monitor=FakeMonitor(),
        graceful_timeout_seconds=6.0,
    )

    assert result.exit_code == 0
    assert result.message == "Window monitoring interrupted; runtime stopped."
    assert session.stop_calls == [((), {"graceful_timeout_seconds": 6.0})]


def test_run_monitored_webapp_handles_window_closed_during_browser_launch_gap():
    monitor = StartupCloseMonitor()
    session = FakeSession(monitor_result=closed_result())
    launcher = StartupCloseLauncher(
        LauncherConfig(app_path="app.py", mode="webapp"),
        session,
        monitor,
    )

    result = run_monitored_webapp(
        launcher,
        monitor=monitor,
        graceful_timeout_seconds=7.0,
    )

    assert result.exit_code == 0
    assert result.monitor_result is not None
    assert result.monitor_result.closed is True
    assert result.monitor_result.message == (
        "App-mode window closed before monitoring started."
    )
    assert session.monitor_calls == []
    assert session.stop_calls == [((), {"graceful_timeout_seconds": 7.0})]


def test_run_monitored_webapp_requires_webapp_mode():
    launcher = FakeLauncher(
        LauncherConfig(app_path="app.py", mode="browser"),
        FakeSession(monitor_result=closed_result()),
    )

    with pytest.raises(ConfigurationError, match="mode='webapp'"):
        run_monitored_webapp(launcher, monitor=FakeMonitor())


def test_run_monitored_webapp_rejects_nonpositive_graceful_timeout():
    launcher = FakeLauncher(
        LauncherConfig(app_path="app.py", mode="webapp"),
        FakeSession(monitor_result=closed_result()),
    )

    with pytest.raises(ConfigurationError, match="positive"):
        run_monitored_webapp(
            launcher,
            monitor=FakeMonitor(),
            graceful_timeout_seconds=0,
        )


def test_run_profile_non_monitored_runs_normal_launcher():
    session = FakeSession(monitor_result=closed_result())
    launcher = FakeLauncher(
        LauncherConfig(app_path="app.py", mode="browser"),
        session,
    )
    profile = LaunchProfile(name="dev", config=launcher.config)

    result = run_profile(profile, launcher=launcher)

    assert result.exit_code == 0
    assert result.session is session
    assert result.monitor_result is None
    assert result.launched is True
    assert launcher.run_calls == 1
    assert session.monitor_calls == []


def test_run_profile_non_monitored_launch_failure_is_structured():
    session = FakeSession(monitor_result=closed_result(), ok=False)
    launcher = FakeLauncher(
        LauncherConfig(app_path="app.py", mode="browser"),
        session,
    )
    profile = LaunchProfile(name="dev", config=launcher.config)

    result = run_profile(profile, launcher=launcher)

    assert result.exit_code == 1
    assert result.session is session
    assert result.launched is False
    assert result.message == "launch failed"


def test_run_profile_monitored_uses_profile_runtime_settings():
    session = FakeSession(monitor_result=closed_result())
    launcher = FakeLauncher(
        LauncherConfig(app_path="app.py", mode="webapp"),
        session,
    )
    monitor_config = WindowMonitorConfig(
        appear_timeout_seconds=30.0,
        poll_interval_seconds=0.25,
        stable_poll_count=4,
    )
    profile = LaunchProfile(
        name="webapp",
        config=launcher.config,
        monitor_window=True,
        graceful_timeout_seconds=11.0,
        window_monitor_config=monitor_config,
    )
    monitor = FakeMonitor(baseline=(WindowInfo("old"),))

    result = run_profile(profile, launcher=launcher, monitor=monitor)

    assert result.exit_code == 0
    assert launcher.run_calls == 1
    assert monitor.capture_calls
    assert session.monitor_calls[0][2]["config"] == monitor_config
    assert session.monitor_calls[0][2]["graceful_timeout_seconds"] == 11.0
    assert session.monitor_calls[0][1].baseline_handles == ("old",)


def test_run_profile_can_create_launcher_from_profile_config():
    session = FakeSession(monitor_result=closed_result())

    class LauncherFactory(FakeLauncher):
        def __init__(self, config):
            super().__init__(config, session)

    profile = LaunchProfile(
        name="webapp",
        config=LauncherConfig(app_path="app.py", mode="webapp"),
        monitor_window=True,
    )

    result = run_profile(
        profile,
        monitor=FakeMonitor(),
        launcher_factory=LauncherFactory,
    )

    assert result.exit_code == 0
    assert result.session is session
