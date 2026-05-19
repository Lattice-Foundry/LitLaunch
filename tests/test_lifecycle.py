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
