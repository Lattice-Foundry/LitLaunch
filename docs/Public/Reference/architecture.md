# Architecture

LitLaunch keeps launch orchestration separate from live runtime ownership.

```text
litlaunch.toml / pyproject.toml profile (optional)
      |
      v
LauncherConfig
      |
      v
StreamlitLauncher
      |
      +--> PortManager
      +--> StreamlitCommandBuilder
      +--> BackendCommandProvider builds backend command
      +--> build_launch_plan() resolves behavior without starting it
      +--> ProcessManager starts backend
      +--> HealthChecker waits for Streamlit health
      +--> BrowserRegistry resolves capability
      +--> BrowserLauncher opens browser target
      |
      v
RuntimeSession owns backend process
```

## Public API Surface

These public surfaces are supported:

- `LauncherConfig`
- `HostSizingPolicy`
- `HostSizingHandoff` and `get_host_sizing_handoff()`
- `StreamlitLauncher`
- `LaunchPlan`
- `LaunchProfile`
- `load_profile()` and `load_profiles()`
- `run_profile()`
- `run_monitored_webapp()`
- `BackendCommandProvider`, `BackendCommand`, and `BackendCommandContext`
- `LauncherRuntime` shutdown hooks and shutdown completion callback APIs
- diagnostics report and rendering APIs, including `HTMLDiagnosticsRenderer`

These surfaces are implementation-oriented and may evolve faster:

- windowing provider internals
- Windows HWND/provider implementation details
- low-level browser/window matching details
- console/theme/presentation internals
- private helper modules and modules not exported from `litlaunch.__all__`

LitLaunch is a runtime platform, not a packager. Packaged apps should use the
`BackendCommandProvider` seam when they need custom backend commands.
Packaging automation remains outside LitLaunch's runtime API.

## RuntimeSession

`RuntimeSession` is the live runtime owner. It holds:

- launch result
- managed backend process
- process manager
- optional shutdown client
- lifecycle events

It can:

- report whether the backend is running
- wait for backend exit
- stop the backend
- request optional app-side cleanup when available
- fall back to terminating only the owned backend process

It does not own browser processes.

`StreamlitLauncher.run()` is the friendly common entry point. `start()` is the
explicit lifecycle entry point. Both return a `RuntimeSession`.
`with_port(port)` returns a new launcher with the same injected dependencies
and a fixed port, leaving the original launcher unchanged.

`build_launch_plan()` returns a `LaunchPlan` for diagnostics, tests, and
integration checks. It resolves the backend port, command, URLs, browser
resolution, backend description, working directory, app args, Streamlit flags,
passthrough args, host-sizing policy/static eligibility, and redacted
environment display without starting a backend process or opening a browser.

Python integrations can attach an optional runtime event sink to
`StreamlitLauncher` when they need product logs or support trails. The sink is a
small structured callback surface, not telemetry or a logging framework, and
runtime behavior continues even if the sink fails.

`StreamlitBackendCommandProvider` is the default command provider and preserves
the normal `python -m streamlit run ...` source-app command. Custom providers
may supply a different command tuple for packaged or embedded apps, but they do
not start processes. LitLaunch still calls `ProcessManager.start()`, injects
environment variables, performs health checks, launches browsers, and owns the
returned session lifecycle.

## Profiles

`LaunchProfile` is a reusable project configuration wrapper around
`LauncherConfig` plus runtime-only settings such as `monitor_window`,
`graceful_timeout_seconds`, and `WindowMonitorConfig`. Profiles can be loaded
from `litlaunch.toml` or `[tool.litlaunch]` in `pyproject.toml`.

Profiles are declarative inputs. Loading a profile does not start a backend,
open a browser, monitor a window, or request shutdown. CLI commands apply
profile values first and explicit CLI arguments second before constructing the
same `LauncherConfig` and `LaunchPlan` used by non-profile flows.

`run_profile()` connects a loaded `LaunchProfile` to runtime execution. If
`profile.monitor_window` is enabled, it delegates to `run_monitored_webapp()`.
If `profile.monitor_browser_window` is enabled, it delegates to the managed
browser-window runner. If monitoring is disabled, it uses the normal
`StreamlitLauncher.run()` path. All monitored paths return `MonitoredRunResult`
so integrations can inspect launch, monitor, and exit status consistently.

`RuntimeSession.wait()` with no timeout waits until the backend exits. Timed
waits return `None` if the timeout expires and leave the backend running with
the session state unchanged.

## Backend Lifecycle

```text
optional build_launch_plan() dry run
resolve port
build backend command through provider
start backend process with configured cwd/env
wait for /_stcore/health
return healthy backend or failure result
```

