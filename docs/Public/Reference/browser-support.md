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
default. The profile is created under LitLaunch's runtime state root, which
defaults to system temp, and is removed when the LitLaunch runtime session
stops. This keeps simultaneous local app-mode sessions from sharing normal
browser profile, cache, extension, or component state without silently writing
browser cache into a source tree. Use `--runtime-state-root` or profile
`runtime_state_root` when an app or package needs an explicit state location.
If a launch explicitly passes `--browser-arg=--user-data-dir=...`, LitLaunch
respects that user profile choice and does not replace or clean it.

## Custom App Icons

Profiles and CLI launches can configure an app identity icon. For the strongest
Windows app-window behavior, use a real `.ico` file and run in webapp mode:

```powershell
litlaunch app.py --mode webapp --title "My App" --app-icon assets/my-app.ico
```

```toml
[profiles.my-webapp]
app_path = "app.py"
title = "My App"
mode = "webapp"
app_icon = "assets/my-app.ico"
```

In the Streamlit app, match the page title to the LitLaunch title so monitored
app-window detection can reliably find the window:

```python
import streamlit as st

st.set_page_config(page_title="My App")
```

For reusable local launches:

```powershell
litlaunch create profile --name my-webapp --app app.py --app-icon assets/my-app.ico
litlaunch create shortcut --profile my-webapp
litlaunch --profile my-webapp
```

`app_icon` accepts `.ico`, `.png`, `.svg`, and `.icns` paths for profile,
diagnostic, and shortcut metadata. Use `.ico` for Windows app-window icon
behavior. The icon path may be absolute or relative to the profile file.

Chromium and Edge app-mode command lines do not expose a stable custom icon
flag for one-off temporary app windows. LitLaunch therefore treats app icons as
best-effort app identity metadata and uses the strongest supported surface it
can find:

- native shortcuts use the configured icon where the shortcut format supports
  it;
- Windows `.ico` webapp launches first try a LitLaunch-generated temporary
  `.lnk` with icon metadata before Edge/Chrome starts;
- Windows monitored app-window launches also attempt a best-effort live `.ico`
  window icon override through Win32 window messaging after the monitored
  app window is observed;
- browser-tab launches ignore app icons;
- unsupported platforms, browsers, and image formats fall back without breaking
  the launch.

Chrome/Chromium may honor the shortcut identity immediately. Edge may briefly
show the browser icon before LitLaunch observes the app window and applies the
live override. Browsers may still show their own icon on some taskbar, Alt-Tab,
dock, or title-bar surfaces. Icon handling is intentionally quiet in runtime
diagnostics because it is presentation polish, not a launch-health condition.

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
- Custom app icons are best-effort; one-off Chromium app-mode launches do not
  provide a stable cross-platform icon flag, so LitLaunch uses shortcut/window
  icon metadata where supported.
- Managed browser-window lifecycle is best-effort and currently strongest on
  Windows with Edge or Chrome/Chromium.

Resolution is deterministic: LitLaunch starts from the requested browser choice,
checks whether that browser can satisfy the requested mode, and only considers a
fallback when `allow_browser_fallback` is enabled. Browser-tab mode may fall
back to the default browser. App-window mode requires a Chromium-compatible
browser and does not silently downgrade into a normal browser tab.
