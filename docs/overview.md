# Overview

LitLaunch is a runtime-governance and operational-launch layer for Streamlit
applications. It helps projects get predictable startup, browser launch,
diagnostics, shutdown behavior, and runtime posture visibility without
converting a Streamlit app into a different application framework.

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
profiles, shortcuts, diagnostics, and cleaner launch flows. Normal localhost
workflows stay simple; packaged/distributed app workflows can reuse the same
runtime layer across Windows, Linux, and macOS; trust modes, exposure
diagnostics, and transport posture reporting are available when a project needs
stronger operational visibility. Windows and Linux receive first-party manual
validation; macOS support has limited validation until community testing
broadens.

## Current Scope

Implemented:

- Streamlit command construction
- Port selection and fixed-port validation
- Backend process ownership
- Streamlit health checking
- Browser/app-mode launch orchestration
- Edge, Chrome/Chromium, and default-browser capability detection
- Managed browser-window lifecycle for Chromium browser-mode launches
- Runtime session ownership
- Graceful shutdown hooks
- JSON/HTML/bundle inspect diagnostics
- Runtime governance, exposure, and transport posture diagnostics
- Profile wizard and lightweight project-local shortcut generation
- Packaged/distributed workflow support on Windows, Linux, and macOS
  through the same runtime primitives
- Lightweight console rendering
- Argparse CLI
- Optional Windows-first Chromium window monitoring

Out of scope:

- Local diagnostics dashboard/server
- Runtime log viewer
- Background monitor threads
- Packaging automation
- Installer creation
- Browser process ownership
- Browser automation

At runtime, `LauncherConfig` resolves into a launch plan, the backend process is
started under LitLaunch ownership, health is checked, and browser launch is
attempted without transferring browser ownership. `RuntimeSession` represents
the owned backend lifecycle; inspect/report workflows collect diagnostics
without starting that lifecycle.
