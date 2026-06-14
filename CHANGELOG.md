# Changelog

LitLaunch uses PEP 440 public versions. The `1.0.0` release is the first stable
LitLaunch release and aligns with the coordinated LitLaunch / RoleThread
launch.

Granular pre-release history is preserved in git. This changelog now presents
the project history at the level most useful to release users and integrators.

## Current Release Highlights

- Cleaner app-window launches: LitLaunch now hides Streamlit's default toolbar
  chrome by default, with `--show-streamlit-chrome` when you want it back.
- Better webapp isolation: Chromium app-mode launches use temporary browser
  profiles by default, keeping local app sessions from stepping on each other.
- Safer multi-app launching: when a requested port is already busy, LitLaunch
  can automatically choose the next available port instead of opening the wrong
  local app.
- Cleaner console output: Streamlit startup banners, usage-stat notices, and
  backend server chatter stay hidden by default while LitLaunch reports the
  selected local URL.
- More reliable close-to-shutdown behavior: app-window and browser-window
  monitoring now handles small title differences more gracefully.
- Product-style app icons: profiles, shortcuts, diagnostics, and Windows
  webapp launches can use `app_icon` for a more polished local app identity.
- Cleaner generated artifacts: project-local reports and shortcuts stay under
  `.litlaunch/`, while temporary runtime and browser state stays out of source
  trees by default.
- Stronger diagnostics and support surfaces: inspect/report workflows remain
  local, shareable after review, and focused on practical runtime posture.
- Tighter release quality: stricter type checking and release hygiene checks
  guard the package before publication.
- Cleaner public repository hygiene: internal working notes are excluded from
  public package artifacts and the public source tree.

## 1.0.10 - Stable

- Hardened port ownership checks so LitLaunch no longer treats an already
  occupied Streamlit port as a successful launch target for a new backend.
- Fixed Windows port probing by avoiding reuse-address checks and using
  exclusive bind probing where the platform supports it.
- Added configurable `port_range = [start, end]` and `--port-range START:END`
  support for safe multi-app local launch ranges.
- Added selected-port diagnostics and concise auto-port console warnings when
  LitLaunch moves away from the requested/default port.
- Kept CLI profile launches adaptive by default; `--no-auto-port` is now the
  explicit fixed-port hard-fail mode for command-line launches.

## 1.0.9 - Stable

- Moved LitLaunch-owned ephemeral runtime and browser-profile state out of
  project source trees by default and into a system temp runtime root.
- Added explicit `runtime_state_root` / `--runtime-state-root` support for apps
  that want to choose an intentional runtime-state location.
- Added inspect/report visibility for runtime state root, browser profile root,
  profile policy, and cleanup policy.
- Hardened browser-profile cleanup with LitLaunch ownership markers so cleanup
  only removes directories LitLaunch created.
- Hid raw backend console output by default so Streamlit banners, usage-stat
  notices, and app-side server chatter do not leak into the LitLaunch console.
- Added `--show-streamlit-output` and `show_streamlit_output = true` for launches
  that intentionally want raw Streamlit/backend output visible.

## 1.0.8 - Stable

- Added `app_icon` configuration for launch profiles, CLI/Python config,
  diagnostics, and native shortcut metadata.
- Added a Windows `.ico` webapp launch strategy that opens Edge/Chrome through
  a LitLaunch-generated temporary shortcut with icon metadata before the
  browser app window starts.
- Added a best-effort live Windows app-window `.ico` override for monitored
  webapp launches while documenting browser/platform fallback limits.

## 1.0.7 - Stable

- Tightened the mypy gate to `disallow_untyped_defs` for the package source and
  annotated the remaining untyped helpers.
- Consolidated duplicated launch-URL host/port parsing into a single shared
  helper used by the launcher and runtime session.

## 1.0.6 - Stable

- Treated missing app-side cleanup endpoints as the expected default for plain
  Streamlit apps, rendering a warning instead of a graceful-shutdown error
  before stopping the owned backend process.
- Clarified that `LauncherRuntime` cleanup hooks are optional power-user
  behavior for apps with real cleanup work, not required for the default
  window-close experience.

## 1.0.5 - Stable

- Hardened app-window and managed browser-window monitoring with shared,
  conservative near-title matching for cases where framework page titles drift
  slightly from LitLaunch profile titles.
- Improved monitor timeout diagnostics so LitLaunch can report the expected
  title and observed candidate browser window title when matching fails.
- Clarified monitored window title guidance for Streamlit apps and profiles.
- Fixed cross-platform mypy checks for Windows-only registry and Win32 API
  access on Linux and macOS CI runners.

## 1.0.4 - Stable

