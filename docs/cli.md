# CLI

LitLaunch uses stdlib `argparse`. The CLI is intentionally thin over the Python
runtime APIs.

## Commands

```powershell
litlaunch version
litlaunch platform
litlaunch browsers
litlaunch help [topic]
litlaunch inspect [app_path]
litlaunch report [app_path]
litlaunch command <app_path>
litlaunch run <app_path>
litlaunch <app_path>
litlaunch --profile <profile>
litlaunch create profile
litlaunch create shortcut --profile <profile>
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

## Help

Use argparse help for command reference:

```powershell
litlaunch --help
litlaunch run --help
litlaunch report --help
```

Use workflow help for practical guidance:

```powershell
litlaunch help
litlaunch help launch
litlaunch help diagnostics
litlaunch help profiles
litlaunch help tools
litlaunch help examples
litlaunch help dev
```

`litlaunch help dev` documents internal developer-facing console preview
tooling. It is useful for contributors, but it is not a stable public workflow
contract.

## Run

Friendly shorthand:

```powershell
litlaunch app.py
litlaunch app.py --mode webapp --browser edge
litlaunch --profile my-webapp
litlaunch --profile my-webapp --port 8502
litlaunch report --profile my-webapp
```

Explicit launch form:

```powershell
litlaunch run app.py
litlaunch run app.py --mode browser
litlaunch run app.py --mode webapp --browser edge
litlaunch run app.py --port 8501 --host 127.0.0.1
litlaunch run app.py --port 8501 --no-auto-port
litlaunch run app.py --host 0.0.0.0 --allow-network-exposure
litlaunch run app.py --no-browser-fallback
litlaunch run app.py --dry-run
litlaunch run --profile my-webapp
litlaunch run --config litlaunch.toml --profile my-webapp
```

Both forms use the same internal launch pipeline. Bare profile names such as
`litlaunch my-webapp` are intentionally unsupported; use `--profile` to keep
profile launches distinct from paths and future commands.

Browser-window monitoring is enabled by default for browser-mode CLI launches
where LitLaunch can use a Chromium browser. LitLaunch creates a managed
temporary Chromium profile, opens a new top-level browser window, observes that
exact window, and routes close-to-shutdown through the same graceful
`RuntimeSession.stop()` path. If no confident browser window is observed,
LitLaunch falls back cleanly to the manual `Ctrl+C` stop path.

Use `--no-monitor-browser-window` when you intentionally want browser mode to
keep running until `Ctrl+C` or backend exit.

CLI webapp launches enable app-window close monitoring by default where window
monitoring is supported; use `--no-monitor-window` only when you intentionally
want an unmonitored app window.

```powershell
litlaunch run app.py --mode browser --browser edge
litlaunch run app.py --mode browser --browser edge --no-monitor-browser-window
litlaunch run app.py --mode webapp
litlaunch run app.py --mode webapp --title "My Streamlit App"
litlaunch run app.py --mode webapp --graceful-timeout 15
litlaunch run app.py --mode webapp --monitor-appear-timeout 90
litlaunch run app.py --mode webapp --monitor-poll-interval 0.5
litlaunch run app.py --mode webapp --monitor-stable-polls 3
litlaunch run app.py --mode webapp --no-monitor-window
```

`--title` sets the expected runtime/app-window title. For monitored webapp
flows, choose a stable title that matches the browser app-mode window closely
enough for detection.

`--graceful-timeout` controls the backend-exit wait after a monitored browser
or app-window close triggers graceful shutdown.

`--monitor-appear-timeout`, `--monitor-poll-interval`, and
`--monitor-stable-polls` tune observational window detection only. They do not
make LitLaunch own, close, or kill browser windows.

Window monitoring matches title, Chromium window class/process signals,
baseline handles, and stable polling. It does not inspect browser URLs.

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

`127.0.0.1` is the default localhost-only host. Non-loopback hosts such as
`0.0.0.0`, `::`, LAN IPs, or internal hostnames may expose the app beyond this
machine depending on routing and firewall configuration. LitLaunch requires
`--allow-network-exposure` or `allow_network_exposure = true` in a profile
before launching with those bindings. LitLaunch does not add authentication or
otherwise secure Streamlit applications.

Use `--trust-mode` to declare the operational intent for a launch:

```powershell
litlaunch app.py --trust-mode development
litlaunch app.py --trust-mode strict_local
litlaunch app.py --host 0.0.0.0 --trust-mode internal_network --allow-network-exposure
```

`strict_local` refuses non-loopback hosts even when exposure is acknowledged.
`internal_network` allows deliberate non-loopback use only with explicit
acknowledgement. Trust modes govern LitLaunch runtime behavior; they do not
secure the Streamlit application.

Wildcard bind addresses remain bind/listen addresses. LitLaunch still uses a
client URL such as `http://127.0.0.1:8501` or `http://[::1]:8501` for health
checks and local browser launch while Streamlit remains bound to the requested
network-visible host.

