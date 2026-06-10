# Quickstart

LitLaunch keeps the first run simple:

```powershell
litlaunch app.py --mode webapp
```

That local-first path gives you explicit backend ownership, Streamlit health
checks, browser capability detection, an app-window experience where supported,
isolated Chromium app-mode browser profiles, minimal Streamlit app chrome by
default, clean shutdown handling, and diagnostics/reporting without shell
scripts or custom runtime glue. Profiles, shortcuts, shutdown hooks,
packaged-app runtime workflows, trust modes, and report tooling are available
when the project needs more repeatable launch behavior or operational
visibility. LitLaunch can run inside
packaged/distributed Streamlit apps across Windows, Linux, and macOS, but it
does not create installers or replace packaging tools. Windows and Linux receive
first-party manual validation. macOS support is available with lighter
first-party validation while community coverage broadens.

## Run The Minimal Example

From a source checkout:

```powershell
litlaunch examples/minimal_app/app.py
```

The minimal example is a source-tree fixture. If LitLaunch is installed from a
wheel, point commands at your own Streamlit app instead. The explicit
`litlaunch run examples/minimal_app/app.py` form remains supported when you want
the command name in scripts or documentation.

Run as a Chromium app-mode window:

```powershell
litlaunch examples/minimal_app/app.py --mode webapp --browser auto
```

Inspect first:

```powershell
litlaunch report examples/minimal_app/app.py
```

For workflow guidance, use:

```powershell
litlaunch help
litlaunch help launch
litlaunch help diagnostics
```

Use `litlaunch --help` or a command-specific `--help` flag for reference help.

## Use Your Own App

```powershell
litlaunch app.py --mode webapp
```

LitLaunch hides Streamlit's default app toolbar/menu chrome by default through
Streamlit's supported `client.toolbarMode = "minimal"` setting. Add
`--show-streamlit-chrome` when you want Streamlit's default chrome visible:

```powershell
litlaunch app.py --mode webapp --show-streamlit-chrome
```

With Streamlit flags:

```powershell
litlaunch app.py --server.runOnSave true --theme.base=dark
```

With app arguments after Streamlit's separator:

```powershell
litlaunch app.py --server.runOnSave true -- --workspace demo
```

## Reusable Profiles

Profiles store repeatable launch settings in `litlaunch.toml`:

```powershell
litlaunch create profile
```

The Simple wizard defaults to the recommended app-window experience and writes
a `litlaunch.toml` profile after confirmation. It uses app-root defaults such
as `app.py` and the current folder name when they are available, while still
letting you confirm or change every prompt. Type `back` to revisit a previous
step, or `quit` to cancel. Choose Advanced mode when you need profile fields
such as host, port, monitor tuning, Streamlit flags, app args, working
directory, or extra environment variables. After saving a profile, the wizard
can optionally create a project-local launch shortcut.

```toml
[profiles.my-webapp]
app_path = "app.py"
title = "My App"
mode = "webapp"
browser = "edge"
trust_mode = "development"
port = 8501
auto_port = false
headless = true
runtime_event_log = ".litlaunch/runtime-events.log"
graceful_timeout = 15

[profiles.my-webapp.window_monitor]
enabled = true
appear_timeout = 60
poll_interval = 1
stable_polls = 2
```

Run, inspect, or show the launch plan for the profile:

```powershell
litlaunch --profile my-webapp
litlaunch command --profile my-webapp
litlaunch report --profile my-webapp
litlaunch create shortcut --profile my-webapp
```

The same shape can live under `[tool.litlaunch.profiles.my-webapp]` in
`pyproject.toml`. When both `litlaunch.toml` and `pyproject.toml` define
profiles, use `--config` to choose one explicitly.

CLI arguments override profile values:

```powershell
litlaunch --profile my-webapp --port 8502
```

Bare profile names such as `litlaunch my-webapp` are intentionally not
supported. Use `--profile` for profile launches so they remain clear and do not
conflict with paths or future commands.

Use `litlaunch report --profile my-webapp` for the default human-readable HTML
diagnostics report. It writes `.litlaunch/reports/litlaunch-report.html` unless
`--output` is provided. Use `litlaunch inspect --json` or
`litlaunch inspect --bundle` for machine-readable diagnostics and support
bundles. Generated reports, shortcuts, and managed browser scratch profiles live
under `.litlaunch/` by default so projects can ignore them with one
`.gitignore` entry.

Reports include runtime governance, runtime exposure, and transport security
posture. Local profiles can remain simple with `trust_mode = "development"` or
use `trust_mode = "strict_local"` for loopback-only tools. Intentional internal
network profiles should use `trust_mode = "internal_network"` plus explicit
`allow_network_exposure = true`.

## Generate A Support Page

Apps that want an in-app diagnostics/support surface can generate an editable
Streamlit page:

```python
from litlaunch import create_diagnostics_page

create_diagnostics_page(
    output_path="ui/litlaunch_diagnostics.py",
    app_name="My App",
    profile_name="my-webapp",
)
```

Then mount it wherever it fits the app's navigation:

```python
from ui.litlaunch_diagnostics import render_litlaunch_diagnostics

render_litlaunch_diagnostics()
```

The generated page is app-owned code. It imports Streamlit inside the generated
module, uses `theme="auto"` by default, and can be customized after generation
to match the host app.

Python integrations can use the same profile runtime path:

```python
from litlaunch import load_profile, run_profile

profile = load_profile("my-webapp")
result = run_profile(profile)
```

