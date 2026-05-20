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
      +--> build_launch_plan() previews resolved behavior
      +--> ProcessManager starts backend
      +--> HealthChecker waits for Streamlit health
      +--> BrowserRegistry resolves capability
      +--> BrowserLauncher opens browser target
      |
      v
RuntimeSession owns backend process
```

## Beta API Stability

During the 0.9x beta band, these public surfaces are intended to stabilize:

- `LauncherConfig`
- `StreamlitLauncher`
- `LaunchPlan`
- `LaunchProfile`
- `load_profile()` and `load_profiles()`
- `run_profile()`
- `run_monitored_webapp()`
- `BackendCommandProvider`, `BackendCommand`, and `BackendCommandContext`
- `LauncherRuntime` shutdown hooks and shutdown completion callback APIs
- diagnostics report and rendering APIs, including `HTMLDiagnosticsRenderer`

Breaking changes are still possible before 1.0. The stronger API freeze target
is `1.0.0-rc1`.

These surfaces remain experimental or implementation-oriented and may evolve
faster:

- windowing provider internals
- Windows HWND/provider implementation details
- low-level browser/window matching details
- console/theme/presentation internals
- private helper modules and modules not exported from `litlaunch.__all__`

LitLaunch is a runtime platform, not a packager. Packaged apps should use the
`BackendCommandProvider` seam when they need custom backend commands. Future
packaging tooling may build on this contract, but packaging automation is not
part of the beta runtime API.

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
- request graceful shutdown first when available
- fall back to terminating only the owned backend process

It does not own browser processes.

`StreamlitLauncher.run()` is the friendly common entry point. `start()` is the
explicit lifecycle entry point. Both return a `RuntimeSession`.
`with_port(port)` returns a new launcher with the same injected dependencies
and a fixed port, leaving the original launcher unchanged.

`build_launch_plan()` returns a `LaunchPlan` for diagnostics, tests, and
integration previews. It resolves the backend port, command, URLs, browser
resolution, backend description, working directory, app args, Streamlit flags,
passthrough args, and redacted environment preview without starting a backend
process or opening a browser.

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
If monitoring is disabled, it uses the normal `StreamlitLauncher.run()` path.
Both paths return `MonitoredRunResult` so integrations can inspect launch,
monitor, and exit status consistently.

`RuntimeSession.wait()` with no timeout waits until the backend exits. Timed
waits return `None` if the timeout expires and leave the backend running with
the session state unchanged.

## Backend Lifecycle

```text
optional build_launch_plan() preview
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

`RuntimeSession.stop()` first sends a graceful shutdown request when an app-side
shutdown endpoint is available. The shutdown request client has a short default
request timeout, and `stop(graceful_timeout_seconds=...)` controls how long the
session waits for the backend to exit before using owned-process termination
fallback.

App code can register cleanup hooks with `LauncherRuntime`. Apps that need a
post-response completion phase can also register a shutdown completion callback.
The endpoint runs hooks, sends the HTTP response to LitLaunch, and then schedules
the app-provided completion callback. Hooks and completion callbacks are
idempotent for a single shutdown request sequence; duplicate shutdown requests
return the stored result and do not rerun cleanup.

## Browser Flow

```text
detect capabilities
resolve requested browser
apply fallback policy
launch selected target
do not retain browser process ownership
```

Browser launch is command-based for Chromium adapters and `webbrowser.open` for
default browser mode.

## Monitoring Flow

```text
optional --monitor-window
capture baseline windows
launch runtime
observe app-mode window
on close: RuntimeSession.stop()
```

The monitor observes only. Shutdown remains a session responsibility.

`run_monitored_webapp()` is the high-level helper for integrations that want the
standard monitored app-mode flow without manually assembling platform detection,
monitor creation, baseline capture, `WindowTarget` construction, session
monitoring, and result interpretation. It returns a `MonitoredRunResult` and
keeps the same ownership boundary: LitLaunch may stop the owned backend session,
but it never owns, kills, closes, or controls browser windows.

## Inspect Architecture

Inspect uses structured report types:

- `DiagnosticItem`
- `DiagnosticSection`
- `DiagnosticsReport`

Renderers produce text, JSON, or bundle output from the same report. Collection
does not start Streamlit or browsers.

## Failure Handling

Runtime failures return structured results or nonzero CLI exit codes with
console guidance. Guidance is presentation-only; it does not drive runtime
behavior.

[diagram needed]
Create: architecture diagram with ownership boundaries. Highlight that
BrowserLauncher launches but does not own browser processes.
