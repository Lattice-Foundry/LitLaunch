# LitLaunch

LitLaunch is a lightweight launcher and runtime layer for Streamlit applications.
It is being built by LatticeFoundry for projects that need a clean, dependable
way to start Streamlit in browser or webapp-style modes without hiding process,
browser, or configuration behavior behind magic.

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

StreamlitLauncher(config).run()
```

For now, `StreamlitLauncher.build_command()` is the stable foundation API.
`run()` is intentionally not implemented until process lifecycle management is
designed and tested.

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

MIT
