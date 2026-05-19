from dataclasses import FrozenInstanceError

import pytest

from litlaunch.browsers import BrowserKind
from litlaunch.windowing import (
    NoopWindowMonitor,
    PollingWindowMonitor,
    WindowInfo,
    WindowMonitorConfig,
    WindowMonitorEvent,
    WindowMonitorResult,
    WindowMonitorStatus,
    WindowTarget,
)


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def monotonic(self):
        self.value += 1.0
        return self.value

    def time(self):
        return self.value


def window(handle, title="My Streamlit App", process_name=None):
    return WindowInfo(
        handle=handle,
        title=title,
        class_name="Chrome_WidgetWin_1",
        pid=123,
        process_name=process_name,
    )


def sequence_provider(*captures):
    calls = iter(captures)

    def capture(target):
        return next(calls)

    return capture


def monitor_for(*captures):
    return PollingWindowMonitor(
        sequence_provider(*captures),
        clock=FakeClock(),
        sleeper=lambda seconds: None,
    )


def config(**kwargs):
    return WindowMonitorConfig(
        appear_timeout_seconds=10.0,
        poll_interval_seconds=0.1,
        **kwargs,
    )


def test_window_info_defaults_and_immutability():
    info = WindowInfo(" 0x1 ")

    assert info.handle == "0x1"
    assert info.title == ""
    assert info.class_name == ""
    assert info.pid is None
    assert info.process_name is None
    with pytest.raises(FrozenInstanceError):
        info.title = "new"


def test_window_target_normalizes_baseline_and_requires_title_for_app_mode():
    target = WindowTarget(" My App ", baseline_handles=[" 0x1 ", "0x2"])

    assert target.title == "My App"
    assert target.baseline_handles == ("0x1", "0x2")
    with pytest.raises(ValueError, match="title"):
        WindowTarget("")


def test_window_monitor_config_validation():
    assert WindowMonitorConfig().stable_poll_count == 2

    with pytest.raises(ValueError, match="appear_timeout"):
        WindowMonitorConfig(appear_timeout_seconds=0)
    with pytest.raises(ValueError, match="poll_interval"):
        WindowMonitorConfig(poll_interval_seconds=0)
    with pytest.raises(ValueError, match="stable_poll_count"):
        WindowMonitorConfig(stable_poll_count=0)


def test_window_result_and_event_are_frozen_and_tuple_safe():
    event = WindowMonitorEvent(
        WindowMonitorStatus.WAITING_FOR_WINDOW,
        "waiting",
        1.0,
    )
    result = WindowMonitorResult(
        supported=True,
        observed=False,
        closed=False,
        status=WindowMonitorStatus.TIMEOUT,
        message="timeout",
        events=[event],
    )

    assert result.events == (event,)
    with pytest.raises(FrozenInstanceError):
        result.message = "changed"


def test_noop_window_monitor_reports_unsupported():
    target = WindowTarget("My App")
    monitor = NoopWindowMonitor()

    result = monitor.wait_for_close(
        target,
        backend_is_running=lambda: True,
        config=WindowMonitorConfig(),
    )

    assert monitor.capture(target) == ()
    assert result.supported is False
    assert result.observed is False
    assert result.closed is False
    assert result.status == WindowMonitorStatus.UNSUPPORTED
    assert "not supported" in result.message


def test_polling_monitor_excludes_baseline_handles_and_detects_close():
    existing = window("0x100")
    target_window = window("0x200")
    monitor = monitor_for(
        (existing, target_window),
        (existing, target_window),
        (existing,),
    )

    result = monitor.wait_for_close(
        WindowTarget("My Streamlit", baseline_handles=("0x100",)),
        backend_is_running=lambda: True,
        config=config(),
    )

    assert result.status == WindowMonitorStatus.WINDOW_CLOSED
    assert result.closed is True
    assert result.target == target_window


