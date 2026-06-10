# CLI Surface Recon

> INTERNAL / RESEARCH DOCUMENTATION
>
> This document preserves pre-release CLI review notes. It is not part of the
> stable public LitLaunch documentation surface.

Absolutely bro. Pulled from the current CLI parser.

**1. Current `litlaunch` Commands**

Public/top-level commands:

```text
litlaunch version
litlaunch platform
litlaunch browsers
litlaunch inspect
litlaunch command
litlaunch run
litlaunch example
```

Internal/dev-facing command:

```text
litlaunch console-preview
litlaunch console-preview --all
litlaunch console-preview --normal
litlaunch console-preview --verbose
```

Global flags available on commands:

```text
--no-color
--quiet
--verbose
-h / --help
```

**2. Raw / Practical Terminal Commands**

Help and discovery:

```text
python -m litlaunch.cli --help
python -m litlaunch.cli run --help
python -m litlaunch.cli command --help
python -m litlaunch.cli inspect --help
python -m litlaunch.cli browsers --help
python -m litlaunch.cli platform --help
python -m litlaunch.cli console-preview --help
```

Version/platform/browser info:

```text
python -m litlaunch.cli version
python -m litlaunch.cli platform
python -m litlaunch.cli platform --verbose
python -m litlaunch.cli browsers
python -m litlaunch.cli browsers --verbose
```

Example path:

```text
python -m litlaunch.cli example
```

Launch a Streamlit app:

```text
python -m litlaunch.cli run app.py
python -m litlaunch.cli run app.py --mode browser
python -m litlaunch.cli run app.py --mode webapp
python -m litlaunch.cli run app.py --browser edge
python -m litlaunch.cli run app.py --browser chrome
python -m litlaunch.cli run app.py --browser default
python -m litlaunch.cli run app.py --port 8501
python -m litlaunch.cli run app.py --host 127.0.0.1
python -m litlaunch.cli run app.py --no-auto-port
python -m litlaunch.cli run app.py --no-browser-fallback
```

Profile-based launch:

```text
python -m litlaunch.cli run --profile my-webapp
python -m litlaunch.cli run --profile my-webapp --config litlaunch.toml
python -m litlaunch.cli run --profile my-webapp --port 8502
```

Window monitoring launch:

```text
python -m litlaunch.cli run app.py --mode webapp --monitor-window
python -m litlaunch.cli run app.py --mode webapp --monitor-window --browser edge
python -m litlaunch.cli run app.py --mode webapp --monitor-window --title "Example App"
python -m litlaunch.cli run app.py --mode webapp --monitor-window --graceful-timeout 15
python -m litlaunch.cli run app.py --mode webapp --monitor-window --monitor-appear-timeout 60
python -m litlaunch.cli run app.py --mode webapp --monitor-window --monitor-poll-interval 1
python -m litlaunch.cli run app.py --mode webapp --monitor-window --monitor-stable-polls 2
```

Dry-run / command preview:

```text
python -m litlaunch.cli run app.py --dry-run
python -m litlaunch.cli command app.py
python -m litlaunch.cli command --profile my-webapp
```

Streamlit/app passthrough args:

```text
python -m litlaunch.cli run app.py --streamlit-flag server.headless=true
python -m litlaunch.cli run app.py --app-arg value
python -m litlaunch.cli command app.py --streamlit-flag server.headless=true
python -m litlaunch.cli command app.py --app-arg value
```

Diagnostics / inspect:

```text
python -m litlaunch.cli inspect
python -m litlaunch.cli inspect app.py
python -m litlaunch.cli inspect --profile my-webapp
python -m litlaunch.cli inspect --profile my-webapp --config litlaunch.toml
```

Diagnostics artifacts:

```text
python -m litlaunch.cli inspect --html --output litlaunch-report.html
python -m litlaunch.cli inspect --json
python -m litlaunch.cli inspect --json --output litlaunch-diagnostics.json
python -m litlaunch.cli inspect --bundle
python -m litlaunch.cli inspect --bundle --output litlaunch-support.txt
python -m litlaunch.cli inspect --html --output litlaunch-report.html --force
```

Inspect with launch options applied:

```text
python -m litlaunch.cli inspect app.py --mode webapp
python -m litlaunch.cli inspect app.py --browser edge
python -m litlaunch.cli inspect app.py --port 8501
python -m litlaunch.cli inspect app.py --host 127.0.0.1
python -m litlaunch.cli inspect app.py --no-auto-port
python -m litlaunch.cli inspect app.py --no-browser-fallback
```

Console preview/dev tooling:

```text
python -m litlaunch.cli console-preview
python -m litlaunch.cli console-preview --all
python -m litlaunch.cli console-preview --normal
python -m litlaunch.cli console-preview --verbose
```

No-color / quiet / verbose variants that commonly matter:

```text
python -m litlaunch.cli run app.py --no-color
python -m litlaunch.cli run app.py --quiet
python -m litlaunch.cli run app.py --verbose
python -m litlaunch.cli inspect --html --output litlaunch-report.html --no-color
python -m litlaunch.cli browsers --verbose --no-color
python -m litlaunch.cli platform --verbose --no-color
```
