# RoleThread Integration Notes

RoleThread can consume LitLaunch as an external package for runtime ownership,
diagnostics, profile-driven launch configuration, and optional project-local
shortcut generation.

These notes describe expectations, not a current dependency. LitLaunch must not
import RoleThread or assume RoleThread paths, names, environment variables, or
packaging behavior.

## Expected Integration Shape

RoleThread should provide:

- app path
- stable title for display and app-window matching
- launch mode
- browser preference
- Streamlit flags
- app arguments
- optional monitor-window choice
- optional shutdown hooks inside the app

LitLaunch should provide:

- backend process ownership
- command construction
- port resolution
- health checking
- browser resolution and launch
- graceful shutdown request/fallback
- inspect diagnostics

## Runtime Expectations

RoleThread should treat `RuntimeSession` as the backend lifecycle owner. If
RoleThread adds UI or packaged-launcher behavior, it should still call
`session.stop()` rather than managing backend PIDs independently.

## Shutdown Hooks

RoleThread app code can register cleanup hooks through `LauncherRuntime`.
Hook labels and color metadata should remain app-level presentation metadata.

## Window Monitoring

RoleThread may opt into `--monitor-window` or equivalent API behavior for
Windows Chromium app-mode flows. Monitoring must remain observational; closing
or killing browser windows should remain outside LitLaunch.

Choose a stable `LauncherConfig.title` for webapp monitoring. If the browser
window title differs significantly from the configured title, window detection
may timeout.

## Launch Profiles

RoleThread or similar apps can store reusable development, browser-tab,
app-window, and packaged-style runtime settings in `litlaunch.toml` profiles.
Use `litlaunch create profile` for an interactive starting point, then commit or
ship the resulting configuration according to the downstream app's policy.

Profile-based launches use the same runtime path as explicit `LauncherConfig`
usage:

```powershell
litlaunch --profile rolethread-webapp
litlaunch report --profile rolethread-webapp
litlaunch create shortcut --profile rolethread-webapp
```

Use the profile path when validating RoleThread's app-window lifecycle.
Generic `litlaunch app.py` remains useful as a smoke test, but it does not apply
RoleThread's profile settings such as app-window mode, fixed browser policy, or
window monitoring. Close-to-shutdown behavior requires an explicit monitored
webapp launch path.

RoleThread still owns product policy, app-specific settings, packaged resource
layout, and user-facing support text. LitLaunch owns the generic Streamlit
runtime mechanics and returns `RuntimeSession` ownership for the backend process
it starts.
