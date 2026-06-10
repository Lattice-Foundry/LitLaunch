# Browser Support

LitLaunch supports browser launch strategy through explicit browser capability
detection and adapters.

## Current Targets

| Browser | Browser mode | App-mode | Notes |
| --- | --- | --- | --- |
| Microsoft Edge | Supported | Supported | Strongest Windows app-mode and managed browser-window target. |
| Chrome / Chromium | Supported | Supported | Supported for app-mode and managed browser-window launches where available. |
| Default browser | Supported | Not app-mode | LitLaunch may resolve a Chromium default into a managed browser-window launch; otherwise it remains full-browser fallback only. |

## App-Mode

`--mode webapp` uses Chromium-style app-mode arguments:

```powershell
litlaunch run app.py --mode webapp --browser edge
litlaunch run app.py --mode webapp --browser chrome
```

Default browser mode does not provide Chromium app-mode semantics.

App-mode launches use a LitLaunch-managed temporary Chromium profile by
default. The profile is created under `.litlaunch/tmp/browser-profiles/` for
the app project and removed when the LitLaunch runtime session stops. This
keeps simultaneous local app-mode sessions from sharing normal browser profile,
cache, extension, or component state. If a launch explicitly passes
`--browser-arg=--user-data-dir=...`, LitLaunch respects that user profile
choice and does not replace it.

## Managed Browser-Window Mode

Browser mode is not general tab ownership. When LitLaunch can use Edge or
Chrome/Chromium, it may launch a managed browser window instead:

- create a temporary Chromium user-data directory
- suppress first-run/default-browser/sync prompts where supported
- launch with a new top-level browser window
- snapshot windows before and after launch
- observe the exact new window handle
- close window -> graceful backend shutdown

LitLaunch never kills browser processes or closes unrelated windows. If a
managed window cannot be identified confidently, browser mode falls back to the
manual `Ctrl+C` stop path.

Disable managed browser-window monitoring when you want plain browser-mode
ownership:

```powershell
litlaunch run app.py --browser edge --no-monitor-browser-window
```

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
- Managed browser-window lifecycle is best-effort and currently strongest on
  Windows with Edge or Chrome/Chromium.

Resolution is deterministic: LitLaunch starts from the requested browser choice,
checks whether that browser can satisfy the requested mode, and only considers a
fallback when `allow_browser_fallback` is enabled. Browser-tab mode may fall
back to the default browser. App-window mode requires a Chromium-compatible
browser and does not silently downgrade into a normal browser tab.
