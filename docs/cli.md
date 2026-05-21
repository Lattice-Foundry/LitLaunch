# CLI

LitLaunch uses stdlib `argparse`. The CLI is intentionally thin over the Python
runtime APIs.

## Commands

```powershell
litlaunch version
litlaunch platform
litlaunch browsers
litlaunch inspect [app_path]
litlaunch command <app_path>
litlaunch run <app_path>
litlaunch <app_path>
litlaunch --profile <profile>
litlaunch example
```

## Global Flags

```powershell
--no-color
--quiet
--verbose
```

Quiet suppresses routine output, but essential errors and failure guidance may
still be emitted. Verbose adds sanitized details.

## Run

Friendly shorthand:

```powershell
litlaunch app.py
litlaunch app.py --mode webapp --browser edge
litlaunch --profile my-webapp
litlaunch --profile my-webapp --port 8502
```

Explicit launch form:

```powershell
litlaunch run app.py
litlaunch run app.py --mode browser
litlaunch run app.py --mode webapp --browser edge
litlaunch run app.py --port 8501 --host 127.0.0.1
litlaunch run app.py --port 8501 --no-auto-port
litlaunch run app.py --no-browser-fallback
litlaunch run app.py --dry-run
litlaunch run --profile my-webapp
litlaunch run --config litlaunch.toml --profile my-webapp
```

Both forms use the same internal launch pipeline. Bare profile names such as
`litlaunch my-webapp` are intentionally unsupported; use `--profile` to keep
profile launches distinct from paths and future commands.

Window monitoring is explicit and webapp-only:

```powershell
litlaunch run app.py --mode webapp --monitor-window
litlaunch run app.py --mode webapp --monitor-window --title "My Streamlit App"
litlaunch run app.py --mode webapp --monitor-window --graceful-timeout 15
litlaunch run app.py --mode webapp --monitor-window --monitor-appear-timeout 90
litlaunch run app.py --mode webapp --monitor-window --monitor-poll-interval 0.5
litlaunch run app.py --mode webapp --monitor-window --monitor-stable-polls 3
```

`--title` sets the expected runtime/app-window title. For monitor-window flows,
choose a stable title that matches the browser app-mode window closely enough
for detection.

`--graceful-timeout` controls the backend-exit wait after a monitored app-window
close triggers graceful shutdown.

`--monitor-appear-timeout`, `--monitor-poll-interval`, and
`--monitor-stable-polls` tune observational window detection only. They do not
make LitLaunch own, close, or kill browser windows.

Window monitoring matches title, Chromium window class/process signals,
baseline handles, and stable polling. It does not inspect browser URLs; choose a
stable `--title` for monitored webapp flows.

## Streamlit Passthrough

Unknown arguments before `--` are forwarded to Streamlit:

```powershell
litlaunch run app.py --server.runOnSave true --theme.base=dark
```

Arguments after `--` are app arguments:

```powershell
litlaunch run app.py --server.fileWatcherType none -- --workspace demo
```

Structured flags remain available:

```powershell
litlaunch run app.py --streamlit-flag server.maxUploadSize=200 --app-arg demo
```

Avoid specifying the same Streamlit option through both structured
`--streamlit-flag` and raw passthrough arguments. LitLaunch avoids duplicating
its own built-in defaults, but it does not deduplicate repeated user-supplied
Streamlit options.

Prefer explicit LitLaunch flags such as `--host`, `--port`, `--no-auto-port`,
and `--mode` for LitLaunch-owned behavior. Raw Streamlit passthrough remains an
escape hatch and may duplicate those values if callers provide overlapping
Streamlit config flags manually.

## Command Preview

```powershell
litlaunch command app.py --server.runOnSave true -- --workspace demo
```

This prints the backend command and does not launch Streamlit or a browser.
Use `--no-auto-port` with `command` when you want fixed-port availability
checked instead of allowing automatic port selection.

`litlaunch command` and `litlaunch run --dry-run` use the same launch planning
path exposed to Python integrations through
`StreamlitLauncher.build_launch_plan()`.

## Developer Console Preview

LitLaunch includes hidden developer-facing preview tooling for console renderer
work. These commands are intended for rapid formatting, category, color, and
verbosity review; they are not a stable public output contract.

```powershell
litlaunch console-preview --all
litlaunch console-preview --normal
litlaunch console-preview --verbose
```

`--all` renders both normal and verbose examples. `--normal` and `--verbose`
render only that console mode. The preview does not start Streamlit, open a
browser, inspect windows, or touch ports. Some values are simulated so the
output resembles real runtime views, including backend IDs, URLs, browser
fallbacks, monitor statuses, and shutdown hook results.

## Inspect

```powershell
litlaunch inspect
litlaunch inspect app.py --html
litlaunch inspect app.py --json
litlaunch inspect app.py --bundle
litlaunch inspect app.py --html --output litlaunch-report.html
litlaunch inspect app.py --json --output litlaunch-report.json
litlaunch inspect app.py --bundle --output litlaunch-report.txt --force
```

Plain `litlaunch inspect` prints concise guidance for choosing an output
format. Use `--html` for the recommended human-readable diagnostics report,
`--json` for tools, or `--bundle` for a copyable support artifact.

Use `--no-auto-port` with `inspect` to validate fixed-port behavior before a
launch.

Profiles work with inspect too:

```powershell
litlaunch inspect --profile my-webapp --html --output litlaunch-report.html
litlaunch inspect --config pyproject.toml --profile my-webapp --json
```

## Profiles

LitLaunch profiles are reusable launch/runtime settings loaded from either
`litlaunch.toml`:

```toml
[profiles.my-webapp]
app_path = "app.py"
title = "My App"
mode = "webapp"
browser = "edge"
host = "127.0.0.1"
port = 8501
auto_port = false
headless = true
allow_browser_fallback = false
graceful_timeout = 15

[profiles.my-webapp.window_monitor]
enabled = true
appear_timeout = 60
poll_interval = 1
stable_polls = 2
```

or the equivalent `pyproject.toml` table:

```toml
[tool.litlaunch.profiles.my-webapp]
app_path = "app.py"
title = "My App"
```

Profile values load first. Explicit CLI arguments override profile values, so
`litlaunch run --profile my-webapp --port 8502` keeps the profile but changes
the port. If both `litlaunch.toml` and `pyproject.toml` contain profiles, use
`--config` so LitLaunch does not guess.

`run --profile` uses the profile runtime path. If the profile enables
`window_monitor`, LitLaunch runs the monitored webapp flow; otherwise it uses
the normal launcher runtime flow. `command --profile` and `inspect --profile`
remain plan-oriented and do not launch the backend or browser.

## Example

```powershell
litlaunch example
```

This reports the minimal example path only when running from a source checkout.
Installed wheels may not include repository-level examples.
