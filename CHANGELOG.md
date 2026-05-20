# Changelog

LitLaunch is pre-alpha. Entries are intentionally concise until the public API
settles.

## 0.71.0

- Added sanitized standalone HTML diagnostics output for `litlaunch inspect`.
- Included profile runtime settings in diagnostics when inspecting a loaded
  profile.

## 0.61.0

- Added `run_profile()` for profile-driven runtime execution through the normal
  or monitored webapp path.
- Routed CLI `run --profile` through the profile runtime path while preserving
  plan-only `command` and `inspect` behavior.

## 0.51.0

- Added `MonitoredRunResult` and `run_monitored_webapp()` for reusable
  monitored Chromium app-mode orchestration.
- Routed CLI `run --monitor-window` through the monitored webapp helper while
  preserving explicit opt-in behavior and backend-only ownership.

## 0.41.0

- Aligned `StreamlitLauncher.build_command()` with launch planning so backend
  command providers are respected consistently.
- Reused configured graceful timeout values on monitor-driven CLI stop paths.
- Clarified editable reinstall and raw Streamlit passthrough guidance.
- Added project launch profiles from `litlaunch.toml` and `[tool.litlaunch]`
  `pyproject.toml` configuration, with CLI support for `run`, `command`, and
  `inspect`.
- Added a Python 3.10-only `tomli` runtime dependency for profile TOML loading.

## 0.31.1

- Documented the window monitoring URL boundary: LitLaunch does not inspect
  browser URLs and uses title, process/class signals, baseline handles, and
  stable polling for monitored app-mode windows.

## 0.31.0

- Added CLI tuning for opt-in window monitoring appearance timeout, poll
  interval, and stable poll count.
- Documented monitor tuning for CLI and Python `WindowMonitorConfig` usage.
- Preserved observational-only window monitoring and backend-owned shutdown
  behavior.

## 0.30.0

- Added launch-time browser fallback retry when fallback is allowed and the
  selected browser fails to open.
- Preserved strict browser behavior when fallback is disabled.
- Kept webapp/app-mode fallback limited to app-mode capable browsers while
  allowing browser mode to fall back to the default browser.

## 0.29.1

- Tightened backend command provider validation for empty commands and
  arguments.
- Added provider contract tests for invalid provider returns, provider start
  failures, frozen command context behavior, and default command preservation.
- Clarified packaged-backend provider documentation and metadata expectations.

## 0.29.0

- Added public backend command provider types for packaged, frozen, and
  embedded backend command customization.
- Wired custom backend commands into launch plans and backend process start
  while preserving LitLaunch-owned env injection, health checks, browser
  launch, and session lifecycle.
- Documented the generic packaged-backend command contract.

## 0.28.0

- Added public `LaunchPlan` and `StreamlitLauncher.build_launch_plan()` for
  inspecting resolved launch behavior without starting Streamlit or opening a
  browser.
- Aligned CLI command previews, dry runs, and inspect target previews around
  the shared launch planning path.
- Included redacted command and environment previews for integration-safe
  diagnostics.

## 0.27.0

- Added `LauncherConfig.cwd` and `LauncherConfig.extra_env` for backend process
  working-directory and child-only environment overrides.
- Ensured LitLaunch shutdown environment injection wins over app-provided
  environment collisions.
- Added `--no-auto-port` for `run`, `command`, and `inspect`.
- Reused sensitive-value redaction for verbose command details and CLI command
  previews.

## 0.26.0

- Added an optional app-side shutdown completion callback that runs after
  shutdown hooks complete and the endpoint response is sent.
- Hardened shutdown endpoint idempotency so hooks and completion callbacks do
  not rerun on duplicate shutdown requests.
- Added configurable graceful-timeout plumbing for monitor-window shutdown.
- Documented generic shutdown hooks, completion callbacks, and monitor-window
  graceful timeout behavior.

## 0.25.0

- Documented inspect redaction limits and support-bundle review expectations.
- Added common home/user path prefix redaction for diagnostics output.
- Clarified the internal shutdown-result storage contract used by the local
  shutdown endpoint.
- Documented the browser adapter naming invariant used by registry resolution.
- Tracked screenshot and diagram placeholders as deferred beta documentation
  work.

## 0.24.0

- Updated package metadata to the Alpha development classifier for TestPyPI
  rehearsal readiness.
- Clarified `run()`/`start()`, `with_port()`, title/window matching, and
  Streamlit flag passthrough expectations in docs.
- Kept temporary internal integration docs excluded from distributions and
  isolated from public docs.
- Avoided duplicate verbose-mode guidance in console failure output.

## 0.23.0

