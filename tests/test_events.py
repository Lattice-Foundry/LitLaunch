from datetime import UTC, datetime
from types import MappingProxyType

import pytest

from litlaunch.events import RuntimeEvent, RuntimeEventEmitter


def test_runtime_event_normalizes_values_and_freezes_details():
    event = RuntimeEvent(
        name=" launch_planned ",
        category=" Launch ",
        level=" INFO ",
        message=" Launch planned ",
        timestamp=datetime(2026, 5, 24, tzinfo=UTC),
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
        "timestamp": datetime(2026, 5, 24, tzinfo=UTC),
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
