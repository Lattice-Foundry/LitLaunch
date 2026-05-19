# RoleThread Integration Notes

RoleThread is expected to consume LitLaunch as an external package once the
runtime contract is stable enough for integration.

These notes describe expectations, not a current dependency. LitLaunch must not
import RoleThread or assume RoleThread paths, names, environment variables, or
packaging behavior.

## Expected Integration Shape

RoleThread should provide:

- app path
- title
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

## Future Compatibility

Future launch profiles may help RoleThread map development, browser, webapp,
and packaged-style launch configurations. Until implemented, integration should
use explicit `LauncherConfig` fields.

[diagram needed]
Create: RoleThread-to-LitLaunch integration boundary diagram. Show RoleThread
configuration flowing into LitLaunch and `RuntimeSession` returning ownership.

