# LitLaunch

LitLaunch is a lightweight launcher and runtime layer for Streamlit
applications. It starts Streamlit backends, resolves browser launch strategy,
supports browser and Chromium app-mode flows, provides opt-in graceful shutdown,
and exposes diagnostics without hiding ownership or process behavior.

LitLaunch is developed and maintained by LatticeFoundry, a software division of
Sierra Cognitive Group, LLC. LitLaunch is not affiliated with Streamlit.

Current status: pre-beta internal integration and TestPyPI rehearsal readiness.
The runtime is usable for early integration work, but public API stability is
still being hardened.

## What It Solves

- Start Streamlit through explicit, shell-free command construction.
- Own and stop only the Streamlit backend process LitLaunch starts.
- Open a normal browser or Chromium app-mode window.
- Resolve Edge, Chrome/Chromium, and default-browser capability.
- Provide tokened loopback graceful shutdown hooks for app cleanup.
- Inspect local runtime readiness without launching the app.
- Keep failure output calm, concise, and actionable.

## Runtime Philosophy

LitLaunch is infrastructure, not magic orchestration.

- Backend ownership is explicit through `RuntimeSession`.
- Browser processes are launched but never owned, killed, or controlled.
- Window monitoring is observational only.
- Commands are argument tuples, never shell strings.
- Runtime dependencies remain stdlib-only.
- Diagnostics are sanitized and avoid raw environment dumps.

See [docs/philosophy.md](docs/philosophy.md) and
[docs/architecture.md](docs/architecture.md) for the full ownership model.

## Install

From a source checkout:

```powershell
python -m pip install -e .[dev]
```

After package publication, normal installs will use:

```powershell
python -m pip install litlaunch
```

The development environment currently uses Python 3.14.5. Package metadata
allows Python 3.10 and newer, and CI currently tests Python 3.10, 3.12, and
3.14 across Windows, Linux, and macOS.

## Quickstart

Run an app from the CLI:

```powershell
litlaunch run examples/minimal_app/app.py
```

The `examples/minimal_app` path exists in a source checkout. Installed package
users should point LitLaunch at their own Streamlit app path.

Run in Chromium app-mode:

```powershell
litlaunch run examples/minimal_app/app.py --mode webapp --browser auto
```

Inspect local readiness without launching:

```powershell
litlaunch inspect examples/minimal_app/app.py
```

Use the Python API:

```python
from litlaunch import LauncherConfig, StreamlitLauncher

config = LauncherConfig(
    app_path="app.py",
    title="My Streamlit App",
    mode="browser",
)

session = StreamlitLauncher(config).run()

try:
    print(f"Running at {session.url}")
finally:
    session.stop()
```

`run()` is the friendly common entry point. `start()` is the explicit lifecycle
entry point; both return a `RuntimeSession`.

## Feature Status

| Area | Status | Notes |
| --- | --- | --- |
| Streamlit backend launch | Beta foundation | Shell-free command construction and owned backend process management. |
| Browser mode | Beta foundation | Uses default browser or detected Chromium browser capability. |
| Chromium app-mode | Beta | Edge and Chrome/Chromium adapters first. |
| Browser fallback | Beta | Explicit browser choices can fall back unless disabled. |
| Graceful shutdown hooks | Beta | Opt-in app runtime, tokened loopback endpoint, fallback backend termination. |
| Inspect diagnostics | Beta foundation | Text, JSON, and sanitized bundle output. No app launch. |
| Window monitoring | Experimental | Opt-in, Windows Chromium app-mode first, observational only. |
| Packaging guidance | Notes only | LitLaunch supports packaged apps conceptually but does not own packaging. |
| HTML inspector/dashboard | Not implemented | Future work; no local diagnostics server exists today. |

## Common CLI Examples

```powershell
litlaunch version
litlaunch platform
litlaunch browsers

litlaunch command app.py --server.runOnSave true -- --workspace demo
litlaunch run app.py --mode browser
litlaunch run app.py --mode webapp --browser edge
litlaunch run app.py --mode webapp --monitor-window --title "My Streamlit App"

litlaunch inspect
litlaunch inspect app.py --json
litlaunch inspect app.py --bundle --output litlaunch-report.txt --force
```

Unknown arguments before Streamlit's `--` separator are passed through to
Streamlit. Arguments after `--` are passed to the app.

## App-Mode And Monitoring

`--mode webapp` opens a Chromium app-mode window when an app-mode capable
browser is available. `--monitor-window` is optional and currently strongest on
Windows with Edge or Chrome/Chromium. Monitoring observes app windows only; it
does not own or kill browser processes.

See [docs/browser_support.md](docs/browser_support.md) and
[docs/window_monitoring.md](docs/window_monitoring.md).

## Inspect And Troubleshooting

Use `litlaunch inspect` before launching or when a runtime fails. Inspect can
render plain text, JSON, or a sanitized support bundle:

```powershell
litlaunch inspect app.py
litlaunch inspect app.py --json --output litlaunch-report.json
litlaunch inspect app.py --bundle --output litlaunch-report.txt
```

See [docs/inspect.md](docs/inspect.md) and
[docs/troubleshooting.md](docs/troubleshooting.md).

## Documentation

- [Overview](docs/overview.md)
- [Philosophy](docs/philosophy.md)
- [Installation](docs/installation.md)
- [Quickstart](docs/quickstart.md)
- [CLI](docs/cli.md)
- [Browser Support](docs/browser_support.md)
- [Window Monitoring](docs/window_monitoring.md)
- [Inspect](docs/inspect.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Architecture](docs/architecture.md)
- [RoleThread Integration Notes](docs/integration/rolethread.md)
- [Packaging Notes](docs/integration/packaging_notes.md)

## Non-Goals

- Owning, killing, or controlling browser processes.
- Killing by process name, PID discovery, or port owner.
- Replacing Streamlit's CLI/config system.
- Running a local diagnostics dashboard or HTML inspector today.
- Owning PyInstaller, Nuitka, shortcut, or installer workflows.
- Adding terminal UI frameworks or heavy runtime dependencies.

## Versioning

LitLaunch uses `0.0.0` style internal versioning:

- Patch bumps are for fixes, cleanup, and basic hardening passes.
- Minor bumps are for larger internal milestones and feature work.
- Major versions are controlled manually by the project owner.

## License

MIT. Copyright (c) 2026 Sierra Cognitive Group, LLC.
