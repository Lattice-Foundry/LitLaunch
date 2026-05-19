# LitLaunch

LitLaunch is a lightweight launcher and runtime layer for Streamlit applications.
It is being built by LatticeFoundry for projects that need a clean, dependable
way to start Streamlit in browser or webapp-style modes without hiding process,
browser, or configuration behavior behind magic.

LitLaunch is developed and maintained by LatticeFoundry, a software division of
Sierra Cognitive Group, LLC.

Current status: active pre-alpha runtime hardening. LitLaunch already includes
typed launcher configuration, shell-free Streamlit command construction, port
management, platform and browser capability detection, backend process
ownership, graceful shutdown hooks, console rendering, and an argparse CLI.

The development environment currently uses Python 3.14.5. Package metadata
allows Python 3.10 and newer, but the active local hardening work is verified
against Python 3.14.5 unless noted otherwise.

LitLaunch is not affiliated with Streamlit.

## Intended Usage

```python
from litlaunch import LauncherConfig, StreamlitLauncher

config = LauncherConfig(
    app_path="app.py",
    title="My Streamlit App",
    mode="browser",
)

session = StreamlitLauncher(config).run()

print(f"Running at {session.url}")

try:
    ...
finally:
    session.stop()
```

`StreamlitLauncher.run()` returns a `RuntimeSession` so backend lifecycle
ownership stays explicit. LitLaunch owns only the Streamlit backend process it
started; browser processes are launched but not owned, monitored, stopped, or
killed by LitLaunch.

## Design Principles

- Explicit behavior over hidden magic
- Strong boundaries and separation of concerns
- Deterministic behavior over convenience shortcuts
- Fail-safe and defensive design
- Clear ownership of responsibility
- Lightweight, testable components
- Structured lifecycle management
- Safe process and resource handling
- Strong validation at system boundaries
- Maintainability over cleverness
- Readability over abstraction abuse

Commands are built as argument tuples, not shell strings. Runtime dependencies
are intentionally minimal.

LitLaunch also includes a platform capability layer for runtime diagnostics and
future browser fallback decisions. It reports normalized OS, architecture,
Python runtime details, and conservative launch capability flags.

Browser capability detection now covers initial Edge, Chrome, Chromium, and
default-browser availability. Detection is used for compatibility planning and
future runtime launch behavior; it does not launch browsers.

LitLaunch can now orchestrate backend startup, Streamlit health checks, browser
capability resolution, browser launch, and explicit runtime-session ownership.
Browser mode and Chromium app-mode are supported through command-based adapters.
Advanced Streamlit flags and app arguments remain part of the compatibility
model, while window monitoring remains future work. LitLaunch injects its
Streamlit defaults only when the user has not supplied the equivalent
Streamlit flag, so explicit user flags remain the authority. The CLI validates
that the target app file exists before starting the backend.

## Graceful Shutdown

Streamlit apps can opt in to cleanup hooks when launched by LitLaunch:

```python
from litlaunch import LauncherRuntime

runtime = LauncherRuntime.from_env()


@runtime.shutdown_hook(label="Closing resources", color="streamlit_blue")
def close_resources():
    ...


runtime.enable_shutdown_endpoint()
```

This is safe when the app is run with plain `streamlit run`: registration still
works and the endpoint simply does not start. During `RuntimeSession.stop()`,
LitLaunch requests graceful shutdown first, then falls back to terminating only
the owned Streamlit backend process if needed. Browser processes are not killed.
The `color` metadata is stored now for future console/theme rendering.

## Console UX

LitLaunch includes a lightweight stdlib-only console renderer for launcher,
runtime, diagnostics, and shutdown-hook messages. The default primary color is
`streamlit_blue` with an indigo accent, and output can run in `quiet`, `normal`,
or `verbose` modes. Plain/no-color output is supported, including `NO_COLOR`,
without adding Rich, Textual, or Colorama.

## CLI

LitLaunch includes a small argparse-based CLI with no external command-line
framework dependencies:

```powershell
litlaunch version
litlaunch platform
litlaunch browsers
litlaunch run examples/minimal_app/app.py
litlaunch run app.py --mode webapp --browser auto
litlaunch run app.py --streamlit-flag server.maxUploadSize=200 --app-arg demo
```

The CLI is intentionally thin over the Python runtime APIs. A fuller inspector
or diagnostics dashboard is future work. `litlaunch example` reports the
minimal example path when running from a source checkout; installed wheels may
not include the repository-level example directory.

## Examples

The [minimal example app](examples/minimal_app) is a tiny Streamlit target for
manual launcher checks, documentation, and future smoke/runtime tests. It is a
fixture first: small, stable, and intentionally free of showcase complexity.

## Versioning

LitLaunch uses `0.0.0` style internal versioning:

- Patch bumps are for fixes, cleanup, and basic hardening passes.
- Minor bumps are for larger internal milestones and feature work.
- Major versions are controlled manually by the project owner.

## License

MIT. Copyright (c) 2026 Sierra Cognitive Group, LLC.