- Reorganized internal developer documentation into lane-based
  architecture, audits, research, roadmap, validation, and assets directories,
  matching the current workspace internal documentation model.
- Retired the root `notes/` working area in favor of tracked internal docs
  lanes and added ignore guardrails for future local scratch material.

## 1.0.3 - Stable

- Added mypy as a first-class validation gate for LitLaunch's typed package
  source, including CI and release hygiene checks.
- Tightened type annotations around launch configuration normalization,
  backend command construction, browser profile cleanup, diagnostics rendering,
  profile TOML handling, Windows window monitoring, and CLI helper boundaries.

## 1.0.2 - Stable

- Isolated Chromium app-mode/webapp launches with LitLaunch-managed temporary
  browser profiles by default, reducing cross-app profile, cache, extension,
  and component-state interference when multiple local Streamlit apps are open.
- Preserved explicit user browser profile arguments: launches that provide
  `--browser-arg=--user-data-dir=...` keep using the requested browser profile.

## 1.0.1 - Stable

- Opened the post-launch patch line for public repository polish and follow-up
  fixes after the `1.0.0` PyPI release.
- Hid Streamlit's default app toolbar/menu chrome by default through
  Streamlit's supported `client.toolbarMode = "minimal"` setting, with
  `--show-streamlit-chrome` and `show_streamlit_chrome = true` restoring the
  default Streamlit chrome when requested.

## 1.0.0 - Stable

- Promoted LitLaunch from the release-candidate line to the first stable
  release, with the PyPI classifier set to
  `Development Status :: 5 - Production/Stable`.
- Preserved the narrow runtime-governance scope: LitLaunch owns launch
  orchestration, backend lifecycle, browser/app-window strategy, diagnostics,
  profiles, shortcuts, runtime events, shutdown, and support artifacts without
  replacing or securing Streamlit applications.

## 1.0.0rc6 - Release Candidate

- Refined generated diagnostics pages so runtime event sessions render as
  console-style lifecycle replays near the bottom of the page, with raw JSONL
  still available for support/debug review.

## 1.0.0rc5 - Release Candidate

- Moved profile loading, writing, detection, and wizard internals into the
  dedicated `litlaunch.profiles` package while preserving top-level profile
  imports, CLI behavior, and profile file compatibility.

## 1.0.0rc4 - Release Candidate

- Improved generated diagnostics pages with human-readable runtime session
  summaries from runtime event logs while preserving raw JSONL event access and
  event-mix chart support.

## 1.0.0rc3 - Release Candidate

- Updated generated diagnostics pages to parse native runtime event JSONL logs
  for event-mix charts while preserving legacy/plain event-line support and
  safe malformed-line handling.

## 1.0.0rc2 - Release Candidate

- Added optional runtime event log support for CLI/profile/Python launches via
  `runtime_event_log`, `--event-log`, and the local JSONL
  `create_runtime_event_file_sink()` helper.
- Composed runtime event log sinks with app-provided `event_sink` callbacks so
  packaged apps can keep product logs without losing custom integration hooks.
- Improved generated diagnostics pages with an env-var-first event log resolver
  and fallback path support for app-data or project-local runtime logs.
- Updated generated diagnostics page charts for Streamlit's `width="stretch"`
  API to avoid `use_container_width` deprecation warnings.

## 1.0.0rc1 - Release Candidate

Summary:

- Feature-complete release candidate for the coordinated LitLaunch / RoleThread
  launch.
- Stable public API and documentation posture pending final RoleThread
  validation.
- Package metadata remains Beta for the release-candidate line; the
  Production/Stable classifier is reserved for final `1.0.0`.

Highlights:

- CLI and Python API launch paths for owned Streamlit runtimes, including
  `litlaunch`, `python -m litlaunch`, `litlaunch run`, profiles, and direct
  `StreamlitLauncher` usage.
- Managed Chromium browser-window lifecycle for browser mode, using temporary
  profile isolation, controlled Edge/Chrome launch shapes, exact-window
  monitoring, graceful fallback, and no browser-process killing.
- Webapp/app-window lifecycle monitoring for app-style launches, including
  close-to-shutdown behavior where platform support is available.
- Browser support boundaries for Microsoft Edge, Chrome/Chromium, default
  browser fallback, app-mode/webapp behavior, and managed browser profiles.
- Graceful shutdown orchestration with app cleanup requests, loopback-scoped
  shutdown endpoint handling, port release checks, and Ctrl+C reliability.
- Shutdown hook support, `ShutdownHookStatus`, bounded hook failure reporting,
  hook console visibility controls, and app-owned cleanup messaging through the
  LitLaunch console grammar.
- Runtime event sink API for structured lifecycle events that packaged apps can
  write to product logs or support trails without scraping console output.
