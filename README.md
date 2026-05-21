# LitLaunch

LitLaunch is a lightweight launcher and runtime layer for Streamlit
applications. It starts Streamlit backends, resolves browser launch strategy,
supports browser and Chromium app-mode flows, provides opt-in graceful shutdown,
and exposes diagnostics without hiding ownership or process behavior.

LitLaunch is developed and maintained by LatticeFoundry, a software division of
Sierra Cognitive Group, LLC. LitLaunch is not affiliated with Streamlit.

Current status: beta stabilization and TestPyPI rehearsal readiness. The
runtime is usable for integration work, with the public API intended to
stabilize through the beta band.

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
- Runtime dependencies remain stdlib-first; Python 3.10 uses the lightweight
  `tomli` backport for TOML profile loading.
- Diagnostics are sanitized and avoid raw environment dumps.

See [docs/philosophy.md](docs/philosophy.md) and
[docs/architecture.md](docs/architecture.md) for the full ownership model.

## Install

From a source checkout:

```powershell
python -m pip install -e .[dev]
```

After changing versions or build metadata in a source checkout, rerun the
editable install command above. Python import metadata is produced during
installation, so stale editable installs can report an older package metadata
version even when `litlaunch.__version__` has changed in the source tree.

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
litlaunch examples/minimal_app/app.py
```

The `examples/minimal_app` path exists in a source checkout. Installed package
users should point LitLaunch at their own Streamlit app path. The explicit
`litlaunch run examples/minimal_app/app.py` form remains available for scripts
and power-user workflows.

Use workflow help when you want guidance instead of command reference:

```powershell
litlaunch help
litlaunch help launch
litlaunch help diagnostics
```

Use `litlaunch --help` or `litlaunch run --help` for argparse command and flag
reference.

Run in Chromium app-mode:

```powershell
litlaunch examples/minimal_app/app.py --mode webapp --browser auto
```

Inspect local readiness without launching:

```powershell
litlaunch report examples/minimal_app/app.py
```

Use a reusable project profile:

```powershell
litlaunch create profile
```

```toml
[profiles.my-webapp]
app_path = "app.py"
title = "My App"
mode = "webapp"
browser = "edge"
port = 8501
auto_port = false
headless = true
graceful_timeout = 15

[profiles.my-webapp.window_monitor]
enabled = true
appear_timeout = 60
poll_interval = 1
stable_polls = 2
```

```powershell
litlaunch --profile my-webapp
litlaunch command --profile my-webapp
litlaunch report --profile my-webapp
```

Profiles can live in `litlaunch.toml` or under `[tool.litlaunch]` in
`pyproject.toml`. Explicit CLI flags override profile values. Bare profile names
such as `litlaunch my-webapp` are intentionally not launch shorthand; use
`--profile` so profile-based launches stay unambiguous.

`litlaunch report` is the recommended human-facing diagnostics workflow. It
writes `litlaunch-report.html` by default. The explicit `litlaunch inspect
--html`, `--json`, and `--bundle` commands remain available for power-user and
machine-readable diagnostics.

Python integrations can run the same configured profile through `run_profile()`:

```python
from litlaunch import load_profile, run_profile

profile = load_profile("my-webapp")
result = run_profile(profile)

if result.exit_code:
    print(result.message)
```

If `profile.window_monitor` is enabled, `run_profile()` uses the monitored
webapp runner. Otherwise it starts the normal `StreamlitLauncher` path and
returns the same structured `MonitoredRunResult` shape.

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

For app-mode integrations that need close-to-shutdown behavior, LitLaunch also
provides a high-level monitored runner:

```python
from litlaunch import LauncherConfig, LaunchMode, run_monitored_webapp

result = run_monitored_webapp(
    LauncherConfig(
        app_path="app.py",
        title="My Streamlit App",
        mode=LaunchMode.WEBAPP,
        browser="edge",
    ),
    graceful_timeout_seconds=15,
)
```

The monitored runner observes the app window and returns a
`MonitoredRunResult`. It does not own, kill, close, or control browser windows.

Preview launch behavior without starting Streamlit or opening a browser:

```python
plan = StreamlitLauncher(config).build_launch_plan()
print(plan.command_display)
print(plan.app_url)
```

`build_launch_plan()` is useful for diagnostics, integration tests, and
configuration parity checks. Sensitive command and environment values are
redacted in display fields.

Advanced integrations can inject a backend command provider when a packaged or
embedded app needs a custom backend executable while LitLaunch still owns env
injection, health checks, browser launch, and `RuntimeSession` lifecycle:

```python
from litlaunch import BackendCommand, LauncherConfig, StreamlitLauncher


