# LitLaunch

LitLaunch is a lightweight launcher and runtime layer for Streamlit applications.
It is being built by LatticeFoundry for projects that need a clean, dependable
way to start Streamlit in browser or webapp-style modes without hiding process,
browser, or configuration behavior behind magic.

LitLaunch is developed and maintained by LatticeFoundry, a software division of
Sierra Cognitive Group, LLC.

Current status: early foundation. The package skeleton, public API shape,
configuration model, command construction, browser adapter boundary, and tests
are being established first. Full launcher lifecycle behavior will arrive in
staged passes.

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
model, while window monitoring remains future work.

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
