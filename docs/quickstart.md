# Quickstart

## Run The Minimal Example

From a source checkout:

```powershell
litlaunch run examples/minimal_app/app.py
```

The minimal example is a source-tree fixture. If LitLaunch is installed from a
wheel, point commands at your own Streamlit app instead.

Run as a Chromium app-mode window:

```powershell
litlaunch run examples/minimal_app/app.py --mode webapp --browser auto
```

Inspect first:

```powershell
litlaunch inspect examples/minimal_app/app.py
```

## Use Your Own App

```powershell
litlaunch run app.py
```

With Streamlit flags:

```powershell
litlaunch run app.py --server.runOnSave true --theme.base=dark
```

With app arguments after Streamlit's separator:

```powershell
litlaunch run app.py --server.runOnSave true -- --workspace demo
```

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

Preview the resolved launch behavior without starting the backend or opening a
browser:

```python
plan = StreamlitLauncher(config).build_launch_plan()

print(plan.command_display)
print(plan.app_url)
print(plan.health_url)
```

`build_launch_plan()` is intended for diagnostics, integration tests, and
configuration parity checks. It resolves ports and browser strategy but does
not launch Streamlit or a browser.

`LauncherConfig.cwd` sets the backend process working directory.
`LauncherConfig.extra_env` adds child-process environment variables without
mutating `os.environ`. LitLaunch shutdown endpoint variables are injected after
`extra_env`, so LitLaunch-owned shutdown values win on collision.

Use `launcher.with_port(port)` when you need a copy of an existing launcher
with a fixed port. The returned launcher preserves injected managers, browser
helpers, renderer, and clock while leaving the original launcher unchanged.

`LauncherConfig.title` is used for display and browser/app-window matching
where monitoring applies. Choose a stable title for monitored webapp flows.
If the actual app window title differs significantly, `--monitor-window` may
timeout; use `--title` to override the expected title.

Prefer either structured `streamlit_flags` or raw `streamlit_args` for a given
Streamlit option. LitLaunch suppresses its own defaults when user options
overlap, but it does not deduplicate duplicate user options across both inputs.

## App-Side Shutdown Cleanup

Streamlit apps can opt into graceful cleanup when launched by LitLaunch:

```python
from litlaunch import LauncherRuntime

runtime = LauncherRuntime.from_env()


@runtime.shutdown_hook(label="Closing resources")
def close_resources():
    ...


def finish_after_response(result):
    if result.ok:
        ...


runtime.set_shutdown_completion_callback(finish_after_response)
runtime.enable_shutdown_endpoint()
```

Shutdown hooks run before the endpoint responds to LitLaunch. The optional
completion callback runs after the endpoint response is sent and is useful when
an app needs to schedule its own final exit or post-response completion work.
Duplicate shutdown requests do not rerun hooks or the completion callback.

[screenshot needed]
Capture: normal `litlaunch run examples/minimal_app/app.py --no-color` output.
Demonstrate: backend, health, browser, and runtime-ready phase output.
