# Window Monitoring

Window monitoring is experimental, opt-in, and observational.

It is intended for Chromium app-mode flows where closing the app window should
trigger graceful backend shutdown.

## Use

```powershell
litlaunch run app.py --mode webapp --monitor-window --browser edge
```

If the browser window title differs from the default title:

```powershell
litlaunch run app.py --mode webapp --monitor-window --title "My Streamlit App"
```

## Supported Path

Strongest current path:

- Windows 10 or Windows 11
- Edge or Chrome/Chromium
- Chromium app-mode
- visible top-level app window

Unsupported platforms fail clearly when `--monitor-window` is explicitly
requested.

## Ownership Model

Window monitoring:

- observes candidate windows
- waits for close signals
- reports monitor outcomes

Window monitoring does not:

- kill browser processes
- close browser windows
- own browser PIDs
- kill by process name
- kill by port owner

When a close is observed, `RuntimeSession.stop()` performs graceful shutdown and
owned-backend fallback termination if needed.

## Timeout Behavior

If no stable app window is observed before timeout, the monitor reports timeout.
The CLI treats explicit monitor failure as nonzero and stops the owned backend.

## Future Work

Potential future work includes more platform providers and richer monitor
diagnostics. Monitoring should remain optional unless a future release clearly
defines safe defaults.

[screenshot needed]
Capture: Windows Edge app-mode minimal app window launched by LitLaunch.
Demonstrate: title matching and separate app-mode window.

