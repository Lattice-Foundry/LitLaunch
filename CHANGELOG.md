# Changelog

LitLaunch uses PEP 440 pre-release versions until the coordinated
LitLaunch / RoleThread launch. Public documentation is stable-facing while the
package classifier remains `Development Status :: 4 - Beta` until the final
`1.0.0` release.

Granular pre-release history is preserved in git. This changelog now presents
the project history at the level most useful to release users and integrators.

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
