# Troubleshooting

Use this as a first pass when a launch does not behave as expected.

## Backend Exits Immediately

Likely causes:

- Streamlit is not installed in the active Python environment.
- The app crashes during import/startup.
- Streamlit CLI arguments are invalid.
- The app path is wrong.

Next steps:

```powershell
litlaunch inspect app.py
litlaunch run app.py --verbose
streamlit run app.py
```

## Health Timeout

The backend process started but Streamlit did not report healthy before timeout.

Likely causes:

- app startup is slow
- app import error
- Streamlit internal failure
- localhost/firewall issue
- timeout too short for the app

Next steps:

```powershell
litlaunch inspect app.py
litlaunch run app.py --verbose
streamlit run app.py
```

## Browser Did Not Open

Likely causes:

- requested browser is not installed
- browser executable detection failed
- app-mode requested with a non-app-mode browser
- browser launch was blocked by local policy

Next steps:

```powershell
litlaunch browsers
litlaunch run app.py --browser default
litlaunch run app.py --mode webapp --browser edge --verbose
```

## App-Mode Unavailable

Use Edge or Chrome/Chromium for app-mode:

```powershell
litlaunch run app.py --mode webapp --browser edge
litlaunch run app.py --mode webapp --browser chrome
```

For normal browser behavior:

```powershell
litlaunch run app.py --mode browser --browser default
```

## Window Monitoring Unsupported

`--monitor-window` is experimental and currently strongest on Windows with
Chromium app-mode.

Next steps:

```powershell
litlaunch run app.py --mode webapp
litlaunch run app.py --mode webapp --browser edge --monitor-window --verbose
```

Omit `--monitor-window` when close detection is not required.

## Shutdown Uses Fallback Termination

LitLaunch first requests graceful app shutdown when the app enables the
shutdown endpoint. If that fails or times out, LitLaunch terminates only the
Streamlit backend process it started.

The shutdown request itself uses a short client timeout so stop operations do
not hang indefinitely. `RuntimeSession.stop(graceful_timeout_seconds=...)`
controls how long LitLaunch waits for the backend to exit after a graceful
request is accepted before using the owned-process fallback.

Check:

- app calls `LauncherRuntime.from_env()`
- app calls `runtime.enable_shutdown_endpoint()`
- shutdown hooks complete quickly
- apps that need to exit themselves after responding register a completion
  callback with `runtime.set_shutdown_completion_callback(...)`
- verbose output for safe runtime details

## Support Bundle

For support or issue triage:

```powershell
litlaunch inspect app.py --bundle --output litlaunch-report.txt --force
```

The bundle is sanitized and does not include shutdown tokens or raw environment
dumps. LitLaunch also redacts common home/user path prefixes where practical.
Sanitization is pattern-based, so encoded, URL-wrapped, or reformatted secrets
may not always be detected. Review support bundles before sharing them publicly.
