# RoleThread Lite Integration

RoleThread Lite uses LitLaunch as its runtime launch layer while keeping product
behavior owned by RoleThread. The integration is a concrete example of how a
local-first Streamlit product can delegate launch orchestration, runtime
lifecycle, browser/app-window strategy, diagnostics, and support artifacts to
LitLaunch without making LitLaunch a RoleThread-specific launcher.

LitLaunch remains a standalone runtime package. It must not import RoleThread or
assume RoleThread paths, names, environment variables, packaging behavior, data
models, workflows, or product policy.

## Integration Shape

RoleThread Lite supplies application-specific launch inputs:

- app entrypoint
- stable title for display and app-window matching
- launch mode
- browser preference
- Streamlit flags
- app arguments
- optional monitor-window choice
- optional managed browser-window choice
- optional shutdown hooks inside the app

LitLaunch supplies generic runtime mechanics:

- backend process ownership
- shell-free command construction
- port resolution
- health checking
- browser resolution and launch
- managed browser-window lifecycle when enabled
- graceful shutdown request/fallback
- inspect diagnostics and support artifacts

RoleThread owns the application workflow, user experience, product settings,
packaging choices, data handling, and support messaging. LitLaunch owns only the
generic Streamlit runtime layer it starts and observes.

## Runtime Expectations

RoleThread Lite should treat `RuntimeSession` as the backend lifecycle owner. If
RoleThread adds UI or packaged-launcher behavior, it should still call
`session.stop()` rather than managing backend PIDs independently.

## Shutdown Hooks

RoleThread app code can register cleanup hooks through `LauncherRuntime` when
product cleanup is needed during shutdown. The cleanup behavior belongs to
RoleThread; LitLaunch provides the hook runtime, status rendering, and shutdown
coordination. Hook labels and color metadata remain app-level presentation
metadata.

## Window Monitoring

RoleThread Lite can opt into `--monitor-window` or equivalent API behavior for
Windows Chromium app-mode flows. Browser-mode profiles can opt into
`browser_window_monitor.enabled` for managed browser-window close detection.
Monitoring must remain observational; closing or killing browser windows should
remain outside LitLaunch.

Choose a stable `LauncherConfig.title` for webapp monitoring. If the browser
window title differs significantly from the configured title, window detection
may timeout.

## Launch Profiles

RoleThread Lite and similar apps can store reusable development, browser-tab,
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

Use the profile path when validating RoleThread's intended app-window
lifecycle. Generic `litlaunch app.py` remains useful as a smoke test and now
exercises LitLaunch's managed browser-window lifecycle where supported, but it
does not apply RoleThread's profile settings such as app-window mode, fixed
browser policy, profile-specific monitoring, or packaged-app choices.

## Boundary Summary

RoleThread Lite integration should stay thin and explicit:

- LitLaunch should not train models, transform RoleThread data, or implement
  RoleThread product logic.
- LitLaunch should not own RoleThread auth, hosting, TLS termination, reverse
  proxies, telemetry, cloud logging, packaging, installer behavior, or update
  policy.
- RoleThread should not require LitLaunch internals or private modules.
- RoleThread-specific behavior should be expressed as app configuration,
  profile values, app arguments, shutdown hooks, or app-owned support text.

This boundary keeps LitLaunch useful for RoleThread Lite while preserving the
same integration model for other Streamlit products.