- Runtime governance layer composing trust mode, runtime exposure,
  acknowledgement state, transport/TLS posture, launch allow/block posture, and
  recommendations.
- Runtime exposure and transport security diagnostics, including trust modes,
  network-visible host guidance, Streamlit-native TLS detection, plaintext HTTP
  warnings, and honest security-boundary language.
- Diagnostics and reporting outputs for inspect/report workflows, HTML reports,
  JSON diagnostics, support bundles, privacy warnings, and pattern-based
  redaction limits.
- Generated Streamlit-native diagnostics/support page API, including
  app-owned generated code, posture cards, operational charts, event trail,
  support artifact controls, and `auto`/`dark`/`light` theme modes.
- Project-local generated artifact layout under `.litlaunch/`, including
  `.litlaunch/reports/`, `.litlaunch/shortcuts/`, and
  `.litlaunch/tmp/browser-profiles/`.
- Profile system and profile wizard for repeatable launch behavior, trust
  modes, Streamlit flag passthrough, browser/window options, and guided local
  configuration.
- Native shortcut generation with Windows `.lnk`, Linux `.desktop`, macOS
  `.app` bundle limited-validation support, and script fallback via
  `--kind script`.
- Packaged/distributed application positioning and support for workflows built
  with tools such as PyInstaller, Inno Setup, and local desktop-style runtime
  distributions.
- Console UX polish for normal, verbose, quiet, and no-color output, including
  bounded error/cause/next-step messaging and consistent status grammar.
- Security/privacy posture hardening around support bundles, credential hygiene,
  diagnostics redaction, internal docs boundaries, and release artifact policy.
- Release hygiene tooling for classifier/version consistency, credential
  prefix scanning, forbidden archive entries, package artifact inspection,
  twine checks, and installed-wheel smoke validation.

## Beta Development Era

The 0.91.x line hardened LitLaunch from a capable Streamlit launcher into a
runtime-governance and operational-launch layer for real applications.

Major beta-era work included:

- Runtime hardening for backend startup, health checks, browser launch,
  graceful shutdown, port release, and repeated launch/close workflows.
- Browser lifecycle breakthroughs, including duplicate-tab prevention,
  Streamlit headless ownership, managed Chromium profile isolation,
  Edge/Chrome top-level window detection, first-run prompt suppression, and
  monitored browser-window close-to-shutdown.
- Webapp/app-window monitoring improvements that made app-mode close behavior
  explicit, testable, and reliable without weakening Ctrl+C shutdown.
- Runtime governance passes that introduced trust modes, exposure
  classification, acknowledgement enforcement, TLS/transport posture, and
  concise diagnostics summaries.
- Diagnostics/reporting expansion across inspect, report, HTML, JSON, support
  bundle, browser/platform, runtime exposure, transport security, and
  governance outputs.
- Generated diagnostics/support page work, moving from a generator API to a
  polished Streamlit-native support surface with artifact controls, event
  trail, operational visuals, and theme modes.
- Runtime event sink support for app-owned lifecycle trails and packaged-app
  support logs without telemetry or built-in persistence.
- Profile and shortcut polish, including the profile wizard, profile
  documentation, project-local `.litlaunch/` artifacts, and native shortcut
  outputs.
- Shutdown hook maturity, including `ShutdownHookStatus`, hook visibility
  controls, normal/verbose console behavior, and bounded hook error reporting.
- Public docs, CLI help, README/PyPI positioning, packaged-app messaging, and
  cross-platform workflow alignment.
- Release-readiness hardening, including metadata/classifier checks,
  credential scanning, sdist/wheel hygiene, internal docs visibility, and
  package smoke validation.

## Alpha Development Era

The early alpha line established LitLaunch's core runtime shape and project
philosophy.

Major alpha-era work included:

- Initial `StreamlitLauncher` abstraction for launching Streamlit apps from
  Python while owning the backend process.
- CLI foundations for launch, inspect, report, browser/platform discovery,
  examples, and workflow help.
- Browser detection and launch strategies for default browser, Edge,
  Chrome/Chromium, and app-mode/webapp behavior.
- Basic profile support for repeatable launch configuration and early
  Streamlit flag passthrough.
- Graceful shutdown groundwork, including cleanup callbacks, backend stop
  orchestration, and port release validation.
- Early diagnostics/reporting primitives for platform, Streamlit availability,
  browser support, command preview, and app path validation.
- Packaged-application groundwork for local-first apps, working-directory
  handling, app-mode launches, and installer/runtime integration scenarios.
- Console rendering foundations with status labels, normal/verbose output
  shaping, and developer-facing troubleshooting guidance.