def test_polling_monitor_times_out_when_no_candidate_appears():
    monitor = PollingWindowMonitor(
        lambda target: (),
        clock=FakeClock(),
        sleeper=lambda seconds: None,
    )

    result = monitor.wait_for_close(
        WindowTarget("My Streamlit"),
        backend_is_running=lambda: True,
        config=WindowMonitorConfig(
            appear_timeout_seconds=2.0,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.supported is True
    assert result.observed is False
    assert result.closed is False
    assert result.status == WindowMonitorStatus.TIMEOUT


def test_polling_monitor_selects_title_match_and_records_events():
    target_window = window("0x200", title="My Streamlit App")
    monitor = monitor_for((target_window,), ())

    result = monitor.wait_for_close(
        WindowTarget("streamlit"),
        backend_is_running=lambda: True,
        config=config(stable_poll_count=1),
    )

    assert result.closed is True
    assert result.target == target_window
    assert [event.status for event in result.events] == [
        WindowMonitorStatus.WAITING_FOR_WINDOW,
        WindowMonitorStatus.WINDOW_OBSERVED,
        WindowMonitorStatus.WINDOW_CLOSED,
    ]


def test_polling_monitor_rejects_transient_handle():
    transient = window("0x111")
    stable = window("0x222")
    monitor = monitor_for((transient,), (), (stable,), (stable,), ())

    result = monitor.wait_for_close(
        WindowTarget("Streamlit"),
        backend_is_running=lambda: True,
        config=config(stable_poll_count=2),
    )

    assert result.closed is True
    assert result.target == stable


def test_polling_monitor_returns_backend_exited_before_window_observed():
    monitor = monitor_for((window("0x1"),))

    result = monitor.wait_for_close(
        WindowTarget("Streamlit"),
        backend_is_running=lambda: False,
        config=config(),
    )

    assert result.status == WindowMonitorStatus.BACKEND_EXITED
    assert result.observed is False
    assert result.closed is False


def test_polling_monitor_returns_backend_exited_after_window_observed():
    calls = iter([True, False])
    monitor = monitor_for((window("0x1"),))

    result = monitor.wait_for_close(
        WindowTarget("Streamlit"),
        backend_is_running=lambda: next(calls),
        config=config(stable_poll_count=1),
    )

    assert result.status == WindowMonitorStatus.BACKEND_EXITED
    assert result.observed is True
    assert result.closed is False
    assert result.target == window("0x1")


def test_polling_monitor_uses_last_matching_candidate_deterministically():
    older = window("0x100")
    newer = window("0x300")
    monitor = monitor_for((older, newer), (older,))

    result = monitor.wait_for_close(
        WindowTarget("Streamlit"),
        backend_is_running=lambda: True,
        config=config(stable_poll_count=1),
    )

    assert result.closed is True
    assert result.target == newer


def test_polling_monitor_ignores_title_mismatch():
    monitor = PollingWindowMonitor(
        lambda target: (window("0x1", title="Other App"),),
        clock=FakeClock(),
        sleeper=lambda seconds: None,
    )

    result = monitor.wait_for_close(
        WindowTarget("Streamlit"),
        backend_is_running=lambda: True,
        config=WindowMonitorConfig(appear_timeout_seconds=2.0),
    )

    assert result.status == WindowMonitorStatus.TIMEOUT


def test_polling_monitor_filters_browser_process_name_when_available():
    wrong = window("0x1", process_name="msedge")
    right = window("0x2", process_name="chrome")
    monitor = monitor_for((wrong, right), ())

    result = monitor.wait_for_close(
        WindowTarget("Streamlit", browser_kind=BrowserKind.CHROME),
        backend_is_running=lambda: True,
        config=config(stable_poll_count=1),
    )

    assert result.closed is True
    assert result.target == right


def test_polling_monitor_capture_failure_returns_error():
    def fail(target):
        raise RuntimeError("capture broke")

    monitor = PollingWindowMonitor(
        fail,
        clock=FakeClock(),
        sleeper=lambda seconds: None,
    )

    result = monitor.wait_for_close(
        WindowTarget("Streamlit"),
        backend_is_running=lambda: True,
        config=config(),
    )

    assert result.status == WindowMonitorStatus.ERROR
    assert result.closed is False
    assert "capture broke" in result.message


def test_polling_monitor_rejects_non_app_mode_target():
    monitor = monitor_for((window("0x1"),))

    result = monitor.wait_for_close(
        WindowTarget("", app_mode=False),
        backend_is_running=lambda: True,
        config=config(),
    )

    assert result.status == WindowMonitorStatus.UNSUPPORTED
    assert result.supported is False


def test_window_monitors_have_no_browser_control_surface():
    monitor = NoopWindowMonitor()
    polling = PollingWindowMonitor(lambda target: ())

    for instance in (monitor, polling):
        assert not hasattr(instance, "kill_browser")
        assert not hasattr(instance, "stop_browser")
        assert not hasattr(instance, "terminate_browser")
        assert not hasattr(instance, "close_window")
