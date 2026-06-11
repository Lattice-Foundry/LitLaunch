from litlaunch.browsers import BrowserCapability, BrowserKind
from litlaunch.lifecycle import LaunchEvent, LaunchResult, LaunchState


def test_launch_event_is_immutable_state_record():
    event = LaunchEvent(
        state=LaunchState.PROCESS_RUNNING,
        message="started",
        timestamp=12.5,
    )

    assert event.state == LaunchState.PROCESS_RUNNING
    assert event.message == "started"
    assert event.timestamp == 12.5


def test_launch_result_carries_backend_result_details():
    event = LaunchEvent(LaunchState.HEALTHY, "healthy", 1.0)
    result = LaunchResult(
        ok=True,
        state=LaunchState.HEALTHY,
        command=("python", "-m", "streamlit"),
        pid=123,
        url="http://127.0.0.1:8501",
        message="ready",
        events=(event,),
    )

    assert result.ok is True
    assert result.state == LaunchState.HEALTHY
    assert result.events == (event,)
    assert result.browser is None
    assert result.browser_command is None
    assert result.browser_launched is False


def test_launch_result_can_include_browser_launch_fields():
    browser = BrowserCapability(
        kind=BrowserKind.CHROME,
        name="Chrome",
        executable_path="/usr/bin/chrome",
        available=True,
        supports_app_mode=True,
        supports_full_browser=True,
    )
    result = LaunchResult(
        ok=True,
        state=LaunchState.RUNNING,
        command=("python", "-m", "streamlit"),
        pid=123,
        url="http://127.0.0.1:8501",
        message="running",
        events=(),
        browser=browser,
        browser_command=("/usr/bin/chrome", "--app=http://127.0.0.1:8501"),
        browser_launched=True,
    )

    assert result.browser == browser
    assert result.browser_launched is True
