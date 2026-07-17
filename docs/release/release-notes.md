# Release notes

Human-simplified notes for GitHub Releases. The full, detailed history lives in
[`CHANGELOG.md`](../../CHANGELOG.md).

## v1.1.1

The headline of the 1.1.x line is **Experimental host sizing** — LitLaunch can
fit the height of an eligible local Windows webapp window to your app's content,
from trusted frontend measurements. It is Experimental and **off by default**.

### Host sizing (application resizing)

- Three policies: `off` (default), `initial` (one stabilized fit near startup),
  and `continuous` (keeps fitting to meaningful later content growth/shrink for
  the runtime session).
- Windows + webapp mode + an explicit Edge/Chrome selection + a LitLaunch-managed
  browser profile + a loopback host. Anything else simply launches normally.
- Height-only: width, position, activation, and monitor placement are preserved.
  User moves, snapping, maximizing, or authority loss stop sizing safely without
  affecting the app. LitLaunch never retries a native mutation.
- The app owns frontend measurement and forwards a short-lived, authenticated
  handoff to one trusted frontend surface; LitLaunch owns the authenticated
  loopback channel, sequencing, stabilization, exact window authority, native
  sizing, work-area clamping, verification, and cleanup.
- `continuous` now keeps tracking content for the whole session (it no longer
  stops after a fixed number of reports), and the loopback endpoint adds a
  Host-header check as defense-in-depth.

### Other improvements since v1.0.10

- Cleaner app-window launches: Streamlit's default toolbar chrome is hidden by
  default (`--show-streamlit-chrome` brings it back).
- Better multi-app isolation: Chromium app-mode uses temporary browser profiles,
  and auto-port now uses the whole configured port range when a port is busy.
- Product-style app icons for profiles, shortcuts, diagnostics, and Windows
  webapp launches via `app_icon`.
- More reliable close-to-shutdown: window monitoring handles small title
  differences more gracefully.

### Reliability and safety hardening

- A filesystem error while preparing the browser can no longer orphan the owned
  Streamlit backend or leak the host-sizing endpoint — everything is cleaned up.
- App cleanup hooks get the full graceful-shutdown budget; a slow-but-present
  cleanup endpoint is reported as a timeout instead of as "not set up".
- The runtime refuses to adopt a foreign server that raced onto the requested
  port instead of the app it started.
- Diagnostics redact credentials embedded in URLs, native shortcuts quote paths
  with special characters correctly on Linux and Windows, and profiles correctly
  round-trip dotted environment-variable names and value-less Streamlit flags.
- The generated diagnostics page renders under Streamlit 1.43+ and is robust to
  unusual app names.

### Notes

- CLI launches stay adaptive on port selection by default; pass `--no-auto-port`
  when you want a fixed port to fail loudly if it is busy.
- Install/upgrade: `pip install --upgrade litlaunch`.
