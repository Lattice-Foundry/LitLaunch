# RoleThread / LitLaunch Manual Test Plan

> INTERNAL / TEMPORARY INTEGRATION DOCUMENTATION
>
> This plan is for real-world beta validation of LitLaunch through the
> RoleThread integration sandbox. It is expected to change during RC work and
> is not a public support matrix.

## Purpose

RoleThread is the live integration target for LitLaunch because it exercises
browser ownership, Streamlit lifecycle management, managed browser-window
monitoring, app-window monitoring, shutdown hooks, profiles, shortcuts,
diagnostics, runtime governance, and packaged-style workflows.

This plan focuses on manual behavior the automated test suite cannot fully
prove: real browser windows, real OS window handles, real shutdown behavior,
real console output, generated shortcuts, diagnostics UX, and packaged/source
runtime assumptions.

## Test Setup

Run these commands before a manual test session:

```powershell
cd X:\dev\rolethread-test
.\.venv\Scripts\Activate.ps1
python -c "import litlaunch; print(litlaunch.__version__); print(litlaunch.__file__)"
git status --short
```

Expected:

- `litlaunch.__file__` points into `X:\dev\litlaunch\src\litlaunch`.
- RoleThread is running from `X:\dev\rolethread-test`.
- Commands below use the activated `litlaunch` executable unless stated
  otherwise.

If shell activation is unavailable, use this command shape instead:

```powershell
X:\dev\rolethread-test\.venv\Scripts\python.exe -m litlaunch.cli app.py
```

Known RoleThread profiles in the sandbox:

- `rolethread-webapp`: Edge app-window/webapp mode with app-window monitoring.
- `rolethread-browser`: browser mode profile.

Useful cleanup commands:

```powershell
Remove-Item .\litlaunch-report.html -ErrorAction SilentlyContinue
Remove-Item .\rolethread-webapp-test.bat -ErrorAction SilentlyContinue
Get-ChildItem $env:TEMP -Directory | Where-Object Name -like "litlaunch*"
```

Status legend:

- `Complete`: manually verified.
- `Not run`: not manually verified yet.

## A. Smoke Tests: 10-15 Minutes

Must-run tests for every new LitLaunch build tested against RoleThread.

| ID | Status | Effort | Command / Action | Expected Result | Record If It Fails | Severity | Feature Area |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SMK-01 | Complete | Light | `litlaunch version` and `python -c "import litlaunch; print(litlaunch.__version__); print(litlaunch.__file__)"` | Version is the build under test and import path points to `X:\dev\litlaunch\src\litlaunch`. | Version, import path, active venv path. | Blocker | Source/install |
| SMK-02 | Complete | Light | `litlaunch app.py` | One browser window opens, RoleThread loads, console says browser window is monitored or clearly falls back, closing the managed browser window triggers graceful shutdown when detected. | Full console output, browser used, whether existing browser was open. | Blocker | Browser lifecycle |
| SMK-03 | Complete | Light | `litlaunch app.py`, then press `Ctrl+C` instead of closing the browser. | Backend stops cleanly, hook path runs, port releases. | Console excerpt from `Ctrl+C` through port release. | Blocker | Shutdown |
| SMK-04 | Complete | Light | `litlaunch app.py --mode webapp` | One Edge app window opens, `Monitor: watching app window...` appears, closing the app window triggers graceful shutdown. | Console output and screenshot if monitor does not start. | Blocker | Webapp lifecycle |
| SMK-05 | Complete | Light | `litlaunch --profile rolethread-webapp` | RoleThread webapp profile launches one app window, close-to-shutdown works, RoleThread shutdown hook runs. | Profile name, console output, hook lines. | Blocker | Profiles/hooks |
| SMK-06 | Complete | Light | `litlaunch report --profile rolethread-webapp --output litlaunch-report.html --force` then open `.\litlaunch-report.html`. | HTML report is generated, standalone, readable, and includes governance/exposure/transport sections. | Report path, screenshot, missing sections. | High | Diagnostics/report |
| SMK-07 | Complete | Light | `litlaunch inspect --profile rolethread-webapp --json` | Valid JSON prints without launching the app. | JSON parse issue or unexpected launch behavior. | High | Diagnostics/JSON |

## B. Core Lifecycle Tests: 30-60 Minutes

Focus on launch ownership, close detection, hooks, and repeatability.

