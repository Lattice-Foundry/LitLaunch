# Changelog

LitLaunch is in beta stabilization. Entries are intentionally concise while the
public API finishes settling.

## 0.91.42b0

- Tuned runtime console verbosity so normal mode keeps lifecycle milestones
  while verbose mode shows backend/browser handoff and shutdown request details.
- Split early backend health failure guidance into a concise cause plus
  actionable next-step lines.

## 0.91.41b0

- Hardened managed Chromium/Edge browser-window launches by seeding temporary
  profiles with first-run state and adding sync/onboarding/default-browser
  suppression switches.
- Kept the managed browser profile temporary and non-controlling: LitLaunch
  still observes user-closed browser windows and removes the temporary profile
  after the runtime exits.

## 0.91.40b0

- Upgraded browser-mode window observation to use a LitLaunch-managed
  temporary Chromium profile for direct CLI launches, combining
  `--user-data-dir`, `--new-window`, and window naming to make HWND detection
  more deterministic.
- Kept browser-mode observation non-controlling: LitLaunch watches for
  user-closed windows and still falls back to Ctrl+C when no confident browser
  window can be matched.

## 0.91.39b0

- Enabled the browser-window lifecycle monitor for plain browser
  CLI launches so `litlaunch app.py` can exercise the HWND baseline/diff path
  without extra flags.
- For plain auto-browser CLI launches, LitLaunch now nudges browser-mode launches
  toward a monitorable Edge/Chromium new-window launch while retaining a hidden
  opt-out and Ctrl+C fallback.

## 0.91.38b0

- Added a browser-window lifecycle monitor for explicit
  Edge/Chrome browser mode using pre-launch HWND baselines and exact-window
  close observation.
- Kept normal browser-mode defaults unchanged: Ctrl+C remains the guaranteed
  shutdown path and webapp mode remains the recommended close-to-shutdown flow.

## 0.91.37b0

- Clarified browser-mode runtime messaging so users know Ctrl+C is the
  shutdown path for normal browser-tab sessions.

## 0.91.36b0

- Restored Ctrl+C shutdown reliability by keeping the owned backend in the
  parent console signal path while preserving LitLaunch's backend-only
  ownership boundary.
- Hardened monitored webapp interrupt handling so Ctrl+C during window
  monitoring routes through the same runtime stop path.
- Matched transient URL-style Edge app-window titles during startup so quick
  closes before Streamlit's page title settles still trigger shutdown.

## 0.91.35b0

- Enabled window monitoring by default for direct CLI `--mode webapp` launches
  where supported so app-window close events can initiate graceful shutdown.
- Added `--no-monitor-window` as an explicit app-window monitoring opt-out.
- Updated window-monitoring docs to reflect the default app-window lifecycle
  behavior.

## 0.91.34b0

- Isolated LitLaunch-owned backend subprocesses from parent terminal interrupts
  so Ctrl+C is handled by LitLaunch first and can request app-side graceful
  shutdown hooks before falling back to backend termination.
- Kept backend ownership scoped to the process LitLaunch starts while
  preserving existing fallback stop behavior.

## 0.91.33b0

- Changed LitLaunch-owned browser launches to suppress Streamlit's native
  browser opener by default, preventing duplicate tabs/windows in generic
  `litlaunch app.py` runs.
- Preserved explicit opt-in to Streamlit-native browser opening through
  `headless = false` or raw `server.headless=false` Streamlit flags.
- Documented the RoleThread integration finding that profile/app-window paths
  should use `rolethread-webapp` for monitored close-to-shutdown behavior.

## 0.91.32b0

- Aligned public docs, workflow help, and argparse help with the completed
  Stage 1 runtime-governance features.
- Added workflow guidance for trust modes, runtime governance, runtime
  exposure, transport security, and Streamlit-native TLS diagnostics.
- Updated README, quickstart, CLI, inspect, and security docs so normal users
  keep the simple local-first path while advanced users can discover governance
  and posture reporting.
- Improved README/PyPI first-read positioning around LitLaunch as a
  runtime-governance and operational-launch layer for Streamlit apps.
- Added README/overview positioning for packaged, distributed, and
  cross-platform Streamlit app workflows while keeping packaging and installer
  creation out of scope.
- Kept wording explicit that LitLaunch reports operational posture and does not
  secure Streamlit applications.

## 0.91.31b0

