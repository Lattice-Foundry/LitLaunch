import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType

import pytest

from litlaunch.events import (
    RuntimeEvent,
    RuntimeEventEmitter,
    compose_runtime_event_sinks,
    create_runtime_event_file_sink,
)


def test_runtime_event_normalizes_values_and_freezes_details():
    event = RuntimeEvent(
        name=" launch_planned ",
        category=" Launch ",
        level=" INFO ",
        message=" Launch planned ",
        timestamp=datetime(2026, 5, 24, tzinfo=timezone.utc),
        details={"port": 8501, "browser": "edge"},
    )

    assert event.name == "launch_planned"
    assert event.category == "launch"
    assert event.level == "info"
    assert event.message == "Launch planned"
    assert event.details == {"port": "8501", "browser": "edge"}
    assert isinstance(event.details, MappingProxyType)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"name": "  "}, "name"),
        ({"category": "telemetry"}, "category"),
        ({"level": "debug"}, "level"),
        ({"message": "  "}, "message"),
    ],
)
def test_runtime_event_rejects_invalid_values(kwargs, message):
    values = {
        "name": "launch_planned",
        "category": "launch",
        "level": "info",
        "message": "Launch planned",
        "timestamp": datetime(2026, 5, 24, tzinfo=timezone.utc),
    }
    values.update(kwargs)

    with pytest.raises(ValueError, match=message):
        RuntimeEvent(**values)


def test_runtime_event_emitter_without_sink_is_noop():
    emitter = RuntimeEventEmitter()

    emitter.emit(
        "launch_planned",
        category="launch",
        message="Launch planned",
        details={"port": 8501},
    )


def test_runtime_event_file_sink_writes_jsonl_and_creates_parent_dirs():
    with tempfile.TemporaryDirectory(prefix="litlaunch-events-test-") as directory:
        event_path = Path(directory) / "nested" / "runtime-events.log"
        sink = create_runtime_event_file_sink(event_path)
        event = RuntimeEvent(
            name="launch_planned",
            category="launch",
            level="info",
            message="Launch planned token=abc123",
            timestamp=datetime(2026, 5, 24, tzinfo=timezone.utc),
            details={"port": 8501, "api_token": "abc123", "mode": "webapp"},
        )

        sink(event)

        records = [
            json.loads(line)
            for line in event_path.read_text(encoding="utf-8").splitlines()
        ]
        assert records == [
            {
                "timestamp": "2026-05-24T00:00:00+00:00",
                "level": "info",
                "category": "launch",
                "name": "launch_planned",
                "message": "Launch planned token=<redacted>",
                "details": {
                    "api_token": "<redacted>",
                    "mode": "webapp",
                    "port": "8501",
                },
            }
        ]


def test_compose_runtime_event_sinks_calls_all_sinks_and_isolates_failure():
    events: list[RuntimeEvent] = []

    def failing_sink(event: RuntimeEvent) -> None:
        events.append(event)
        raise RuntimeError("sink failed")

    sink = compose_runtime_event_sinks(events.append, failing_sink)
    assert sink is not None
    emitter = RuntimeEventEmitter(sink)

    emitter.emit("backend_started", category="backend", message="Backend started.")

    assert [event.name for event in events] == ["backend_started", "backend_started"]
