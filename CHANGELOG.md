# Changelog

LitLaunch is pre-alpha. Entries are intentionally concise until the public API
settles.

## 0.10.0

- Added structured text diagnostics report types and collector.
- Added `litlaunch inspect [app.py]` for local runtime readiness checks.
- Added plain-text diagnostics rendering without launching Streamlit or browsers.

## 0.9.1

- Added release hygiene tooling for build, metadata, wheel, and sdist checks.
- Added installed-wheel smoke checks for imports and basic CLI commands.
- Added dev-only build and twine tooling for repeatable artifact validation.

## 0.9.0

- Added ordered raw Streamlit argument passthrough and CLI app-arg splitting.
- Added `litlaunch command` and `litlaunch run --dry-run`.
- Improved health failure messages for early backend exits and timeouts.
- Fixed IPv6 shutdown client URL formatting.

## 0.8.4

- Added early host validation and CLI invalid-host coverage.
- Added a webapp/headless configuration guardrail.
- Clarified source-checkout example policy and provisional documentation areas.

## 0.8.3

- Added line-ending normalization metadata for the repository.
- Tightened runtime typing around clock and managed subprocess surfaces.
- Exposed stable dependency-injection utility classes at the top-level API.
- Added metadata and documentation polish before the next feature pass.

## 0.8.2

- Added CLI app-path validation before backend startup.
- Removed provisional public API aliases and dead public surfaces.
- Added Streamlit built-in flag duplication guardrails.
- Added repository line-ending and ignore-file hygiene.

## 0.8.1

- Fixed process stop behavior after kill fallback timeouts.
- Privatized shutdown client access on runtime sessions.
- Prevented duplicate graceful-shutdown hook execution.
- Added typing marker packaging and updated legal/branding docs.

## 0.8.0

- Added the first argparse CLI surface.
- Added version, platform, browser capability, run, and example commands.
- Wired the CLI through the existing runtime and console layers.
