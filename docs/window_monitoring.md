# Window Monitoring

Window monitoring is experimental and observational.

It is intended for Chromium app-mode flows where closing the app window should
trigger graceful backend shutdown. CLI `--mode webapp` launches enable it by
default where supported; profile launches follow the profile's
`window_monitor.enabled` setting.

## Use

```powershell
litlaunch run app.py --mode webapp --browser edge
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

Use `--no-monitor-window` when you intentionally want a webapp/app-window
launch that keeps running until Ctrl+C or the backend exits on its own.

## Supported Path

Strongest current path:

- Windows 10 or Windows 11
- Edge or Chrome/Chromium
- Chromium app-mode
- visible top-level app window

Unsupported platforms fail clearly when monitoring is enabled.

## Ownership Model

Window monitoring:

- observes candidate windows
- waits for a stable matching app-mode window
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

When a close is observed, `RuntimeSession.stop()` performs graceful shutdown and
owned-backend fallback termination if needed.

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

## Timeout Behavior

If no stable app window is observed before timeout, the monitor reports timeout.
The CLI treats explicit monitor failure as nonzero and stops the owned backend.

## Matching Boundary

LitLaunch currently matches monitored app-mode windows using:

- window title
- Chromium window class signals
- browser process-name signals when available
- baseline handle exclusion
- stable polling

It does not inspect browser URLs. URL inspection would require browser
automation, remote debugging, accessibility scraping, or process command-line
inspection, and those approaches are intentionally outside the current
observational monitoring contract.

Choose a stable `LauncherConfig.title` / `--title` for monitored webapp flows.
If the visible app-mode window title differs significantly from the expected
title, monitoring may time out.

## Future Work

Potential future work includes more platform providers and richer monitor
diagnostics. Monitoring should remain optional unless a future release clearly
defines safe defaults.

For app-window flows, the recommended manual smoke check is to launch with
`--mode webapp --monitor-window`, confirm a separate Chromium app-mode window
appears with the expected title, and close that window to verify LitLaunch stops
only the owned backend session.
