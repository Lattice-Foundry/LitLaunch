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

## Visual Documentation

Public docs should avoid unfinished visual placeholders. Screenshots and
diagrams can still be added after TestPyPI and RoleThread integration
validation, but prose should stand on its own until then.

## Runtime Profiles

Runtime profiles are implemented as reusable LitLaunch configuration. They can
map development, browser-tab, app-window, and packaged-style launch preferences
without bloating `LauncherConfig`. RoleThread integration may use profiles now,
while still keeping RoleThread-specific product policy outside LitLaunch.

## Packaging Notes

LitLaunch should support packaged apps as a runtime dependency, but it should
not own PyInstaller, Nuitka, installer, updater, or distribution behavior.
Lightweight profile shortcut scripts are supported; full installer workflows are
not.

Packaging guidance is expected to evolve during RoleThread validation.