| ID | Status | Effort | Command / Action | Expected Result | Record If It Fails | Severity | Feature Area |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LIFE-01 | Complete | Medium | Close all Edge windows, then run `litlaunch app.py --browser edge`. | Managed Edge browser window opens without sync/first-run prompts; closing it stops backend. | Whether prompt appears, HWND monitor messages, console output. | Blocker | Managed browser profile |
| LIFE-02 | Complete | Medium | Open a normal Edge window first, then run `litlaunch app.py --browser edge`. | LitLaunch opens a separate managed window; existing Edge session is not hijacked; close-to-shutdown still works. | Existing Edge state, new window behavior, fallback text. | High | Browser isolation |
| LIFE-03 | Complete | Medium | `litlaunch app.py --browser edge --no-monitor-browser-window` | Browser opens; console tells user to press `Ctrl+C`; closing browser should not be required to stop backend; `Ctrl+C` stops cleanly. | Console wording and shutdown result. | High | Browser fallback |
| LIFE-04 | Complete | Medium | `litlaunch app.py --browser default` | Default-browser launch works or clearly falls back to `Ctrl+C` ownership without duplicate windows. | Browser chosen, monitor/fallback messaging. | Medium | Browser selection |
| LIFE-05 | Complete | Medium | `litlaunch app.py --browser chrome` if Chrome is installed. | Chrome/Chromium path behaves like Edge where supported, or failure/fallback is clear. | Chrome availability, prompt behavior, monitor result. | Medium | Browser selection |
| LIFE-06 | Complete | Medium | `litlaunch app.py --mode webapp --browser edge` | App-window close triggers graceful shutdown; unrelated Edge windows remain untouched. | Window count before/after, console output. | Blocker | Webapp monitor |
| LIFE-07 | Complete | Medium | `litlaunch --profile rolethread-webapp`, then close app window. | RoleThread hook runs once, backend stops, port 8501 releases. | Hook count, port status, console output. | Blocker | Profile lifecycle |
| LIFE-08 | Complete | Medium | `litlaunch --profile rolethread-browser`, then close browser or press `Ctrl+C`. | Browser profile respects browser-mode lifecycle; `Ctrl+C` always stops cleanly. | Whether monitor is enabled by profile and final shutdown lines. | High | Profile lifecycle |
| LIFE-09 | Complete | Medium | Run `litlaunch app.py --mode webapp`, close window, immediately run it again. Repeat 3 times. | Each cycle starts, closes, runs hooks, and releases the port. | Cycle number and first failing output. | High | Repeatability |
| LIFE-10 | Complete | Medium | `litlaunch app.py --verbose`, then close managed browser window. | Verbose-only startup/shutdown details appear; normal lifecycle still succeeds. | Verbose output around monitor and shutdown. | Medium | Verbose lifecycle |

Port release check after any lifecycle test:

```powershell
netstat -ano | Select-String ":8501"
```

Expected: no owned Streamlit backend remains after shutdown.

## C. Diagnostics And Governance Tests: 30-60 Minutes

Run these without launching the app unless noted.

