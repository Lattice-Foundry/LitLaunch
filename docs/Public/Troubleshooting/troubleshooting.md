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
litlaunch report app.py
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
litlaunch report app.py
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

`--monitor-window` is for webapp/app-window monitoring and is currently
strongest on Windows with Chromium app-mode. Browser mode uses the separate
managed browser-window monitor when LitLaunch can use Edge or Chrome/Chromium.

Next steps:

```powershell
litlaunch run app.py --mode webapp
litlaunch run app.py --mode webapp --browser edge --monitor-window --verbose
litlaunch run app.py --browser edge --verbose
```

Omit `--monitor-window` for unmonitored webapp mode. Use
`--no-monitor-browser-window` when browser mode should keep running until
Ctrl+C or backend exit.

If browser-window monitoring falls back, LitLaunch should say that Ctrl+C
remains the shutdown path. That fallback is expected when a new top-level
browser window cannot be identified confidently.

If a webapp/app-window launch opens successfully and then reports
`Timed out waiting for app-mode window to appear`, check the window title.
For Streamlit, make the LitLaunch profile `title` or CLI `--title` match
`st.set_page_config(page_title="...")`.

## Network Exposure Launch Times Out

When binding Streamlit to a wildcard host such as `0.0.0.0` or `::`,
LitLaunch should still health-check through a local client URL such as
`127.0.0.1` or `::1`. If a network-exposed launch times out after Streamlit
prints its Local/Network URLs, run with verbose output and capture the health
URL:

```powershell
litlaunch run app.py --host 0.0.0.0 --trust-mode internal_network --allow-network-exposure --verbose
```

The runtime warning is expected for non-loopback hosts. It means exposure is
intentional and still operationally visible; it does not mean LitLaunch failed
the launch.

## Shutdown Uses Fallback Termination

Plain Streamlit apps can use LitLaunch without app-side shutdown setup. If no
cleanup endpoint is available, LitLaunch stops only the Streamlit backend
process it started. Apps that need custom cleanup can opt into the
`LauncherRuntime` shutdown endpoint.

If an app enables the shutdown endpoint and that request fails or times out,
LitLaunch reports the cleanup problem and still terminates only the Streamlit
backend process it started.

The shutdown request itself uses a short client timeout so stop operations do
not hang indefinitely. `RuntimeSession.stop(graceful_timeout_seconds=...)`
controls how long LitLaunch waits for the backend to exit after a graceful
request is accepted before using the owned-process fallback.

For apps that need custom cleanup, check:

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