- Added a lightweight runtime governance assessment layer that composes trust
  mode, host exposure, acknowledgement state, and transport/TLS posture.
- Added a concise `Runtime Governance` diagnostics summary so reports show
  launch allowed/blocked posture, highest severity, and top recommendation
  without duplicating full exposure and transport sections.
- Routed launch-time exposure enforcement through the governance evaluator while
  preserving existing `development`, `strict_local`, and `internal_network`
  behavior.
- Documented governance assessment as operational runtime posture, not a
  security score, policy engine, auth layer, signing system, or audit log.

## 0.91.30b0

- Added transport security diagnostics that detect Streamlit-native TLS
  settings and report plaintext network-exposure risk.
- Added TLS-aware runtime exposure guidance so non-loopback launch warnings
  distinguish plaintext HTTP from Streamlit TLS-configured launches.
- Extended inspect/report JSON, HTML, and support-bundle output with
  `Transport Security` posture data without adding TLS termination,
  certificate management, auth, or reverse-proxy behavior.
- Documented LitLaunch's transport-security boundary and recommended
  Streamlit-native or infrastructure-native TLS paths for internal deployments.

## 0.91.29b0

- Added runtime exposure/posture diagnostics that summarize host binding scope,
  trust mode, acknowledgement state, and whether current policy allows launch.
- Expanded host exposure classification for localhost, loopback IPs, wildcard
  binds, local-network addresses, and public or unknown hostnames.
- Added operational posture reminders for loopback shutdown hooks, diagnostics
  privacy, plaintext profile environment values, and browser ownership
  boundaries.
- Extended HTML, JSON, and support-bundle diagnostics with posture data without
  adding TLS, auth, policy engines, or new runtime behavior.

## 0.91.28b0

- Added a lightweight `trust_mode` foundation with `development`,
  `strict_local`, and `internal_network` operational postures.
- Wired trust mode through `LauncherConfig`, profiles, CLI runtime/diagnostics
  flags, profile writing, and diagnostics target output.
- Integrated trust mode with existing network exposure guardrails so
  `strict_local` refuses non-loopback hosts even when exposure is acknowledged.
- Documented trust modes as runtime governance settings, not application
  security or authentication.

## 0.91.27b0

- Made port availability checks address-family aware, including bracketed IPv6
  hosts and localhost resolutions that return both IPv4 and IPv6 addresses.
- Expanded CI coverage to every advertised Python version from 3.10 through
  3.14 across Windows, Linux, and macOS.
- Removed fragile argparse private-action mutation for hidden developer preview
  tooling and cleaned remaining CLI implementation drift.
- Hardened release hygiene checks for repo-root temp artifacts, stale generated
  reports, and bytecode/cache artifacts outside ignored local environments.

## 0.91.26b0

- Centralized console ANSI styling and status-label formatting behind a shared
  presentation helper used by runtime console, workflow help, argparse color
  bridging, and profile wizard output.
- Routed profile wizard warning/status coloring through the shared console
  styling layer and removed local raw ANSI helpers.
- Removed dead console phase enum members and unused ad hoc color aliases while
  preserving current runtime, help, preview, and wizard output behavior.

## 0.91.25b0

- Added explicit non-loopback host exposure detection, launch warnings, and
  acknowledgement support through CLI/profile/env paths.
- Surfaced host-binding exposure posture in diagnostics and strengthened
  support-bundle privacy wording.
- Hardened profile TOML escaping, validation-before-write, atomic profile file
  replacement, and Windows shortcut batch quoting.
- Added concise security/trust-boundary documentation without changing runtime
  ownership behavior.

## 0.91.24b0

- Added focused automated coverage for the profile wizard and LitLaunch profile
  writer.
- Corrected public example links to the canonical `Lattice-Foundry/LitLaunch`
  GitHub repository casing.
- Removed public documentation placeholders and refreshed integration docs for
  current profile and shortcut workflows.
- Cleaned repo-root temporary test directory usage from profile-related tests.

## 0.91.23b1

- Finalized CLI Tools documentation for profile and shortcut creation workflows.
- Normalized workflow help and argparse help around `litlaunch create profile`
  and `litlaunch create shortcut --profile NAME`.
- Updated public docs to present shorthand launch, report, profile creation, and
  shortcut creation as the current ergonomic command system.

## 0.91.23b0

