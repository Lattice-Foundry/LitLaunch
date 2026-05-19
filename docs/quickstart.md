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

[screenshot needed]
Capture: normal `litlaunch run examples/minimal_app/app.py --no-color` output.
Demonstrate: backend, health, browser, and runtime-ready phase output.
