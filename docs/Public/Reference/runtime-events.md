# Runtime Events

LitLaunch can optionally emit small structured runtime events to Python
integrations. This is useful for packaged apps that want product logs or support
trails for launch, health, browser, monitor, hook, shutdown, and port-release
milestones.

Runtime events are not telemetry. LitLaunch does not upload, rotate, or manage
event logs. Applications can either provide a Python sink or ask LitLaunch to
append a local JSONL event log for CLI/profile launches.

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

For simple local product logs, use the built-in JSONL file sink:

```python
from litlaunch import LauncherConfig, StreamlitLauncher

config = LauncherConfig(
    "app.py",
    runtime_event_log=".litlaunch/runtime-events.log",
)

launcher = StreamlitLauncher(config)
launcher.start()
```

Or compose it with a custom sink:

```python
from litlaunch import StreamlitLauncher, create_runtime_event_file_sink

launcher = StreamlitLauncher(
    "app.py",
    event_sink=create_runtime_event_file_sink(".litlaunch/runtime-events.log"),
)
launcher.start()
```

Profiles can use the same project-local path:

```toml
[profiles.my-webapp]
app_path = "app.py"
mode = "webapp"
runtime_event_log = ".litlaunch/runtime-events.log"
```

CLI launches can set the path per run:

```powershell
litlaunch app.py --event-log .litlaunch/runtime-events.log
```

Relative event log paths resolve against the LitLaunch project root for the
launch. Parent directories are created as needed, and events are appended as one
JSON object per line.

The sink receives `RuntimeEvent` objects with:

- `name`
- `category`
- `level`
- `message`
- `timestamp`
- `details`

Details are intended for safe operational metadata such as host, port, mode,
browser, PID, or hook label. LitLaunch does not include raw environment values
or secret-bearing command previews in runtime event details. The built-in file
sink applies lightweight redaction to sensitive-looking event messages and
detail keys before writing JSONL.

If your sink adds custom event details or writes events to disk, that app-owned
sink is responsible for redacting app-specific sensitive data before persisting
or sharing the log.

If the sink raises an exception, LitLaunch suppresses the failure and continues
the runtime lifecycle. In verbose console mode, LitLaunch emits one concise
warning that the event sink failed.
