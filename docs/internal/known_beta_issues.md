# Known Beta Issues

> INTERNAL / TEMPORARY INTEGRATION DOCUMENTATION
>
> This list tracks expected rough edges during beta integration. It is not a
> permanent public limitations page.

## Windows-First Runtime Validation

Most deep runtime validation has happened on Windows, especially for Chromium
app-mode and window monitoring. macOS and Linux should continue to be tested
through CI and fake-driven tests, but manual browser/app-mode validation is
lighter today.

## Window Monitoring Limitations

Window monitoring is:

- opt-in.
- strongest on Windows.
- focused on Chromium app-mode windows.
- observational only.
- not a browser process ownership system.

Known rough edges:

- app window title matching may need a project-specific title override.
- multiple matching windows can require careful smoke testing.
- browser process reuse can make process-based assumptions unreliable, which is
  why LitLaunch does not own browser processes.
- RDP, locked desktops, and unusual shell environments may affect visible
  window enumeration.

## App-Mode Limitations

App-mode depends on Chromium behavior and installed browser capability. Edge and
Chrome/Chromium are the first supported targets. Other browsers are not treated
as app-mode capable today.

Fallback can keep a runtime usable, but product integrations should decide
whether fallback from app-mode to normal browser mode is acceptable.

## Unsupported Browsers

Default browser fallback is full-browser only. It should not be presented as a
desktop app-mode path.

Firefox, Safari, and other browsers are not app-mode targets in the current
runtime layer.

## Shutdown Rough Edges

The graceful shutdown endpoint is tokened and loopback-only by default. It runs
registered hooks and lets `RuntimeSession.stop()` fall back to terminating only
the owned backend process if graceful shutdown does not complete.

Potential beta issues:

- app code may forget to call `enable_shutdown_endpoint()`.
- hooks may need clearer ordering during real RoleThread cleanup.
- hook output should remain sanitized and should not expose tokens or secrets.
- duplicate shutdown requests should not rerun hooks.

## Inspect Rough Edges

Inspect is useful for prelaunch readiness and support bundles, but it does not
run the app. It cannot prove that an app will import successfully or that a
browser window will appear.

Use inspect alongside real smoke tests, not instead of them.

## Screenshot And Diagram Placeholders

Public and internal docs intentionally keep `[screenshot needed]` and
`[diagram needed]` placeholders as deferred until release stabilization. Actual
images should be captured after TestPyPI and RoleThread integration validation
reduce the chance of rework.

## Future Runtime Profiles

Runtime profiles are a future possibility, not implemented behavior. They may
eventually help map development, browser, webapp, packaged-style, or kiosk-ish
launch preferences without bloating `LauncherConfig`.

Do not build RoleThread integration around profiles until the API exists.

## Packaging Notes

LitLaunch should support packaged apps as a runtime dependency, but it should
not own PyInstaller, Nuitka, shortcut, installer, updater, or distribution
behavior.

Packaging guidance is expected to evolve during RoleThread validation.

[diagram needed]
Create: beta risk map showing which areas are stable beta foundation, which are
experimental, and which remain future work. Include browser fallback, window
monitoring, graceful shutdown, inspect, and packaging.
