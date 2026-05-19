# LitLaunch Minimal Example App

This is a tiny Streamlit app used as a stable runtime fixture and demo target
for LitLaunch development. It confirms that a Streamlit runtime started and
shows a few basic runtime details.

It is intentionally small: no dashboards, no custom styling, no browser
automation, and no project-specific dependencies.

## Run With Streamlit

From this directory:

```powershell
streamlit run app.py
```

## Run With LitLaunch

From the repository root:

```powershell
litlaunch run examples/minimal_app/app.py
```

You can also ask the CLI for the source-checkout example path:

```powershell
litlaunch example
```

The example app is kept in the source tree as a development/demo fixture. It is
not currently guaranteed to be present in installed wheel layouts.

## Development Runtime

The current LitLaunch development environment uses Python 3.14.5.