- Clarified and tested `RuntimeSession.wait()` timed-wait behavior.
- Added an optional real Streamlit backend smoke test that avoids browser
  launch and skips when Streamlit is not installed.
- Expanded installed-wheel release smoke checks to cover inspect and command
  preview paths.
- Clarified source-checkout example availability, `run()`/`start()` policy,
  quiet-mode expectations, and graceful shutdown timeout budgets.

## 0.22.0

- Removed stray root artifact handling and strengthened release hygiene checks
  for suspicious repo-root files.
- Excluded temporary `docs/internal/` integration notes from source
  distributions while keeping public docs in release artifacts.
- Cleaned public exports for typed exceptions and shutdown integration helpers.
- Removed dead diagnostics and console-rendering surfaces superseded by inspect
  and the named theme color contract.

## 0.21.0

- Added temporary internal integration docs for RoleThread migration planning,
  beta runtime validation, TestPyPI rehearsal, and Codex handoff continuity.
- Added internal RoleThread runtime mapping, handoff checklist, test matrix,
  and known beta issue tracking while keeping public docs isolated.

## 0.20.0

- Reworked README as a concise beta-quality integration entry point.
- Added repository-native markdown docs for architecture, philosophy,
  installation, quickstart, CLI, browser support, window monitoring, inspect,
  troubleshooting, RoleThread integration, and packaging notes.
- Added operational screenshot and diagram placeholders for future docs polish.

## 0.19.0

- Added calm, actionable failure guidance for backend startup, health timeout,
  browser launch, window monitoring, shutdown fallback, and hook failures.
- Standardized inspect and verbose-mode recovery hints across runtime failures.
- Preserved quiet/normal/verbose console behavior and token redaction.

## 0.18.0

- Added structured runtime console phase rendering for backend startup, health
  checks, browser launch, window monitoring, and shutdown.
- Added concise elapsed timing for key runtime and shutdown phases.
- Improved browser fallback, monitor status, and shutdown hook console messages.

## 0.17.0

- Added stable developer-facing console theme color names and hex values.
- Updated console theme defaults around `[LitLaunch]` prefix, Streamlit blue
  labels, terminal green branding, PowerShell-style red errors, and muted
  warning/detail colors.
- Documented named shutdown-hook color metadata for future polished rendering.

## 0.16.2

- Fixed Windows window-provider fake paths on non-Windows hosts by avoiding
  eager `kernel32` loading when an injected process-name provider is used.
- Added coverage for importing and exercising the Windows provider without
  `ctypes.WinDLL` or `ctypes.WINFUNCTYPE`.

## 0.16.1

- Hardened Windows browser detection to use the real process environment by default.
- Added coverage for Edge discovery through standard Windows Program Files paths.
- Documented the manual webapp window-monitoring smoke checklist.

## 0.16.0

- Added explicit CLI opt-in window monitoring with `litlaunch run --monitor-window`.
- Restricted CLI window monitoring to webapp mode and fail clearly when unsupported.
- Wired monitored app-window close results through `RuntimeSession.stop()`.

## 0.15.0

- Added a Windows HWND capture provider using stable Win32 APIs through `ctypes`.
- Added a Windows Chromium app-mode monitor built on the existing polling monitor.
- Added platform-aware window monitor factory behavior with clean non-Windows fallback.

## 0.14.0

- Added the foundational window monitoring contracts and result types.
- Added no-op and fake-friendly polling window monitor implementations.
- Added opt-in `RuntimeSession.monitor_window()` scaffolding for future app-mode close handling.

## 0.13.2

- Removed CI pip caching after hosted macOS jobs emitted cache warning noise.
- Kept the modernized GitHub Actions versions and cross-platform matrix.

## 0.13.1

- Updated GitHub Actions checkout usage to the current Node 24-backed major.
- Added CI job timeouts and pip caching for lower-noise hosted runs.
- Kept the existing cross-platform Python matrix pending hosted-runner proof.

## 0.13.0

- Added GitHub Actions CI for tests, linting, formatting, and release hygiene.
- Added a cross-platform Python matrix for Windows, Linux, and macOS.
- Hardened Python 3.10 test compatibility for TOML metadata reads.

## 0.12.0

- Added UTC metadata to structured inspect reports.
- Added `litlaunch inspect --json --output` and `--bundle --output`.
- Added safe output-file validation with explicit `--force` overwrite behavior.

## 0.11.0

- Added JSON diagnostics rendering for `litlaunch inspect --json`.
- Added sanitized support bundle output for `litlaunch inspect --bundle`.
- Hardened diagnostics redaction for sensitive-looking report values.

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