LitLaunch injects shutdown endpoint environment variables into the backend
process after applying any `LauncherConfig.extra_env` overrides. This keeps
app-provided environment values child-process only and ensures LitLaunch-owned
shutdown variables win on collision. The shutdown token is redacted from
console output.

`RuntimeSession.stop()` can send an app-side cleanup request when a Streamlit
app enables the `LauncherRuntime` shutdown endpoint. Plain Streamlit apps do not
need that endpoint for the default close flow; if no endpoint is available,
LitLaunch treats that as expected and stops only the owned backend process it
started. The shutdown request client has a short default request timeout, and
`stop(graceful_timeout_seconds=...)` controls how long the session waits for
the backend to exit before using owned-process termination fallback.

App code can register cleanup hooks with `LauncherRuntime`. Apps that need a
post-response completion phase can also register a shutdown completion callback.
Hook labels and messages are developer-defined presentation hints. Console
output for those callbacks uses the orange `Hook:` category, not `Shutdown:` or
`Backend:`, so app cleanup remains visually distinct from LitLaunch-owned
lifecycle mechanics. Hook status brackets keep the normal status colors, hook
message text remains unstyled for readability, and hook color metadata is
preserved on hook results for integrations. Hooks can mark routine success
messages as `console_visibility="verbose"`; important success messages can opt
into quiet output with `show_in_quiet=True`. Failures stay visible in normal and
quiet output through the standard error/cause/verbose-details guidance. Hooks
that need run-specific presentation can return `ShutdownHookStatus`; this lets
apps surface dynamic cleanup messages through LitLaunch's `Hook:` renderer
instead of printing raw stdout lines. The endpoint runs hooks, sends the
HTTP response to LitLaunch, and then schedules the app-provided completion
callback. Hooks and completion callbacks are idempotent for a single shutdown
request sequence; duplicate shutdown requests return the stored result and do
not rerun cleanup.

## Browser Flow

```text
detect capabilities
resolve requested browser
apply fallback policy
launch selected target
do not retain browser process ownership
```

Browser launch is command-based for Chromium adapters and `webbrowser.open` for
default browser mode. Managed browser-window launches use Chromium command-line
arguments with a temporary LitLaunch profile directory, a new top-level window,
and prompt-suppression flags where supported. That gives LitLaunch a safer
window lifecycle signal without taking browser process ownership.

## Monitoring Flow

```text
optional webapp --monitor-window or browser-window monitor
capture baseline windows
launch runtime
observe app-mode window or new managed browser window
on close: RuntimeSession.stop()
```

The monitor observes only. Shutdown remains a session responsibility. If a
browser-window target cannot be identified confidently, LitLaunch falls back to
the manual Ctrl+C stop path.

`run_monitored_webapp()` is the high-level helper for integrations that want the
standard monitored app-mode flow without manually assembling platform detection,
monitor creation, baseline capture, `WindowTarget` construction, session
monitoring, and result interpretation. It returns a `MonitoredRunResult` and
keeps the same ownership boundary: monitoring may stop the owned backend
session, but it never owns, kills, or closes browser windows. The separate
Experimental host-sizing policy below is the only bounded window-geometry
mutation in this model.

## Experimental Host-Sizing Flow

```text
host_sizing = "initial" | "continuous"
validate static launch eligibility
start launch-scoped authenticated loopback channel
inject private handoff into the app child process
launch managed Edge/Chrome webapp
establish exact launch-process and stable window authority
accept one authoritative frontend measurement stream
stabilize and apply policy-approved bounded height-only changes
close after one initial attempt or retain authority until continuous shutdown
```

The public surface is limited to the launch policy and immutable handoff
metadata. Transport, timing, bounds, process authority, window authority,
geometry conversion, and native mutation stay private. Any failure leaves the
base app running and the window unchanged. See the
[host-sizing guide](../Guides/host-sizing.md) for eligibility and the
app-owned frontend contract.

## Inspect Architecture

Inspect uses structured report types:

- `DiagnosticItem`
- `DiagnosticSection`
- `DiagnosticsReport`

Renderers produce HTML, JSON, or support bundle output from the same report.
Collection does not start Streamlit or browsers.

## Failure Handling

Runtime failures return structured results or nonzero CLI exit codes with
console guidance. Guidance is presentation-only; it does not drive runtime
behavior.

Ownership boundaries are intentionally narrow: LitLaunch owns the backend
process it starts, observes optional browser-window state when requested, and
never owns or kills browser processes. Browser launching, health checks,
shutdown requests, and diagnostics all flow through explicit runtime/session
objects so integrations can reason about responsibility boundaries without a
separate diagram.
