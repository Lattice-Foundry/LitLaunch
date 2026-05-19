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

From the repository root, future CLI support is expected to use:

```powershell
litlaunch run examples/minimal_app/app.py
```

Until the CLI lands, this app is useful as a known-good target for
`LauncherConfig` and `StreamlitLauncher` command-building tests.
