# Runtime Events

LitLaunch can optionally emit small structured runtime events to Python
integrations. This is useful for packaged apps that want product logs or support
trails for launch, health, browser, monitor, hook, shutdown, and port-release
milestones.

Runtime events are not telemetry. LitLaunch does not persist, upload, rotate, or
manage event logs. The application owns any file writing or support-bundle
policy around the sink.

```python
from pathlib import Path

from litlaunch import RuntimeEvent, StreamlitLauncher

log_path = Path("runtime.log")


def write_runtime_event(event: RuntimeEvent) -> None:
    with log_path.open("a", encoding="utf-8") as stream:
        stream.write(
            f"{event.timestamp.isoformat()} "
            f"[{event.level}] {event.category}:{event.name} "
            f"{event.message}\n"
        )


launcher = StreamlitLauncher("app.py", event_sink=write_runtime_event)
launcher.start()
```

The sink receives `RuntimeEvent` objects with:

- `name`
- `category`
- `level`
- `message`
- `timestamp`
- `details`

Details are intended for safe operational metadata such as host, port, mode,
browser, PID, or hook label. LitLaunch does not include raw environment values
or secret-bearing command previews in runtime event details.

If the sink raises an exception, LitLaunch suppresses the failure and continues
the runtime lifecycle. In verbose console mode, LitLaunch emits one concise
warning that the event sink failed.
