# Runtime Philosophy

LitLaunch follows a conservative runtime philosophy: explicit behavior,
deterministic boundaries, and safe ownership over convenience shortcuts.

## Ownership Boundaries

LitLaunch owns only the Streamlit backend process it starts.

It does not:

- kill browser processes
- kill by process name
- kill by port owner
- discover and kill unknown PIDs
- close browser windows
- assume that a browser process belongs to the app

This keeps failure recovery boring and safe.

## Browser Launch Is Not Browser Ownership

LitLaunch may launch Edge, Chrome/Chromium, or the system default browser. After
launch, the browser remains outside LitLaunch ownership. This is intentional:
browsers reuse processes, share profiles, restore windows, and may host many
unrelated sessions.

## Monitoring Is Observational

Window monitoring observes app-mode windows or LitLaunch-created managed
browser windows and reports lifecycle signals. Monitoring does not control
windows or browser processes. When a monitored window closes, `RuntimeSession` handles
backend shutdown through the normal graceful shutdown path. If LitLaunch cannot
identify a browser window confidently, it falls back to the manual Ctrl+C stop
path.

Experimental host sizing is a separate, explicit capability. On one narrow
eligible Windows webapp path, `initial` can apply one bounded height-only
change and `continuous` can accept meaningful later content-fit updates for the
same exact window. Neither policy weakens the observational monitoring boundary
or grants browser-process ownership.

## Stdlib-First

Runtime code is stdlib-first by default. Dev tooling uses test, lint, and
release tools. Runtime dependencies are avoided unless a capability clearly
justifies one; profile loading uses the lightweight `tomli` backport on Python
3.10 because `tomllib` enters the standard library in Python 3.11.

## Packaging-Agnostic

LitLaunch is meant to cooperate with packaged apps, not own packaging. PyInstaller,
Nuitka, uv, pipx, shortcuts, and installers should remain integration guidance
unless a small runtime hook is genuinely needed.

## Diagnostics And Sanitization

Diagnostics should help users and support teams understand the local runtime
without exposing secrets. Inspect output avoids raw environment dumps, shutdown
tokens, browser profile paths, and sensitive-looking values.

## Infrastructure Over Orchestration

LitLaunch should provide dependable primitives and a clean launch path. It
should not become a hidden supervisor that guesses, mutates, or controls
unrelated system state.