- Added optional shortcut creation after successful `litlaunch create profile`
  writes.
- Reused the standalone shortcut writer internals from the profile wizard
  without launching apps or duplicating shortcut generation logic.
- Preserved dry-run behavior so previewing a profile never writes shortcut
  files.

## 0.91.22b0

- Added standalone `litlaunch create shortcut --profile NAME` workflow.
- Added reusable shortcut planning/writing internals for `.bat`, `.sh`, and
  `.command` profile launch files.
- Added dry-run, overwrite protection, explicit output paths, and app-root
  default placement without changing runtime launch behavior.

## 0.91.21b0

- Implemented Advanced mode for `litlaunch create profile`.
- Added grouped wizard prompts for network settings, browser/runtime behavior,
  monitor tuning, Streamlit flags, app args, working directory, and extra
  environment variables.
- Reused the existing wizard state, app-root detection, back navigation,
  cancellation, dry-run, and profile writer paths with no runtime behavior
  changes.

## 0.91.20b0

- Polished the `litlaunch create profile` wizard with a clearer header, step
  framing, current-profile summary, clean cancellation, and back/quit prompt
  controls.
- Fixed Ctrl+C cancellation so the wizard exits calmly without a Python
  traceback.
- Preserved Simple mode behavior, app-root defaults, and profile loading
  validation.

## 0.91.19b0

- Added reusable app-root detection for profile creation defaults.
- Improved `litlaunch create profile` Simple mode defaults for app path,
  profile name, title, config path, and existing profile collision awareness.
- Preserved the full interactive wizard flow while making app-root profile
  creation faster and more transparent.

## 0.91.18b0

- Added the `litlaunch create profile` command namespace with an interactive
  Simple mode profile wizard.
- Made app-window/webapp profiles the recommended default while preserving
  browser-tab profile creation.
- Added a small LitLaunch-owned `litlaunch.toml` writer that validates generated
  profiles through the existing profile loader without changing runtime behavior.

## 0.91.17b0

- Normalized `litlaunch help` workflow topics around the finalized launch,
  report, inspect, profile, planning, info, and developer-tool commands.
- Aligned workflow help color usage with the approved LitLaunch console palette
  and removed stray lighter/lime green styling.
- Clarified that `--help` remains command reference help while
  `litlaunch help ...` remains concise workflow guidance.

## 0.91.16b0

- Added `litlaunch help` workflow guidance for launch, diagnostics, profiles,
  examples, and developer tooling.
- Kept argparse `--help` behavior as command/reference help while making
  `litlaunch help ...` focused on practical workflows.
- Documented the new help workflow without changing runtime, diagnostics, or
  browser behavior.

## 0.91.15b0

- Added `litlaunch report` as an ergonomic standalone HTML diagnostics workflow
  with default `litlaunch-report.html` output.
- Added report `--output`, `--force`, and warning-only `--open` support while
  preserving the explicit `litlaunch inspect --html|--json|--bundle` commands.
- Routed report generation through the shared diagnostics collection and HTML
  rendering path without changing diagnostics schema or collection behavior.

## 0.91.14b0

- Added root launch shorthand so `litlaunch app.py` and
  `litlaunch --profile my-webapp` route through the same internal launch path
  as `litlaunch run`.
- Preserved explicit `litlaunch run ...` workflows and kept bare profile names
  unsupported to avoid command/path ambiguity.
- Updated CLI docs with the friendly shorthand and explicit power-user forms.

## 0.91.13b0

- Polished `platform` and `browsers` informational CLI output with aligned
  status rows and readable verbose metadata.
- Replaced legacy browser `>`/dash output and raw platform field dumps with
  coherent console grammar.
- Added a neutral `info` status label for informational CLI metadata without
  changing platform or browser detection behavior.

## 0.91.12b0

- Removed the legacy full text inspect report before public release.
- Made plain `litlaunch inspect` print concise format guidance instead of a
  redundant human report.
- Kept HTML diagnostics as the human-readable report surface and preserved JSON
  diagnostics and sanitized support bundle behavior without changing collection
  semantics or schema.

## 0.91.11b0

- Polished HTML diagnostics empty-detail cells so they render as intentional
  placeholders instead of empty code elements.
- Added top-level profile context to HTML diagnostics reports when a profile is
  present.
- Tuned HTML warning badge colors and path-heavy value readability without
  changing diagnostics collection or JSON schema.

