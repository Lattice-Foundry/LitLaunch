# RoleThread Test Matrix

> INTERNAL / TEMPORARY INTEGRATION DOCUMENTATION
>
> This matrix is for beta validation. It is expected to change during
> integration work and is not a public support matrix.

## Conventions

- Record the exact LitLaunch version.
- Record RoleThread branch and commit.
- Use a clean virtual environment for package-install tests.
- Prefer `--no-color` when capturing console output for comparison.
- Do not kill unrelated browser or Streamlit processes during cleanup.
- Use `litlaunch inspect` before live runtime tests.

## Matrix

| Area | Scenario | Command shape | Expected result |
| --- | --- | --- | --- |
| Browser mode | Windows managed browser-window launch | `litlaunch run <app.py> --mode browser --browser edge` | Backend starts, managed browser window opens, close-to-shutdown works or fallback says Ctrl+C remains the shutdown path. |
| Browser fallback | Browser launch without monitor | `litlaunch run <app.py> --mode browser --browser edge --no-monitor-browser-window` | Backend starts, browser opens, CLI waits for Ctrl+C/backend exit. |
| Edge app-mode | Windows Edge webapp | `litlaunch run <app.py> --mode webapp --browser edge` | Backend starts, Edge app window opens, no browser ownership. |
| Chrome app-mode | Windows Chrome/Chromium webapp | `litlaunch run <app.py> --mode webapp --browser chrome` | Backend starts if Chrome/Chromium is available; unavailable case is clear. |
| Fallback | Auto browser fallback | `litlaunch run <app.py> --mode webapp --browser auto` | App-mode capable browser selected when available. |
| Fallback disabled | Explicit browser no fallback | `litlaunch run <app.py> --mode webapp --browser edge --no-browser-fallback` | Clear failure if Edge unavailable. |
| Backend failure | Missing app path | `litlaunch run missing.py` | Fail fast before health timeout. |
| Backend failure | App import/startup crash | RoleThread app with forced startup failure | Backend exits early; message suggests app crash or CLI args. |
| Health timeout | Slow or stuck startup | Reduced timeout if exposed by integration harness | Timeout message distinguishes running backend from early exit. |
| Monitor supported | Windows Edge app-mode monitoring | `litlaunch run <app.py> --mode webapp --browser edge --monitor-window` | Close app window, LitLaunch detects close and stops backend. |
| Browser monitor supported | Windows Edge managed browser-window monitoring | `litlaunch run <app.py> --mode browser --browser edge` | Close managed browser window, LitLaunch detects close and stops backend. |
| Monitor unsupported | Unsupported platform/provider | Same command on unsupported host | Explicit unsupported result; no silent success. |
| Graceful shutdown | Hooks succeed | Registered RoleThread hooks | Hooks run once, backend stops cleanly. |
| Forced fallback | Graceful shutdown unavailable | Fake or blocked endpoint | Backend fallback termination only applies to owned process. |
| Inspect HTML | Prelaunch human report | `litlaunch inspect <app.py> --html --output litlaunch-report.html` | No launch, useful readiness report. |
| Inspect JSON | Machine-readable report | `litlaunch inspect <app.py> --json` | Valid JSON, no token/env dump. |
| Inspect bundle | Support report | `litlaunch inspect <app.py> --bundle` | Copyable sanitized report. |
| Console quiet | Quiet runtime | `litlaunch run <app.py> --quiet` | Essential failures still visible; normal noise reduced. |
| Console verbose | Verbose runtime | `litlaunch run <app.py> --verbose` | More sanitized detail, no secrets. |
| Source checkout | Editable install | `python -m pip install -e .[dev]` | CLI and imports resolve from source. |
| Local wheel | Built wheel install | `python scripts/check_release.py` | Wheel installs and CLI smoke passes. |
| TestPyPI | Test package install | TestPyPI install command | Version and CLI smoke match package under test. |

## Manual Validation Notes

For app-mode and monitor-window tests:

- Confirm the browser window is an app-mode window, not a normal tab.
- Confirm closing the app window does not close unrelated browser windows.
- Confirm backend shutdown is visible in console output.
- Confirm no LitLaunch-owned backend remains after exit.
- Record console output for a successful RoleThread webapp launch with
  monitoring enabled after the app window has closed and backend shutdown has
  completed.

For browser-window tests:

- Confirm LitLaunch opens a managed top-level Edge/Chrome window.
- Confirm closing that specific window triggers graceful shutdown when observed.
- Confirm fallback output tells the user to press Ctrl+C when no managed window
  can be observed.
- Confirm no unrelated browser windows are closed or killed.

## Packaged And Unpackaged Expectations

Unpackaged source and editable installs should validate runtime mechanics
first. Packaged RoleThread workflows should be tested only after source and
local-wheel behavior is stable.

LitLaunch should remain packaging-agnostic. Package-specific environment setup,
shortcuts, update behavior, and user-data paths remain RoleThread or installer
concerns.
