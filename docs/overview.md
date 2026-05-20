# Overview

LitLaunch is a Streamlit runtime layer for projects that need predictable
startup, browser launch, diagnostics, and shutdown behavior without converting a
Streamlit app into a different application framework.

The core idea is small:

1. Build the Streamlit backend command explicitly.
2. Start one backend process.
3. Wait for Streamlit health.
4. Resolve a browser strategy.
5. Open the browser target.
6. Return a `RuntimeSession` that owns only the backend process.

LitLaunch should work with any app that can run with:

```powershell
streamlit run app.py
```

It should also reward better app structure through graceful shutdown hooks,
diagnostics, and cleaner launch flows.

## Current Scope

Implemented:

- Streamlit command construction
- Port selection and fixed-port validation
- Backend process ownership
- Streamlit health checking
- Browser/app-mode launch orchestration
- Edge, Chrome/Chromium, and default-browser capability detection
- Runtime session ownership
- Graceful shutdown hooks
- Text/JSON/HTML/bundle inspect diagnostics
- Lightweight console rendering
- Argparse CLI
- Optional Windows-first Chromium window monitoring

Not implemented:

- Local diagnostics dashboard/server
- Runtime log viewer
- Background monitor threads
- Packaging automation
- Browser automation
- Browser process ownership

[diagram needed]
Create: a one-page runtime flow from `LauncherConfig` to `RuntimeSession`.
Show: backend process ownership, browser launch without ownership, optional
inspect and shutdown paths.
