# LL-HS8 Public Host-Sizing Surface Implementation

- Date: 2026-07-15
- LitLaunch reference: 1.0.11
- Baseline: `b0cb26c`
- Scope: Experimental public initial host sizing

## Public contract

LitLaunch now exposes one launch-time policy with exactly two values:

```text
host_sizing = off | initial
```

`off` is the default. It creates no sizing channel, credentials, sizing authority
work, or behavior change. `initial` requests one authenticated, stabilized,
height-only fit and permits at most one native mutation before the policy becomes
terminal.

The same strict value is available through `LauncherConfig`, profiles, the direct
CLI, planning, inspection, and profile serialization. Booleans and aliases such as
`enabled`, `auto`, `fit`, and `continuous` are rejected. No timing, bounds, source,
transport, width, or continuous-sizing controls are public.

## Implementation

The public enum is `HostSizingPolicy`. `LauncherConfig.host_sizing` normalizes the
policy once, and profile and CLI layers preserve the same semantics. Existing
configurations omit the field and remain off.

One static eligibility evaluator checks the pre-launch requirements:

- Windows;
- webapp mode;
- explicit Edge or Chrome selection;
- no externally supplied browser profile; and
- loopback backend host.

An eligible request enters the existing private production pipeline. That pipeline
still requires a LitLaunch-managed profile, launch-ID-bound process authority, one
stable exact Chromium HWND, normal window state, an authenticated exact-origin
report, valid DPR, and an unchanged authority chain at mutation time. It retains the
proven channel-before-backend, baseline-before-browser, one-shot mutation, terminal
channel closure, and session cleanup order.

Known static incompatibility emits one concise warning and continues the base app
launch. Runtime inability to establish transport, authority, policy, or native
mutation remains fail-soft and does not stop an otherwise valid application.

## Application handoff

Applications can call:

```python
from litlaunch.host_sizing import get_host_sizing_handoff
```

The accessor returns `None` when the launch-scoped child handoff is absent or
invalid. Otherwise it returns an immutable `HostSizingHandoff` containing only the
endpoint, launch ID, protocol version, fixed source ID, token header name, and
capability token required by the trusted frontend adapter. The token is excluded
from `repr`; parsing is strict; endpoint credentials never use a URL query string.

The application must deliberately pass this short-lived capability to one trusted
frontend surface. LitLaunch does not forward it automatically, inject browser code,
or claim protection from code already executing in the application process.

## Diagnostics

Launch plans and inspect output expose only the configured policy, Experimental
label, and deterministic static eligibility. They do not expose the endpoint, token,
launch authority, PID, process tree, HWND, or report body.

Runtime events are bounded to useful lifecycle outcomes: channel ready, exact
eligibility, first accepted report, applied, completed, timed out, skipped,
ineligible, or failed safely. Event details contain only policy, coarse status,
policy state, accepted-report count, and mutation count. Rejected-request floods
remain aggregated inside the private transport and do not create event spam.

## Public documentation

The public guide documents profile, CLI, and Python enablement; the sensitive
handoff boundary; a small framework-neutral TypeScript reporter; optional LitBridge
`onContentSize` wiring; exact requirements; one-shot behavior; troubleshooting;
security posture; and non-goals. README and relevant guide/reference pages link to
or summarize the Experimental contract.

The reference adapter remains application-owned. It requires the application to
provide a complete desired host viewport height rather than treating component
content height as a native window target. LitBridge remains optional and was not
modified.

## Deterministic validation

Coverage proves:

- default-off behavior and absence of activation work;
- strict policy validation and config/profile/CLI/Python parity;
- profile serialization and old-config compatibility;
- deterministic platform, mode, browser, profile, and host eligibility;
- immutable, redacted, strictly parsed handoff behavior;
- credential-free plan, inspect, event, and support-report surfaces;
- public activation through the existing production lifecycle;
- one report, one mutation, one acknowledgement, and terminal cleanup;
- timeout, authentication, origin, authority, user-intent, mutation, and shutdown
  failure behavior through the existing lower-layer suites; and
- normal browser, webapp, shortcut, monitoring, profile cleanup, and shutdown
  regressions.

Final automated results:

- full test suite, including the real Streamlit smoke test: 1,067 passed;
- Ruff lint: passed;
- Ruff format check: 134 files already formatted;
- mypy: passed for 85 source files;
- release hygiene: passed;
- wheel and sdist build: `1.0.11`;
- Twine checks: passed;
- isolated-wheel import, version, public enum, accessor, and CLI smoke: passed; and
- diff whitespace and machine-path/probe-residue scans: passed.

## Native Windows evidence

Environment:

- Windows 11 build 26200;
- Microsoft Edge 150.0.4078.65;
- Google Chrome 150.0.7871.116;
- Streamlit 1.57.0;
- Python 3.14.5; and
- 96-DPI primary display.

Each probe used ordinary public `LauncherConfig(host_sizing="initial")`, the public
handoff accessor, an app-owned browser reporter, the real Streamlit backend, a real
managed browser profile, and the production transport, policy, process/HWND
authority, geometry, and mutation collaborators.

| Browser | Launch | Reports | Mutations | Acknowledgements | Result |
| --- | --- | ---: | ---: | ---: | --- |
| Edge | direct | 1 | 1 | 1 | applied |
| Edge | shortcut | 1 | 1 | 1 | applied |
| Chrome | direct | 1 | 1 | 1 | applied |
| Chrome | shortcut | 1 | 1 | 1 | applied |

An independent delayed-report geometry probe requested a 120-CSS-pixel height
reduction. All four paths changed client height from 1364 to 1244 pixels while
preserving left, top, outer width, and client width exactly. A separate work-area
probe confirmed that an upward request near the monitor ceiling was clamped instead
of exceeding the usable work area.

Each sizing channel closed after completion. Probe windows received `WM_CLOSE`,
exited naturally, and left no window behind. Existing browser sessions were not
touched. An explicit `initial` request with automatic browser selection emitted one
`unsupported_browser` outcome, created no sizing runtime, and still completed the
ordinary app launch.

## Research disposition

LL-HS0 through LL-HS8 records remain tracked under `docs/research` as durable,
public-safe engineering evidence, consistent with the repository documentation
standard. Private and scratch material remains in ignored lanes. The release build
now explicitly excludes `docs/research`, and release tests reject any research
member in the sdist.

## Limitations

The feature remains Experimental. Native proof covers one current Windows 11 host,
one 96-DPI display context, and current Edge and Chrome versions. Windows 10, 125%
and 150% scaling, mixed-DPI monitors, broader multi-monitor layouts, and independent
product integrations remain unproven here.

Only normal managed Edge and Chrome webapp windows on loopback are eligible. Browser
tabs, default-browser selection, other Chromium builds, unmanaged profiles, hosted
or LAN apps, non-Windows hosts, width fitting, and continuous resizing remain out of
scope. Exact process/window APIs may fail closed on hardened systems or after future
browser behavior changes.

## Release recommendation

Version 1.0.11 is appropriate for this backward-compatible, default-off addition.
The artifacts are ready for owner review. This implementation pass does not publish,
tag, or push the release.

**PUBLIC HOST-SIZING SURFACE READY WITH LIMITATIONS**