## 0.91.10b0

- Corrected `inspect --output` help so it accurately covers JSON, HTML, and
  bundle output files.
- Polished standalone HTML diagnostics reports with clearer summary cards,
  status badges, long-value wrapping, and stronger privacy guidance.
- Preserved diagnostics collection behavior, JSON schema, and support bundle
  rendering semantics.

## 0.91.9b0

- Documented hidden `console-preview --all|--normal|--verbose` developer
  tooling for rapid console formatting, color, and verbosity review.
- Clarified shutdown hook console behavior, including the orange `Hook:`
  category, unstyled hook message text, and preserved hook color metadata.
- Kept preview tooling developer-facing and avoided runtime behavior changes.

## 0.91.8b0

- Formalized `console-preview` as hidden internal developer tooling with
  `--all`, `--normal`, and `--verbose` preview modes.
- Moved console preview scenarios into the intentional `litlaunch.cli.preview`
  module and removed temporary preview command naming.
- Kept preview tooling out of standard user help and public docs; no runtime
  behavior changed.

## 0.91.7b0

- Added a distinct `Hook:` console category for developer-defined shutdown hook
  output.
- Verified shutdown hook label/message/color metadata rendering without changing
  shutdown execution semantics.
- Added console preview examples for successful and failed developer cleanup hooks.

## 0.91.6b0

- Normalized runtime console category labels around Runtime, Backend, Health,
  Browser, Monitor, and Shutdown.
- Replaced action-phrase categories such as `Stopping backend:` with domain
  categories and clearer wording.
- Added backend/runtime categories to port release, dry-run, monitor, and launch
  failure output without changing runtime behavior.

## 0.91.5b0

- Reduced redundant console failure wording in browser launch paths.
- Split browser fallback output into a concise warning plus structured `next`
  guidance lines.
- Kept long-line wrapping conservative and avoided runtime behavior changes.

## 0.91.4b0

- Made normal-mode failure guidance concise with one summary, one `cause`, and
  one `next` line while preserving deeper diagnostic steps in verbose mode.
- Reduced redundant normal-mode browser and shutdown failure messages without
  changing runtime behavior.
- Moved backend PID detail to verbose output and kept normal progress messages
  user-facing.

## 0.91.3b0

- Reviewed RoleThread `main` launcher/runtime console wording and adapted
  generic shutdown/exit phrasing into LitLaunch without changing ownership
  behavior.
- Replaced normal backend exit-code wording with cleaner clean-exit and
  non-zero-exit messages.
- Added verified port-release console output when LitLaunch can safely confirm
  the configured backend port is available after the owned process stops.
- Corrected console guidance labels so `cause` and `next` occupy the
  fixed-width bracket field instead of following an `ok` status label.
- Tuned beta console warning/error colors toward true yellow and a brighter
  PowerShell-style red.

## 0.91.2b0

- Aligned runtime console phase and guidance lines under fixed-width status
  labels while preserving console behavior and beta color roles.
- Updated failure guidance labels to bracketed `cause`/`next` lines for cleaner
  terminal alignment.

## 0.91.1b0

- Added an internal beta `console-preview` developer command for visually
  reviewing runtime terminal output styles.
- Polished runtime console status formatting, startup header styling, beta color
  roles, and label/body color separation without changing runtime behavior.

## 0.91.0b0

- Entered the 0.9x beta stabilization band with beta package metadata and
  classifier alignment.
- Reflected the profiles/runtime, diagnostics, backend-provider, monitoring, and
  organization milestones completed before TestPyPI rehearsal.

## 0.85.0

- Moved CLI implementation modules into a dedicated `litlaunch.cli` package
  while preserving `litlaunch.cli:main` and `python -m litlaunch.cli`.

## 0.84.0

- Split launch planning and backend startup mechanics out of the public
  launcher facade while preserving launcher behavior and public APIs.

## 0.83.0

- Extracted runtime console presentation helpers from launcher/session
  orchestration into a focused runtime console module.

## 0.82.0

- Split CLI command handling into focused parser, command, configuration, inspect,
  and shared helper modules while preserving command behavior and entry points.

## 0.81.0

- Split the inspect diagnostics implementation into focused model, collector,
  renderer, and Streamlit-check modules while preserving the public
  `litlaunch.inspect` API.

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
