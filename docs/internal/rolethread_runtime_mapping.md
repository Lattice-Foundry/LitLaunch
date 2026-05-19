# RoleThread Runtime Mapping

> INTERNAL / TEMPORARY INTEGRATION DOCUMENTATION
>
> This mapping supports RoleThread integration planning only. It is not a public
> compatibility guarantee.

## Purpose

This document maps current RoleThread launcher/runtime concepts to LitLaunch
concepts so integration work does not duplicate responsibilities.

## Mapping Table

| RoleThread concept | LitLaunch concept | Migration expectation |
| --- | --- | --- |
| Streamlit launch command | `StreamlitCommandBuilder` | Move command construction to LitLaunch. RoleThread supplies config. |
| Launch settings/profile | `LauncherConfig` | Convert RoleThread settings into explicit config fields and args. |
| Port selection | `PortManager` | Move runtime port choice to LitLaunch unless RoleThread explicitly requires a fixed port. |
| Backend process tracking | `RuntimeSession` and `ManagedProcess` | RoleThread should stop direct backend PID ownership. |
| Health polling | `HealthChecker` | Move readiness checks to LitLaunch. |
| Browser launch handling | `BrowserRegistry` and `BrowserLauncher` | Move browser selection and launch to LitLaunch. |
| Edge/Chrome app-mode | `LaunchMode.WEBAPP` with Chromium browser capability | Use LitLaunch webapp mode and browser resolution. |
| Fallback behavior | `allow_browser_fallback` and browser resolution | RoleThread decides whether fallback is acceptable per flow. |
| Shutdown cleanup | `LauncherRuntime` and shutdown hooks | Keep cleanup functions in RoleThread app code; use LitLaunch hook runtime. |
| Graceful stop/fallback | `RuntimeSession.stop()` | Let LitLaunch request graceful shutdown and terminate only its owned backend if needed. |
| Window close observation | windowing monitor plus `RuntimeSession.monitor_window()` | Use only for opt-in webapp app-mode flows. |
| Runtime diagnostics | `litlaunch inspect` | Use for prelaunch validation and support bundles. |
| Console output | `ConsoleRenderer` | LitLaunch emits runtime mechanics; RoleThread owns product messaging. |

## What RoleThread Should Stop Owning

RoleThread should gradually stop owning:

- shell or string-based command construction.
- backend process termination.
- process discovery by name.
- cleanup of unknown port owners.
- browser fallback logic.
- Edge/Chrome path detection.
- health endpoint polling.
- window-close observation mechanics.
- duplicated local diagnostics for launch readiness.

## What RoleThread Still Owns

RoleThread still owns:

- app entrypoint choice.
- product-specific launch policy.
- user preferences and saved settings.
- RoleThread-specific Streamlit flags and app arguments.
- app cleanup logic registered as hooks.
- packaging and installer integration.
- product support messages and issue templates.
- any cloud, backup, or account behavior.

## What Remains App-Specific

The following should not move into LitLaunch:

- RoleThread data migration.
- RoleThread workspace setup.
- RoleThread cloud backup staging.
- branded tray, shortcut, installer, or updater behavior.
- RoleThread-specific error recovery.
- product telemetry or analytics policy.

## Avoiding Duplicated Responsibilities

If RoleThread code can be expressed by passing values into `LauncherConfig`,
prefer that over wrapping or reimplementing LitLaunch internals.

If RoleThread needs behavior LitLaunch cannot express, first decide whether it
is:

1. generic Streamlit runtime behavior that belongs in LitLaunch.
2. RoleThread-specific policy that belongs in RoleThread.
3. packaging/installer behavior that should remain outside both core runtime
   code paths.

[diagram needed]
Create: responsibility boundary diagram with three columns: RoleThread app
policy, LitLaunch runtime layer, operating system/browser. Show that LitLaunch
owns only the backend process it starts and observes browser windows without
owning browser processes.

