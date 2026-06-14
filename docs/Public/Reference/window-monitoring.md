# Window Monitoring

Window monitoring is observational: LitLaunch watches supported browser or
app-window surfaces and reacts to lifecycle signals without owning, killing, or
closing browser processes.

It covers two related lifecycle paths:

- monitored webapp/app-window mode, where closing the Chromium app-mode window
  triggers graceful backend shutdown
- managed browser-window mode, where LitLaunch opens a temporary Chromium
  profile in a new top-level browser window and observes that exact window

CLI `--mode webapp` launches enable app-window monitoring by default where
supported. Browser-mode CLI launches attempt managed browser-window monitoring
by default when LitLaunch can use Edge or Chrome/Chromium. Profile launches
follow the profile's `window_monitor.enabled` and
`browser_window_monitor.enabled` settings.

## Use

```powershell
litlaunch run app.py --mode webapp --browser edge
litlaunch run app.py --mode browser --browser edge
```

If app cleanup needs more time after the window closes:

```powershell
litlaunch run app.py --mode webapp --graceful-timeout 15
```

If the app window appears slowly or title matching is noisy, tune the monitor:

```powershell
litlaunch run app.py --mode webapp `
  --monitor-appear-timeout 90 `
  --monitor-poll-interval 0.5 `
  --monitor-stable-polls 3
```

If the browser window title differs from the default title:

```powershell
litlaunch run app.py --mode webapp --title "My Streamlit App"
```

For Streamlit apps, use the same title in the app page config:

```python
st.set_page_config(page_title="My Streamlit App")
```

Use `--no-monitor-window` when you intentionally want a webapp/app-window
launch that keeps running until Ctrl+C or the backend exits on its own. Use
`--no-monitor-browser-window` when you intentionally want browser mode to keep
running until Ctrl+C or backend exit.

## Supported Path

Strongest current path:

- Windows 10 or Windows 11
- Edge or Chrome/Chromium
- Chromium app-mode for webapp monitoring
- managed temporary Chromium profile plus a new top-level window for
  browser-window monitoring
- visible top-level app/browser window

Unsupported platforms fail clearly when monitoring is enabled.

## Ownership Model

Window monitoring:

- observes candidate windows
- waits for a stable matching app-mode window
- can snapshot browser windows before launch and identify a new managed
  browser window after launch
- waits for close signals
- reports monitor outcomes

Window monitoring does not:

- kill browser processes
- close browser windows
- own browser PIDs
- kill by process name
- kill by port owner
- inspect browser URLs
- use browser automation, CDP, remote debugging, or address-bar scraping

When a close is observed, `RuntimeSession.stop()` requests optional app-side
cleanup when the app has enabled it, then stops only the owned backend process
if needed. Plain Streamlit apps do not need app-side setup for the default close
flow.

Managed browser-window mode does not claim general browser-tab ownership. It is
best-effort window observation. If Chromium reuses an existing window, policy
blocks the managed profile, or no confident new top-level window is observed,
LitLaunch reports that fallback and `Ctrl+C` remains the shutdown path.

`--graceful-timeout` controls how long the CLI waits for the backend to exit
after a monitored-window shutdown request is accepted before using the
owned-backend fallback.

Python integrations can pass the same monitoring concepts through
`RuntimeSession.monitor_window(..., config=WindowMonitorConfig(...))`.
`WindowMonitorConfig.appear_timeout_seconds` controls how long to wait for the
window to appear, `poll_interval_seconds` controls polling cadence, and
`stable_poll_count` controls how many matching polls are required before a
window is treated as observed.

For integrations that want LitLaunch to assemble the normal monitored webapp
flow, use `run_monitored_webapp()`. It captures baseline windows before launch,
starts the configured `StreamlitLauncher`, builds the `WindowTarget`, delegates
close detection to `RuntimeSession.monitor_window()`, and returns a
`MonitoredRunResult`. It still observes windows only; backend shutdown remains
owned by the returned session.

```python
from litlaunch import LauncherConfig, LaunchMode, run_monitored_webapp

result = run_monitored_webapp(
    LauncherConfig(
        app_path="app.py",
        title="My Streamlit App",
        mode=LaunchMode.WEBAPP,
        browser="edge",
    ),
    graceful_timeout_seconds=15,
)

if result.exit_code:
    print(result.message)
```

For browser-mode profiles, enable the browser-window monitor explicitly:

```toml
[profiles.browser-window]
app_path = "app.py"
mode = "browser"
browser = "edge"

[profiles.browser-window.browser_window_monitor]
enabled = true
appear_timeout = 8
poll_interval = 0.2
stable_polls = 2
```

## Timeout Behavior

If no stable app window is observed before timeout, the monitor reports timeout.
The CLI treats explicit monitor failure as nonzero and stops the owned backend.
When LitLaunch sees plausible browser windows that do not match, the timeout
message includes the expected title and the observed candidate title so the
profile or CLI `--title` value can be corrected.

## Matching Boundary

LitLaunch currently matches monitored app-mode and managed browser windows
using:

- window title
- Chromium window class signals
- browser process-name signals when available
- baseline handle exclusion
- stable polling

It does not inspect browser URLs. Browser-window mode relies on a managed
temporary Chromium profile and pre-launch/post-launch window snapshots rather
than browser automation. URL inspection would require browser automation,
remote debugging, accessibility scraping, or process command-line inspection,
and those approaches are intentionally outside the current observational
monitoring contract.

Choose a stable `LauncherConfig.title` / `--title` for monitored webapp flows.
When monitoring is enabled, LitLaunch uses the configured app title as the
expected browser window title. For Streamlit apps, this should usually match
`st.set_page_config(page_title="...")`. If the visible app-mode window title
differs significantly from the expected title, monitoring may time out.

LitLaunch also accepts conservative near-title matches such as
`LitBridge Generic Demo` for `LitBridge Generic Interaction Demo`, but matching
the profile title to the framework page title remains the most reliable setup.

## Future Work

Potential future work includes more platform providers and richer monitor
diagnostics. Monitoring should remain observational unless a future release
clearly defines safer defaults.

For app-window flows, the recommended manual smoke check is to launch with
`--mode webapp --monitor-window`, confirm a separate Chromium app-mode window
appears with the expected title, and close that window to verify LitLaunch stops
only the owned backend session.

For browser-window flows, launch with `litlaunch app.py --browser edge`,
confirm the managed browser window opens without first-run/sync prompts, then
close that window and verify LitLaunch runs graceful shutdown. If the monitor
falls back, stop the session with Ctrl+C.