When `window_monitor.enabled = true`, `run_profile()` uses the monitored webapp
runner and applies the profile's graceful timeout and monitor config. When
`browser_window_monitor.enabled = true`, it uses the managed browser-window
runtime path. When monitoring is disabled, it uses the normal launcher runtime
path.

## Python API

```python
from litlaunch import LauncherConfig, StreamlitLauncher

config = LauncherConfig(
    app_path="app.py",
    title="My Streamlit App",
    mode="browser",
    cwd=".",
    extra_env={"APP_ENV": "local"},
)

session = StreamlitLauncher(config).run()

try:
    print(session.url)
finally:
    session.stop()
```

The returned `RuntimeSession` owns the backend process. Stop it explicitly.
`run()` is the friendly entry point; `start()` is the explicit lifecycle entry
point. Both return a live `RuntimeSession`.

Show the resolved launch behavior without starting the backend or opening a
browser:

```python
plan = StreamlitLauncher(config).build_launch_plan()

print(plan.command_display)
print(plan.app_url)
print(plan.health_url)
print(plan.streamlit_chrome_policy)
```

`build_launch_plan()` is intended for diagnostics, integration tests, and
configuration parity checks. It resolves ports and browser strategy but does
not launch Streamlit or a browser.

If a config binds Streamlit to a wildcard host such as `0.0.0.0` or `::`,
`plan.app_url` and `plan.health_url` use the loopback client URL that LitLaunch
can actually connect to, while the backend command still binds Streamlit to the
requested host.

## Custom Backend Commands

The default source-app command path is unchanged. Advanced integrations can
provide a command-only backend provider for packaged, frozen, or embedded
Streamlit apps:

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

plan = launcher.build_launch_plan()
print(plan.command_display)
```

The custom executable must bind the requested `context.host`/`context.port` and
expose Streamlit's health endpoint. LitLaunch still owns environment injection,
health checking, browser launch, and `RuntimeSession` shutdown behavior.
`description` is displayed in plans and diagnostics; `backend_kind` is optional
metadata for integrations and should be a short stable identifier when used.

`LauncherConfig.cwd` sets the backend process working directory.
`LauncherConfig.extra_env` adds child-process environment variables without
mutating `os.environ`. LitLaunch shutdown endpoint variables are injected after
`extra_env`, so LitLaunch-owned shutdown values win on collision.

Use `launcher.with_port(port)` when you need a copy of an existing launcher
with a fixed port. The returned launcher preserves injected managers, browser
helpers, renderer, and clock while leaving the original launcher unchanged.

`LauncherConfig.title` is used for display and app-window matching where
webapp monitoring applies. Browser-window monitoring relies primarily on a
managed temporary Chromium profile and pre-launch/post-launch window snapshots.
For Streamlit apps, match the title to
`st.set_page_config(page_title="...")`. If the actual app window title differs
significantly, `--monitor-window` may timeout; use `--title` to override the
expected title.

Prefer either structured `streamlit_flags` or raw `streamlit_args` for a given
Streamlit option. LitLaunch suppresses its own defaults when user options
overlap, but it does not deduplicate duplicate user options across both inputs.

## App-Side Shutdown Cleanup

Plain Streamlit apps do not need app-side setup for LitLaunch to stop the owned
backend when a monitored window closes. Apps that have real cleanup work can
opt into graceful cleanup when launched by LitLaunch:

```python
from litlaunch import LauncherRuntime, ShutdownHookStatus

runtime = LauncherRuntime.from_env()


@runtime.shutdown_hook(
    label="Closing resources",
    success_message="Resources closed",
    failure_message="Resource cleanup failed",
    color="success_green",
    console_visibility="normal",
)
def close_resources():
    ...


@runtime.shutdown_hook(label="Cloud backup sync")
def sync_backups():
    result = run_cloud_sync()
    if not result.configured:
        return ShutdownHookStatus(render=False)
    return ShutdownHookStatus(
        message="Cloud sync: Staged cloud sync completed.",
        console_visibility="normal",
        show_in_quiet=True,
    )


def finish_after_response(result):
    if result.ok:
        ...


runtime.set_shutdown_completion_callback(finish_after_response)
runtime.enable_shutdown_endpoint()
```

Shutdown hooks run before the endpoint responds to LitLaunch. Hook labels and
messages are app-owned presentation hints; console rendering uses the orange `Hook:` category so developer cleanup is separate from LitLaunch's own `Shutdown:`
and `Backend:` lifecycle messages. Hook status still uses the normal
`ok`/`warn`/`error` bracket colors, while hook message text stays unstyled for
readability. Hook color metadata is preserved on hook results for integrations.
Use `console_visibility="verbose"` for routine hook messages that should only
appear in verbose runs. Add `show_in_quiet=True` when a hook success message is
important enough to appear even when the runtime is launched with `--quiet`.
Hook failures are still shown in normal and quiet output with the standard
error, cause, and verbose-details hint.
When a hook needs a run-specific message, return `ShutdownHookStatus` instead of
printing directly to stdout. `ShutdownHookStatus(render=False)` suppresses
successful no-op hooks while still letting failures surface normally.
Hook failures are reported separately from core shutdown failures. The optional
completion callback runs after the endpoint response is sent to LitLaunch and is
useful when an app needs to schedule its own final exit or post-response
completion work. Duplicate shutdown requests do not rerun hooks or the
completion callback.

Normal console output is organized around bracketed status labels and runtime
categories such as `Backend:`, `Health:`, `Browser:`, `Runtime:`, `Monitor:`,
`Hook:`, and `Shutdown:`. Use `--verbose` when you want deeper troubleshooting
detail; normal mode stays concise for day-to-day launches.
