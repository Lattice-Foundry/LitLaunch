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
The API is usable for early adopters, but still evolving while LitLaunch is in
pre-alpha.

The development environment currently uses Python 3.14.5. Package metadata
allows Python 3.10 and newer. CI tests the supported range on Python 3.10,
3.12, and 3.14 across Windows, Linux, and macOS.

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

Stable utility classes such as `PortManager`, `ProcessManager`,
`ManagedProcess`, `HealthChecker`, and `StreamlitCommandBuilder` are exported
for dependency-injection and testing use cases. Diagnostics helpers are still
intentionally lightweight and may evolve before beta.

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
model, while window monitoring remains opt-in API functionality. LitLaunch injects its
Streamlit defaults only when the user has not supplied the equivalent
Streamlit flag, so explicit user flags remain the authority. The CLI validates
that the target app file exists before starting the backend.
Raw Streamlit passthrough is supported before Streamlit's own `--` separator,
and app arguments remain after that separator.

Known provisional areas are intentionally called out: diagnostics are lightweight
plain-text helpers for now, a web inspector/dashboard is future work, richer
window-monitor defaults are future work, and packaging/install guidance is
future work.

## Window Monitoring

LitLaunch includes the first opt-in window monitoring foundation for future
Chromium app-mode runtime flows. The current API provides observation-only
contracts, a no-op monitor for unsupported environments, a fake-friendly polling
monitor foundation, and a Windows Chromium HWND provider built on stable Win32
APIs available on Windows 10 and Windows 11.
`litlaunch run --mode webapp --monitor-window` can opt into waiting for the
app-mode window and stopping the owned Streamlit backend when that window closes.
Window monitors observe app windows only; `RuntimeSession` remains responsible
for graceful backend shutdown, and LitLaunch never owns, stops, or kills browser
processes.

Manual Windows smoke checklist:

```powershell
litlaunch run examples/minimal_app/app.py --mode webapp --monitor-window --browser edge
# Close the app-mode window and verify the CLI exits after graceful shutdown.
litlaunch run examples/minimal_app/app.py --mode webapp --monitor-window --browser chrome
# Run Chrome only when Chrome/Chromium is installed and detected.
litlaunch run examples/minimal_app/app.py --mode browser --monitor-window
# Expected: rejected because monitoring is webapp-mode only.
```

For unsupported platforms or unavailable monitors, explicit `--monitor-window`
requests fail clearly instead of continuing silently.

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
runtime, diagnostics, and shutdown-hook messages. Output can run in `quiet`,
`normal`, or `verbose` modes. Plain/no-color output is supported, including
`NO_COLOR`, without adding Rich, Textual, or Colorama.

LitLaunch exposes stable developer-facing theme color names:
`streamlit_blue`, `streamlit_blue_light`, `terminal_green`, `powershell_red`,
`muted_amber`, `muted_gray`, and `success_green`. The console prefix text is
fixed as `[LitLaunch]`; its color is themeable, but the product name is not.
The default prefix/brand color is `terminal_green`, status labels use
`streamlit_blue`, errors use `powershell_red`, and shutdown hooks can store
these named colors in their `color` metadata for renderer support.

Normal runtime output is grouped into concise phases such as backend startup,
health checks, browser launch, window monitoring, and shutdown. Where useful,
LitLaunch includes elapsed timings like `ready in 1.2s` without changing
runtime ownership or adding terminal UI dependencies.

## CLI

LitLaunch includes a small argparse-based CLI with no external command-line
framework dependencies:

```powershell
litlaunch version
litlaunch platform
litlaunch browsers
litlaunch inspect
litlaunch inspect examples/minimal_app/app.py
litlaunch inspect --json
litlaunch inspect examples/minimal_app/app.py --bundle
litlaunch inspect app.py --json --output litlaunch-report.json
litlaunch inspect app.py --bundle --output litlaunch-report.txt
litlaunch inspect app.py --bundle --output litlaunch-report.txt --force
litlaunch command examples/minimal_app/app.py --server.runOnSave true
litlaunch run examples/minimal_app/app.py
litlaunch run examples/minimal_app/app.py --dry-run --theme.base=dark
litlaunch run app.py --mode webapp --browser auto
litlaunch run app.py --mode webapp --monitor-window
litlaunch run app.py --mode webapp --monitor-window --title "My Streamlit App"
litlaunch run app.py --streamlit-flag server.maxUploadSize=200 -- --demo
```

The CLI is intentionally thin over the Python runtime APIs. `litlaunch example`
reports the minimal example path when running from a source checkout; installed
wheels may not include the repository-level example directory, and the command
fails clearly when that fixture is unavailable.

Explicit browser choices use fallback only when `allow_browser_fallback` is true
or `--no-browser-fallback` is not set. In webapp mode, fallback remains limited
to app-mode-capable browsers. In browser mode, fallback may eventually resolve to
the system default browser. `--monitor-window` is valid only with
`--mode webapp`; unsupported monitors fail clearly instead of silently ignoring
explicit user intent. Use `--title` when the app-mode browser window title
differs from LitLaunch's default `Streamlit App` title.

## Inspect

`litlaunch inspect` prints a text-only diagnostics report for the local runtime
environment. `litlaunch inspect app.py` adds target-aware checks such as app path
validation, command preview, app URL preview, health URL preview, and browser
resolution. Inspect does not launch Streamlit, open browsers, start local
servers, or dump environment variables. `--json` emits machine-readable output
for tools and automation. `--bundle` emits a concise sanitized support report
for issues or support requests. Both formats render from the same structured
diagnostics report and redact sensitive-looking values. JSON and bundle reports
can be written with `--output`; existing files are not overwritten unless
`--force` is supplied. Output files are UTF-8 text and remain sanitized. A richer
HTML inspector/dashboard may be added later on top of the same structured
diagnostics data.

## Examples

The [minimal example app](examples/minimal_app) is a tiny Streamlit target for
manual launcher checks, documentation, and future smoke/runtime tests. It is a
fixture first: small, stable, and intentionally free of showcase complexity.
Example files are source-checkout fixtures unless they are explicitly packaged
in a later release.

## Release Hygiene / Build Verification

Install development tooling with:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .[dev]
```

Run the release hygiene gate with:

```powershell
.\.venv\Scripts\python.exe scripts\check_release.py
```

The script builds the source distribution and wheel, runs `twine check`,
inspects archive contents for required files and excluded junk, then installs
the built wheel into a temporary virtual environment for import and basic CLI
smoke checks. TestPyPI/PyPI publishing is future work.

## Continuous Integration

GitHub Actions runs the project protection gate on pushes, pull requests, and
manual dispatches. The CI test job installs `.[dev]`, runs pytest, Ruff linting,
and Ruff format checks across Windows, Linux, and macOS on Python 3.10, 3.12,
and 3.14. A separate build job runs `scripts/check_release.py` on Linux to
validate wheel/sdist builds, metadata, archive contents, and installed-package
CLI smoke checks. CI uses current Node 24-backed first-party actions and bounded
job timeouts to keep hosted runs low-noise. CI does not publish to TestPyPI or
PyPI yet.

## Versioning

LitLaunch uses `0.0.0` style internal versioning:

- Patch bumps are for fixes, cleanup, and basic hardening passes.
- Minor bumps are for larger internal milestones and feature work.
- Major versions are controlled manually by the project owner.

## License

MIT. Copyright (c) 2026 Sierra Cognitive Group, LLC.