| ID | Status | Effort | Command / Action | Expected Result | Record If It Fails | Severity | Feature Area |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DIAG-01 | Complete | Light | `litlaunch inspect --profile rolethread-webapp` | Human guidance says diagnostics artifacts are available; no legacy full text report. | Output text. | Medium | Inspect UX |
| DIAG-02 | Complete | Light | `litlaunch inspect --profile rolethread-webapp --json > .\inspect-rolethread.json` | JSON includes runtime governance, exposure, transport security, profile/target info, and no obvious secrets. | JSON file excerpt and missing keys. | High | JSON diagnostics |
| DIAG-03 | Complete | Light | `litlaunch report --profile rolethread-webapp --open --force` | HTML opens, sections are readable, long paths wrap, privacy warning is visible. | Screenshot and generated file path. | High | HTML diagnostics |
| DIAG-04 | Complete | Medium | `litlaunch inspect app.py --host 127.0.0.1 --trust-mode strict_local --json` | Reports loopback/local posture without alarming network-exposure language. | Runtime Governance / Runtime Exposure excerpt. | Medium | Trust mode |
| DIAG-05 | Complete | Medium | `litlaunch inspect app.py --host 0.0.0.0 --trust-mode strict_local --json` | Prints valid JSON and reports strict-local violation/error posture. | JSON severity and recommendation. | High | Exposure guardrail |
| DIAG-06 | Complete | Medium | `litlaunch inspect app.py --host 0.0.0.0 --trust-mode internal_network --json` | Prints valid JSON and reports that network exposure would require acknowledgement before launch. | JSON posture fields. | High | Governance |
| DIAG-07 | Complete | Medium | `litlaunch inspect app.py --host 0.0.0.0 --trust-mode internal_network --allow-network-exposure --json` | Reports acknowledged network-visible posture with warning. | Acknowledgement and severity fields. | High | Governance |
| DIAG-08 | Complete | Medium | `litlaunch report app.py --host 0.0.0.0 --trust-mode internal_network --allow-network-exposure --force` | HTML report clearly warns about network-visible exposure. | Screenshot of governance/exposure sections. | High | Report UX |
| DIAG-09 | Complete | Medium | `litlaunch inspect app.py --host 0.0.0.0 --trust-mode internal_network --allow-network-exposure --streamlit-flag server.sslCertFile=cert.pem --streamlit-flag server.sslKeyFile=key.pem --json` | Transport Security reports Streamlit-native TLS configured and does not imply authentication. | Transport section excerpt. | Medium | TLS posture |
| DIAG-10 | Complete | Medium | `litlaunch inspect app.py --host 0.0.0.0 --trust-mode internal_network --allow-network-exposure --streamlit-flag server.sslCertFile=cert.pem --json` | Transport Security reports incomplete TLS config as warning/error. | Severity and recommendation. | Medium | TLS posture |
| DIAG-11 | Complete | Medium | `litlaunch inspect --profile rolethread-webapp --bundle --output rolethread-support.txt --force` then inspect the file. | Bundle includes privacy disclaimer, redaction wording, governance posture, and no obvious secrets. | Bundle excerpt and sensitive-looking values. | High | Support bundle |

Cleanup:

```powershell
Remove-Item .\inspect-rolethread.json, .\rolethread-support.txt, .\litlaunch-report.html -ErrorAction SilentlyContinue
```

## D. Console And Output Tests: 20-40 Minutes

Validate what humans actually see while running RoleThread.

| ID | Status | Effort | Command / Action | Expected Result | Record If It Fails | Severity | Feature Area |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CON-01 | Complete | Light | `litlaunch app.py` | Normal output is concise; Streamlit native URL block remains familiar; LitLaunch lines use status blocks. | Console screenshot. | Medium | Console normal |
| CON-02 | Complete | Light | `litlaunch app.py --verbose` | Verbose-only startup/shutdown details appear; no secret values. | Console excerpt. | Medium | Console verbose |
| CON-03 | Complete | Light | `litlaunch app.py --quiet` | Nonessential output is suppressed; important failures still show if triggered. | Output and whether shutdown remains understandable. | Medium | Console quiet |
| CON-04 | Complete | Light | `litlaunch app.py --no-color` | No ANSI escapes; labels remain aligned and readable. | Captured output. | Low/Polish | Console no-color |
| CON-05 | Complete | Medium | `litlaunch app.py --host 0.0.0.0 --trust-mode internal_network --allow-network-exposure` then stop with `Ctrl+C`. | Runtime warning mentions network exposure and plaintext HTTP if TLS is absent; `Ctrl+C` reports a user stop, not an error. | Warning text and shutdown excerpt. | High | Security messaging |
| CON-06 | Complete | Medium | `litlaunch app.py --host 0.0.0.0 --trust-mode strict_local --allow-network-exposure` | Fails before backend start; normal error is bounded to error/cause/verbose guidance. | Full error output. | Blocker | Error formatting |
| CON-07 | Complete | Medium | Force a missing app path: `litlaunch missing.py` | Error is clear, cause is shown, and output suggests verbose/diagnostics without a giant traceback. | Full error output. | High | Error formatting |
| CON-08 | Complete | Medium | Close RoleThread via managed browser window or webapp window. | Dynamic RoleThread hook messages render through LitLaunch status grammar once RoleThread migrates; current direct `[RoleThread]` lines should be recorded as RoleThread-side artifacts. | Hook lines and whether they are direct prints. | Medium | Hook presentation |
| CON-09 | Complete | Medium | `litlaunch app.py --verbose`, then close window. | Verbose-only hook success/details show only in verbose; errors would remain visible in normal. | Hook section output. | Medium | Hook visibility |