class PackagedBackend:
    def build_backend_command(self, context):
        return BackendCommand(
            (
                "dist/MyApp/MyApp.exe",
                "--host",
                context.host,
                "--port",
                str(context.port),
            ),
            description="packaged Streamlit backend",
            backend_kind="packaged",
        )


launcher = StreamlitLauncher(
    LauncherConfig(app_path="app.py"),
    backend_command_provider=PackagedBackend(),
)
```

Custom backend commands must bind the requested host/port and expose the
Streamlit health endpoint used by LitLaunch.

## Beta API Stability

The beta-stable public surfaces are the configuration, launcher, launch-plan,
profile, monitored-runner, backend-command-provider, app shutdown, and inspect
diagnostics APIs documented in [docs/architecture.md](docs/architecture.md).
Breaking changes remain possible before 1.0, but these APIs are intended to
stabilize through the 0.9x beta band. Window provider internals, low-level
browser/window matching details, and console presentation internals remain more
experimental.

## Feature Status

| Area | Status | Notes |
| --- | --- | --- |
| Streamlit backend launch | Beta | Shell-free command construction and owned backend process management. |
| Backend command providers | Beta | Optional command-only seam for packaged/embedded integrations. |
| Browser mode | Beta | Uses default browser or detected Chromium browser capability. |
| Chromium app-mode | Beta | Edge and Chrome/Chromium adapters first. |
| Browser fallback | Beta | Explicit browser choices can fall back unless disabled. |
| Graceful shutdown hooks | Beta | Opt-in app runtime, tokened loopback endpoint, optional app completion callback, fallback backend termination. |
| Inspect diagnostics | Beta | HTML, JSON, and sanitized bundle output. No app launch. |
| Window monitoring | Experimental | Opt-in, Windows Chromium app-mode first, observational only. |
| Packaging guidance | Notes only | LitLaunch supports packaged apps conceptually but does not own packaging. |
| Diagnostics dashboard | Not implemented | Future work; no local diagnostics server exists today. |

## Common CLI Examples

```powershell
litlaunch version
litlaunch platform
litlaunch browsers

litlaunch command app.py --server.runOnSave true -- --workspace demo
litlaunch run app.py --mode browser
litlaunch run app.py --mode webapp --browser edge
litlaunch run app.py --port 8501 --no-auto-port
litlaunch run app.py --mode webapp --monitor-window --title "My Streamlit App"
litlaunch run app.py --mode webapp --monitor-window --graceful-timeout 15
litlaunch run app.py --mode webapp --monitor-window --monitor-appear-timeout 90

litlaunch inspect
litlaunch inspect app.py --html --output litlaunch-report.html
litlaunch inspect app.py --json
litlaunch inspect app.py --bundle --output litlaunch-report.txt --force
```

Unknown arguments before Streamlit's `--` separator are passed through to
Streamlit. Arguments after `--` are passed to the app.

Python integrations can set `LauncherConfig.cwd` and `LauncherConfig.extra_env`
to control the backend child process without mutating global environment state.

## App-Mode And Monitoring

`--mode webapp` opens a Chromium app-mode window when an app-mode capable
browser is available. `--monitor-window` is optional and currently strongest on
Windows with Edge or Chrome/Chromium. Monitoring observes app windows only; it
does not own or kill browser processes.

See [docs/browser_support.md](docs/browser_support.md) and
[docs/window_monitoring.md](docs/window_monitoring.md).

## Inspect And Troubleshooting

Use `litlaunch inspect` before launching or when a runtime fails. Plain
`inspect` prints format guidance; HTML is the recommended human-readable
diagnostics report, JSON is for tools, and bundle output is for support:

```powershell
litlaunch inspect app.py --html --output litlaunch-report.html
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
- Running a local diagnostics dashboard or diagnostics server today.
- Owning PyInstaller, Nuitka, shortcut, or installer workflows.
- Adding terminal UI frameworks or heavy runtime dependencies.

## Versioning

LitLaunch uses `0.0.0` style internal versioning:

- Patch bumps are for fixes, cleanup, and basic hardening passes.
- Minor bumps are for larger internal milestones and feature work.
- Major versions are controlled manually by the project owner.

## License

MIT. Copyright (c) 2026 Sierra Cognitive Group, LLC.
