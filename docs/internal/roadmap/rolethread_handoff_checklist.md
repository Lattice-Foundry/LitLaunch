# RoleThread Handoff Checklist

> INTERNAL / TEMPORARY INTEGRATION DOCUMENTATION
>
> This checklist is for integration continuity between engineers or Codex
> sessions. It is not public setup documentation.

## Before Starting

- Confirm the LitLaunch branch and version under test.
- Confirm whether LitLaunch is installed from source or a local/package wheel.
- Start from a clean virtual environment when comparing launcher behavior.
- Record Python version, OS, browser availability, and RoleThread branch.
- Run `litlaunch report` before any live
  app launch.

## Installation Paths

### Editable Source Install

Use this for active LitLaunch development:

```powershell
python -m pip install -e .[dev]
litlaunch version
litlaunch platform
litlaunch browsers
```

### Local Wheel Install

Use this to simulate a package install from a built wheel:

```powershell
python scripts/check_release.py
python -m pip install dist/litlaunch-<version>-py3-none-any.whl
litlaunch version
```

### Package Index Rehearsal

Use this only after a release rehearsal package exists on the configured
package index:

```powershell
python -m pip install --index-url https://test.pypi.org/simple/ litlaunch
litlaunch version
```

If dependencies are unavailable on the rehearsal index, use the public package
index as the extra index for dependency resolution. Do not document rehearsal
commands as public installation guidance.

## RoleThread Launcher Replacement Checklist

- Identify the current RoleThread Streamlit entrypoint.
- Identify current launch flags and app arguments.
- Build equivalent `LauncherConfig` values.
- Preserve RoleThread app-specific configuration outside LitLaunch.
- Confirm command preview with `litlaunch command`.
- Confirm inspect output with `litlaunch report`.
- Start with browser mode before webapp mode.
- Add webapp/app-mode only after backend ownership is validated.
- Add monitor-window last.

## Backend Ownership Validation

- Start RoleThread through the LitLaunch-backed path.
- Confirm the backend PID belongs to the LitLaunch `RuntimeSession`.
- Stop through `session.stop()`.
- Confirm no LitLaunch-owned backend remains.
- Confirm LitLaunch did not kill unrelated Streamlit or browser processes.
- Repeat after backend startup failure.
- Repeat after browser launch failure where fakeable.

## App-Mode Validation

Run a webapp launch with Edge first:

```powershell
litlaunch run <rolethread-app.py> --mode webapp --browser edge
```

Then test Chrome/Chromium if installed:

```powershell
litlaunch run <rolethread-app.py> --mode webapp --browser chrome
```

Record:

- selected browser.
- whether app-mode opened.
- window title observed.
- fallback used, if any.
- whether the backend stopped cleanly.

## Fallback Validation

- Run with `--browser auto`.
- Run with explicit Edge.
- Run with explicit Chrome.
- Run with `--no-browser-fallback`.
- Confirm explicit fallback behavior matches RoleThread product expectations.
- Confirm browser mode can use the default browser path.
- Confirm webapp mode does not silently downgrade when app-mode is required by
  the test.

## Monitor-Window Validation

Use only webapp mode:

```powershell
litlaunch run <rolethread-app.py> --mode webapp --monitor-window --browser edge
```

Validate:

- monitor starts only after app-mode launch.
- unsupported provider fails clearly.
- detected window title is plausible.
- closing the app window triggers `RuntimeSession.stop()`.
- browser processes are not killed.
- backend exits cleanly after close.
- no orphan backend remains.
- capture manual notes for the Windows Edge app-mode window and monitoring
  console output when preparing release evidence.

## Graceful Shutdown Validation

- Register at least one RoleThread cleanup hook through `LauncherRuntime`.
- Confirm the app still runs with plain `streamlit run`.
- Launch through LitLaunch.
- Trigger `session.stop()` or close the monitored app window.
- Confirm hooks run once.
- Confirm failures are summarized without leaking tokens.
- Confirm fallback backend termination is used only if graceful stop does not
  complete.

Trace the graceful shutdown flow from window close or interrupt through
`RuntimeSession.stop()`, shutdown endpoint request, hook execution, and backend
termination fallback during validation.

## Inspect Diagnostics Validation

Run:

```powershell
litlaunch report <rolethread-app.py>
litlaunch inspect <rolethread-app.py> --json
litlaunch inspect <rolethread-app.py> --bundle
```

Confirm:

- no raw environment dump appears.
- no shutdown token appears.
- command preview is sanitized.
- browser capabilities are plausible.
- missing app path returns a clear error.
- support bundle is copyable into an issue or handoff note.

## Findings Log Template

Record each issue with:

- LitLaunch version.
- RoleThread branch.
- OS and Python version.
- command used.
- expected behavior.
- actual behavior.
- whether fallback occurred.
- whether a backend process remained.
- sanitized inspect bundle, if relevant.