## E. Profile And Shortcut Tests: 30-60 Minutes

Validate reusable launch workflows and generated artifacts.

| ID | Status | Effort | Command / Action | Expected Result | Record If It Fails | Severity | Feature Area |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PROF-01 | Not run | Light | `litlaunch command --profile rolethread-webapp` | Prints planned launch command without starting runtime. | Command output. | Medium | Profile preview |
| PROF-02 | Not run | Light | `litlaunch inspect --profile rolethread-webapp --json` | Profile loads cleanly and diagnostics include profile context. | Profile loading error or missing context. | High | Profile loading |
| PROF-03 | Not run | Medium | `litlaunch --profile rolethread-webapp` | Profile launches one app window and close-to-shutdown works. | Console output and window behavior. | Blocker | Profile launch |
| PROF-04 | Not run | Medium | `litlaunch --profile rolethread-browser` | Browser profile launches and `Ctrl+C` remains reliable. | Browser behavior and shutdown output. | High | Profile launch |
| PROF-05 | Not run | Light | `litlaunch --profile does-not-exist` | Clean profile-not-found error, no backend start. | Error text. | Medium | Profile errors |
| PROF-06 | Not run | Medium | `litlaunch create shortcut --profile rolethread-webapp --dry-run` | Shows shortcut plan and content; writes nothing. | Output and whether file appeared. | Medium | Shortcut dry-run |
| PROF-07 | Not run | Medium | `litlaunch create shortcut --profile rolethread-webapp --output .\rolethread-webapp-test.bat --force` then run `.\rolethread-webapp-test.bat`. | Shortcut starts RoleThread from correct working directory; lifecycle matches profile launch. | Shortcut file content and console output. | High | Shortcut launch |
| PROF-08 | Not run | Medium | Run `.\rolethread-webapp-test.bat` from a different current directory. | Working directory is still correct and app assets resolve. | Starting directory and any missing-file errors. | High | Shortcut cwd |
| PROF-09 | Not run | Medium | Create a temporary folder path with spaces, copy the shortcut there, and run it. | Quoting survives spaces in path. | Shortcut path and error text. | Medium | Shortcut quoting |
| PROF-10 | Not run | Medium | `litlaunch create profile --dry-run` and walk Simple mode without writing. | App-root defaults detect `app.py`, folder-derived title/name, app-window default, and optional shortcut is not written. | Prompt sequence and preview. | Medium | Profile wizard |

Cleanup:

```powershell
Remove-Item .\rolethread-webapp-test.bat -ErrorAction SilentlyContinue
```

## F. Packaged / Installer Tests: Effort Depends On Availability

Run these when a packaged RoleThread build or installer artifact is available.

| ID | Status | Effort | Command / Action | Expected Result | Record If It Fails | Severity | Feature Area |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PKG-01 | Not run | Heavy | Build or obtain the packaged RoleThread artifact using RoleThread packaging docs, such as `installer\windows\scripts\build_bundle.ps1` if that workflow is current. | Build completes with packaged LitLaunch dependency resolved as intended. | Build log and exact source commit. | High | Packaged build |
| PKG-02 | Not run | Heavy | Launch packaged RoleThread through its packaged launcher or installed shortcut. | One intended browser/app window opens, working directory and app data paths resolve. | Installer path, launch path, console/log output. | Blocker | Packaged launch |
| PKG-03 | Not run | Heavy | Close packaged app window. | Graceful shutdown hooks run and backend exits. | Logs, hook output, remaining process list. | Blocker | Packaged shutdown |
| PKG-04 | Not run | Heavy | Generate diagnostics from packaged workflow if exposed, or run equivalent source `litlaunch report --profile rolethread-webapp --force`. | Diagnostics/report are available and useful for support. | Report/log paths. | High | Packaged diagnostics |
| PKG-05 | Not run | Heavy | Run packaged app after reboot or fresh shell. | Shortcut/launcher does not depend on the source checkout current directory. | Environment, path assumptions, missing-file errors. | High | Distribution readiness |

Packaged tests should not imply LitLaunch performs packaging. Record whether a
failure belongs to LitLaunch runtime behavior, RoleThread packaging, installer
scripts, or platform configuration.

## G. Stress And Edge Tests: Optional, High Value