For Streamlit-native TLS, pass Streamlit's cert/key settings through the same
flag/profile path. LitLaunch reports these settings in diagnostics, but does
not terminate TLS or manage certificates:

```powershell
litlaunch run app.py --host 0.0.0.0 --trust-mode internal_network --allow-network-exposure `
  --streamlit-flag server.sslCertFile=cert.pem `
  --streamlit-flag server.sslKeyFile=key.pem
```

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

## Report

`litlaunch report` is the ergonomic human-readable diagnostics workflow. It
generates the same sanitized standalone HTML diagnostics report as
`litlaunch inspect --html`.

```powershell
litlaunch report
litlaunch report app.py
litlaunch report --profile my-webapp
litlaunch report --profile my-webapp --output my-report.html
litlaunch report --profile my-webapp --output my-report.html --force
litlaunch report --profile my-webapp --open
litlaunch report app.py --host 0.0.0.0 --trust-mode internal_network --allow-network-exposure
litlaunch report app.py --host 0.0.0.0 --trust-mode internal_network --allow-network-exposure `
  --streamlit-flag server.sslCertFile=cert.pem `
  --streamlit-flag server.sslKeyFile=key.pem
```

By default, reports are written to `litlaunch-report.html` in the current
working directory. Existing files are not overwritten unless `--force` is
provided. `--open` opens the generated HTML file in the default browser after a
successful write; if opening fails, report generation still succeeds and
LitLaunch emits a warning.

HTML, JSON, and support-bundle diagnostics include `Runtime Governance`,
`Runtime Exposure`, and `Transport Security` sections. These sections summarize
trust mode, host exposure scope, acknowledgement state, Streamlit-native TLS
posture, and plaintext network-exposure risk. They are operational posture
reports, not compliance ratings.

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
litlaunch inspect app.py --trust-mode internal_network --html
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
allow_network_exposure = false
trust_mode = "development"
graceful_timeout = 15

[profiles.my-webapp.window_monitor]
enabled = true
appear_timeout = 60
poll_interval = 1
stable_polls = 2

[profiles.my-webapp.browser_window_monitor]
enabled = true
appear_timeout = 8
poll_interval = 0.2
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
`window_monitor`, LitLaunch runs the monitored webapp flow. If it enables
`browser_window_monitor`, LitLaunch runs the managed browser-window flow.
Otherwise it uses the normal launcher runtime flow. `command --profile` and
`inspect --profile` remain plan-oriented and do not launch the backend or
browser.

Governance-oriented profile examples:

```toml
[profiles.local-only]
app_path = "app.py"
host = "127.0.0.1"
trust_mode = "strict_local"

[profiles.internal-dashboard]
app_path = "app.py"
host = "0.0.0.0"
trust_mode = "internal_network"
allow_network_exposure = true

[profiles.internal-dashboard-tls]
app_path = "app.py"
host = "0.0.0.0"
trust_mode = "internal_network"
allow_network_exposure = true

[profiles.internal-dashboard-tls.streamlit_flags]
"server.sslCertFile" = "cert.pem"
"server.sslKeyFile" = "key.pem"
```

Streamlit-native TLS encrypts transport. It does not add app authentication,
and LitLaunch does not terminate TLS or secure Streamlit applications.

Create a new `litlaunch.toml` profile interactively:

```powershell
litlaunch create profile
litlaunch create profile --name my-webapp --app app.py
litlaunch create profile --dry-run
```

Simple mode defaults to the recommended app-window experience, while still
allowing browser-tab profiles. Advanced mode exposes the fuller runtime profile
surface, including network settings, browser fallback, monitor tuning,
Streamlit flags, app args, working directory, and extra environment variables.
Non-loopback hosts are called out during the wizard, and `extra_env` values are
stored as plaintext in `litlaunch.toml`.
When run from an app root, the wizard uses detected values such as `app.py`, the
project folder name, and an existing `litlaunch.toml` as visible prompt
defaults. Users still confirm or change each value before anything is written.
Type `back` to return to the previous step, or `quit` to cancel cleanly. After
writing a profile, the wizard offers to create the same project-local shortcut
that `litlaunch create shortcut --profile NAME` creates.

Create a project-local launch shortcut for an existing profile:

```powershell
litlaunch create shortcut --profile my-webapp
litlaunch create shortcut --profile my-webapp --dry-run
litlaunch create shortcut --profile my-webapp --output Launch.bat --force
```

Shortcut creation writes a `.bat`, `.sh`, or `.command` file into the profile app
root by default. It does not launch the app, modify the Desktop, or install Start
Menu entries. The generated file uses the public `litlaunch --profile NAME`
workflow so it remains easy to inspect and move.

## Example

```powershell
litlaunch example
```

This reports the minimal example path only when running from a source checkout.
Installed wheels may not include repository-level examples.
