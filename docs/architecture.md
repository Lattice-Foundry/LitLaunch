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

## Backend Lifecycle

```text
resolve port
build command
start backend process
wait for /_stcore/health
return healthy backend or failure result
```

LitLaunch injects shutdown endpoint environment variables into the backend
process. The shutdown token is redacted from console output.

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

