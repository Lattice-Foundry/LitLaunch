# Inspect Diagnostics

`litlaunch inspect` checks local runtime readiness without launching Streamlit,
opening browsers, starting a diagnostics server, or dumping raw environment
variables.

## Text Report

```powershell
litlaunch inspect
litlaunch inspect app.py
```

With a target app, inspect adds:

- app path existence
- command preview
- app URL preview
- health URL preview
- browser resolution summary

## JSON

```powershell
litlaunch inspect app.py --json
litlaunch inspect app.py --json --output litlaunch-report.json
```

JSON is for tools and automation. It uses the same structured report model as
text output.

## Sanitized Bundle

```powershell
litlaunch inspect app.py --bundle
litlaunch inspect app.py --bundle --output litlaunch-report.txt
```

The support bundle is concise and copyable for issues or support requests.

## Sanitization

Inspect output avoids:

- shutdown tokens
- raw environment variable dumps
- full PATH dumps
- sensitive-looking values such as token, secret, password, and key values
- common local home/user path prefixes where practical

Existing output files are not overwritten unless `--force` is supplied.

Sanitization is pattern-based and intentionally lightweight. It is appropriate
for LitLaunch's local diagnostics workflow, but it is not a cryptographic
scrubber. Encoded, base64, URL-wrapped, or heavily reformatted secrets may not
always be detected. Review support bundles before sharing them publicly.

## Not Implemented

There is no HTML inspector/dashboard or local diagnostics server today.

[screenshot needed]
Capture: `litlaunch inspect examples/minimal_app/app.py --no-color` output.
Demonstrate: platform, Streamlit, browser, target, and summary sections.
