# RoleThread Integration Plan

> INTERNAL / TEMPORARY INTEGRATION DOCUMENTATION
>
> This document supports beta integration work only. It is not part of the
> stable public LitLaunch documentation surface.

## Purpose

RoleThread should eventually consume LitLaunch as an external runtime package
instead of maintaining app-specific launcher behavior in parallel. The goal is
to reduce launcher code inside RoleThread while preserving RoleThread-specific
application policy, packaging behavior, UI decisions, and product workflows.

LitLaunch should remain a Streamlit runtime layer. It should not become a
general RoleThread orchestration system.

## Current RoleThread Launcher Responsibility Areas

During integration review, map the current RoleThread launcher code around:

- Streamlit command construction and launch flags.
- port selection and backend health readiness.
- browser or app-mode launch behavior.
- development versus production launch choices.
- graceful cleanup and app shutdown triggers.
- window-close observation for app-mode flows.
- console and diagnostic messages.
- packaged-launcher and shortcut behavior.

These areas may currently be intertwined in RoleThread. The integration should
separate runtime mechanics from RoleThread product policy before deleting code.

## Planned LitLaunch Takeover

LitLaunch should take responsibility for:

- `LauncherConfig` construction and validation.
- Streamlit command construction.
- fixed or automatic port resolution.
- owned backend process lifecycle.
- backend health checking.
- browser capability resolution and launch.
- optional graceful shutdown request and fallback backend termination.
- optional Windows Chromium app-mode window monitoring.
- inspect diagnostics for local runtime readiness.
- consistent runtime console messages.

## Boundaries That Stay In RoleThread

RoleThread should continue to own:

- app-specific paths and entrypoint selection.
- product naming, titles, and branded UI copy.
- role/thread/domain configuration.
- cloud, backup, account, workspace, or data workflows.
- packaged-app decisions and installer-specific behavior.
- support messaging that is specific to RoleThread users.
- any product policy around when to use browser, webapp, or monitoring mode.

## Boundaries That Should Migrate To LitLaunch

RoleThread should stop owning:

- backend PID termination logic.
- port-owner cleanup.
- browser process control.
- duplicated Streamlit command assembly.
- duplicated Edge/Chrome fallback decision logic.
- duplicated health polling.
- duplicated graceful shutdown request wiring.
- duplicated app-mode close observation mechanics.

LitLaunch should still only stop the backend process it started.

## Expected Simplifications

After migration, RoleThread launcher code should mostly:

1. Resolve RoleThread-specific app settings.
2. Build a `LauncherConfig`.
3. Register app-side shutdown hooks through `LauncherRuntime`.
4. Start LitLaunch.
5. Hold or wait on the returned `RuntimeSession`.
6. Call `session.stop()` when RoleThread product flow requires shutdown.

## App-Mode Expectations

RoleThread can use `mode="webapp"` with Edge or Chrome/Chromium when a
desktop-style app window is preferred. App-mode remains a browser launch mode,
not a separate app packaging system.

If app-mode is unavailable and fallback is allowed, LitLaunch may fall back
according to its browser resolution policy. RoleThread should decide whether
that fallback is acceptable for a given product workflow.

## Inspect Expectations

Before replacing RoleThread launcher paths, run `litlaunch report` against the RoleThread app entrypoint. Inspect
should help identify:

- missing Streamlit dependency.
- app path mistakes.
- browser capability gaps.
- app-mode capability gaps.
- command preview issues.
- target port and URL expectations.

Inspect does not run the app.

## Shutdown Expectations

RoleThread app code should register cleanup through `LauncherRuntime` when
LitLaunch launches the backend. The app must also remain safe under plain
`streamlit run`; missing LitLaunch shutdown environment variables should not
break imports or startup.

RoleThread-specific cleanup should remain in RoleThread. LitLaunch provides the
hook registry and graceful request path.

## Monitoring Expectations

Window monitoring should be tested first on Windows with Chromium app-mode.
Monitoring observes windows only. It must not own, close, or kill browser
processes.

RoleThread should opt in deliberately and treat unsupported monitoring as a
runtime capability issue, not a product crash.

## Phased Migration

### Phase 1: Parallel Launch Path

- Keep the existing RoleThread launcher available.
- Add an experimental LitLaunch-backed path behind a development switch.
- Compare command previews and app URLs.
- Validate inspect output before live launches.

### Phase 2: Backend Ownership Migration

- Let LitLaunch start and own the Streamlit backend.
- Remove RoleThread backend PID handling from the experimental path.
- Validate no orphan backend remains after normal exit, health failure, browser
  failure, and manual interrupt.

### Phase 3: Browser And App-Mode Migration

- Route browser and app-mode launch through LitLaunch.
- Validate Edge app-mode first, then Chrome/Chromium.
- Validate fallback behavior with fallback enabled and disabled.

### Phase 4: Graceful Shutdown And Monitoring

- Register RoleThread cleanup hooks through `LauncherRuntime`.
- Enable monitor-window only for app-mode validation.
- Confirm window close requests graceful shutdown before fallback termination.

### Phase 5: Remove Duplicated Launcher Code

- Delete only RoleThread launcher code proven redundant.
- Keep product policy, packaging, and UI-specific code in RoleThread.
- Preserve rollback until real beta users have exercised the path.

## Rollback Strategy

- Keep the old RoleThread launch path until LitLaunch-backed smoke tests are
  repeatable.
- Gate the LitLaunch path behind a config switch or development command.
- Log which runtime path was used in internal diagnostics.
- Avoid irreversible cleanup of old launch code until the integration matrix is
  green.

## Known Integration Risks

- RoleThread may rely on implicit launch behavior not yet modeled explicitly.
- Packaged-launcher behavior may require extra environment setup outside
  LitLaunch.
- App window title matching may need a RoleThread-specific title override.
- Browser fallback may be acceptable in development but not in packaged-style
  app flows.
- Shutdown hooks may expose cleanup ordering assumptions in RoleThread.

## Temporary Duplication

Expect short-lived duplication in:

- launch configuration conversion.
- console messages.
- app-mode/browser fallback decisions.
- shutdown hook registration.
- smoke-test scripts.

Delete duplication only after equivalent LitLaunch behavior is validated.

[diagram needed]
Create: RoleThread-to-LitLaunch migration flow. Show current RoleThread
launcher responsibilities, the temporary parallel LitLaunch path, and the final
boundary where RoleThread owns app policy while LitLaunch owns runtime mechanics.