Use after smoke and core lifecycle tests pass.

| ID | Status | Effort | Command / Action | Expected Result | Record If It Fails | Severity | Feature Area |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EDGE-01 | Not run | Heavy | Repeat `litlaunch app.py --browser edge` launch/close 10 times. | No stuck backend, no duplicate windows, temp profiles clean up. | Failing cycle number, console output, temp dirs. | High | Repeatability |
| EDGE-02 | Not run | Heavy | Repeat `litlaunch app.py --mode webapp --browser edge` launch/close 10 times. | App-window monitoring remains reliable. | Failing cycle and monitor output. | High | Webapp monitor |
| EDGE-03 | Not run | Medium | Start `litlaunch app.py --port 8501 --no-auto-port` in one shell, then run the same command in a second shell. | Second launch fails cleanly with port-in-use guidance. | Both console outputs. | High | Port ownership |
| EDGE-04 | Not run | Medium | Start `litlaunch app.py --verbose`, identify backend process, then terminate only the backend process. | LitLaunch reports backend exit and returns cleanly. | PID, output, remaining process check. | Medium | Backend failure |
| EDGE-05 | Not run | Medium | Launch with several unrelated Edge windows open. | LitLaunch monitors only its managed browser window or falls back; unrelated windows are untouched. | Window list before/after and console output. | High | Window safety |
| EDGE-06 | Not run | Medium | `litlaunch app.py --browser chrome` with existing Chrome sessions open, if installed. | Either managed lifecycle works or fallback is explicit and safe. | Chrome version/session state. | Medium | Chrome support |
| EDGE-07 | Not run | Medium | Inspect `$env:TEMP` before and after normal close and `Ctrl+C` shutdown. | LitLaunch temp browser profile directories do not accumulate unexpectedly. | Directory names and timestamps. | Medium | Temp cleanup |
| EDGE-08 | Not run | Heavy | Put machine to sleep or lock screen while runtime is active, then resume and close the window. | Runtime remains understandable; shutdown still works or fallback is clear. | Sleep/resume timing and output. | Low/Polish | Platform edge |

## Issue Capture Template

Use this for every manual failure:

```text
Test ID:
OS / shell:
LitLaunch version:
LitLaunch import path:
RoleThread path:
RoleThread branch/commit:
Command/action:
Expected:
Actual:
Console output excerpt:
Report/log path:
Screenshot path:
Existing browser state:
Suspected component: LitLaunch / RoleThread / browser-platform / profile-config / unknown
Severity: Blocker / High / Medium / Low-Polish
Reproducibility: Always / Often / Intermittent / Once
Cleanup performed:
Notes:
```

## Recommended Live Beta Loop

Use this loop for fast nightly testing:

1. Update LitLaunch and RoleThread sandbox.

   ```powershell
   cd X:\dev\litlaunch
   git status --short
   python -m pip install -e .[dev]

   cd X:\dev\rolethread-test
   git status --short
   .\.venv\Scripts\Activate.ps1
   python -c "import litlaunch; print(litlaunch.__version__); print(litlaunch.__file__)"
   ```

2. Run all Smoke tests.
3. Run one deeper category:
   - lifecycle after runtime changes
   - diagnostics/governance after inspect/report changes
   - console/output after presentation changes
   - profiles/shortcuts after CLI ergonomics changes
4. Capture failures with the issue template.
5. Apply fixes in LitLaunch only unless evidence points to RoleThread.
6. Re-run failed tests, then re-run Smoke tests.

## Release Confidence Checklist

Before calling a LitLaunch build RoleThread-ready:

- Browser mode opens one target and has a reliable `Ctrl+C` fallback.
- Managed browser-window close triggers shutdown where supported.
- Webapp/app-window close triggers shutdown.
- RoleThread shutdown hooks run on browser close, app-window close, and
  `Ctrl+C`.
- Profiles load and launch correctly.
- Shortcut generation and launch work from the RoleThread app root.
- HTML/JSON/bundle diagnostics include governance, exposure, transport, and
  privacy guidance.
- Network exposure warnings are visible and honest.
- Streamlit-native TLS posture is visible in diagnostics.
- No Edge sync, onboarding, or default-browser prompt appears during managed
  browser-window launch.
- No unrelated browser windows are closed or killed.
- No owned backend remains after expected shutdown.
