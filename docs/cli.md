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

```powershell
litlaunch run app.py
litlaunch run app.py --mode browser
litlaunch run app.py --mode webapp --browser edge
litlaunch run app.py --port 8501 --host 127.0.0.1
litlaunch run app.py --no-browser-fallback
litlaunch run app.py --dry-run
```

Window monitoring is explicit and webapp-only:

```powershell
litlaunch run app.py --mode webapp --monitor-window
litlaunch run app.py --mode webapp --monitor-window --title "My Streamlit App"
litlaunch run app.py --mode webapp --monitor-window --graceful-timeout 15
```

`--title` sets the expected runtime/app-window title. For monitor-window flows,
choose a stable title that matches the browser app-mode window closely enough
for detection.

`--graceful-timeout` controls the backend-exit wait after a monitored app-window
close triggers graceful shutdown.

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

## Command Preview

```powershell
litlaunch command app.py --server.runOnSave true -- --workspace demo
```

This prints the backend command and does not launch Streamlit or a browser.

## Inspect

```powershell
litlaunch inspect
litlaunch inspect app.py
litlaunch inspect app.py --json
litlaunch inspect app.py --bundle
litlaunch inspect app.py --json --output litlaunch-report.json
litlaunch inspect app.py --bundle --output litlaunch-report.txt --force
```

## Example

```powershell
litlaunch example
```

This reports the minimal example path only when running from a source checkout.
Installed wheels may not include repository-level examples.
