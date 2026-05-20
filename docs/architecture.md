# Architecture

LitLaunch keeps launch orchestration separate from live runtime ownership.

```text
LauncherConfig
      |
      v
StreamlitLauncher
      |
      +--> PortManager
      +--> StreamlitCommandBuilder
      +--> ProcessManager starts backend
      +--> HealthChecker waits for Streamlit health
      +--> BrowserRegistry resolves capability
      +--> BrowserLauncher opens browser target
      |
      v
RuntimeSession owns backend process
```

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

`RuntimeSession.wait()` with no timeout waits until the backend exits. Timed
waits return `None` if the timeout expires and leave the backend running with
the session state unchanged.

## Backend Lifecycle

```text
resolve port
build command
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
