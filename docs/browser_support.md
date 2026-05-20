# Browser Support

LitLaunch supports browser launch strategy through explicit browser capability
detection and adapters.

## Current Targets

| Browser | Browser mode | App-mode | Notes |
| --- | --- | --- | --- |
| Microsoft Edge | Supported | Supported | Strongest Windows app-mode target. |
| Chrome / Chromium | Supported | Supported | Used first on macOS/Linux app-mode preference. |
| Default browser | Supported | Not app-mode | Full browser fallback only. |

## App-Mode

`--mode webapp` uses Chromium-style app-mode arguments:

```powershell
litlaunch run app.py --mode webapp --browser edge
litlaunch run app.py --mode webapp --browser chrome
```

Default browser mode does not provide Chromium app-mode semantics.

## Fallback Policy

By default, LitLaunch may fall back when the requested browser is unavailable
or when the selected browser fails to launch:

```powershell
litlaunch run app.py --browser edge
```

Disable fallback:

```powershell
litlaunch run app.py --browser edge --no-browser-fallback
```

In webapp mode, fallback is limited to app-mode capable browsers. LitLaunch
does not downgrade app-mode to the default browser. In browser mode, fallback
can use the default browser.

When `--no-browser-fallback` is set, LitLaunch tries only the selected browser
capability and reports the launch failure without retrying alternatives.

## Limitations

- Detection never launches browsers.
- Browser processes are not owned or killed.
- Browser profile and process reuse are browser behavior, not LitLaunch state.
- App-mode depends on Chromium-compatible command-line behavior.

[diagram needed]
Create: browser resolution decision tree for browser mode vs webapp mode.
Show: requested browser, fallback allowed/disabled, default browser fallback.
