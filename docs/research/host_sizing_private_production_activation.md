# LL-HS6 Private Production-Path Host-Sizing Activation

- Date: 2026-07-15
- LitLaunch reference: 1.0.10
- Scope: private, default-off Windows production-lifecycle activation only

## Verdict

**PRIVATE PRODUCTION ACTIVATION PROVEN**

LitLaunch can privately activate the complete host-sizing pipeline inside its normal
production launch lifecycle without changing normal user behavior. A real app-owned
browser adapter received per-launch metadata from the backend environment, sent one
authenticated report, and reached the existing transport, policy, exact process/HWND
authority, one-shot native mutation, acknowledgement, and terminal cleanup path.

The capability remains internal and disabled by default. It has no CLI flag, profile
field, public configuration, package export, inspect field, runtime event contract,
README entry, or release claim. Normal launches do not create the channel, collect
window authority, instantiate the coordinator, or mutate a window.

## Activation gate

`_PrivateHostSizingActivation` is a constructor-only private collaborator injected
into `StreamlitLauncher`. Its `enabled` value defaults to false, and no public config,
environment, profile, or CLI input constructs an enabled instance. Each enabled
launch receives a new `_PrivateHostSizingProductionRuntime`; browser mode and
non-Windows hosts become terminally ineligible before transport startup.

The gate is intentionally removable or promotable without changing `LauncherConfig`
or any public callable. `StreamlitLauncher.with_port()` preserves an explicitly
injected private activation for internal harnesses, while ordinary launcher creation
continues to hold `None`.

## Production lifecycle seams

The integration uses the existing launch path rather than a parallel lifecycle:

1. `StreamlitLauncher.start()` creates the private per-launch controller.
2. Backend environment construction starts the LL-HS1 loopback channel after the
   concrete application URL is known and before the backend process starts.
3. The controller captures pre-browser HWNDs immediately before browser launch.
4. The same random launch ID is bound into the next `BrowserLauncher` process
   authority, for direct or Windows-shortcut activation.
5. After browser success, LL-HS5 establishes one stable exact HWND and immutable
   baseline geometry from the retained process tree.
6. Only then does the controller attach the already-running channel to the LL-HS4
   coordinator and begin stabilization.
7. `RuntimeSession` owns the controller and closes it at the start of shutdown,
   before graceful backend cleanup or termination fallback.
8. Existing browser shortcut and managed-profile callbacks run after backend
   teardown, as before.

Backend-start or browser-launch failure closes private sizing before returning the
ordinary failed launch result. A transport, baseline, authority, or coordinator
failure disables sizing and leaves a valid base launch running.

## Environment handoff

Only the launched backend receives these private values while activation is enabled:

- loopback endpoint URL;
- capability token;
- launch ID;
- exact application origin;
- protocol version;
- expected source ID; and
- an enabled marker.

The channel binds literal `127.0.0.1`, is ready before process creation, and registers
the token with console redaction. The token is not present in snapshots, events,
reports, plans, command previews, or documentation evidence. All reserved host-sizing
environment names are removed from ambient process state and user `extra_env` unless
the private provider supplies them for the active launch, preventing accidental or
spoofed activation through public configuration.

The source ID is now enforced by LL-HS1 before report-store binding. Credentials stop
working when the channel reaches terminal state or session shutdown closes it.

## Measurement and decision flow

The production proof used a temporary Streamlit app with a small app-owned JavaScript
adapter. The adapter read only its backend environment handoff, measured the host
viewport and content in CSS pixels, retained browser DPR, and posted protocol v1 to
the authenticated endpoint. LitBridge and LitPack were not modified.

Reports arriving before exact HWND authority are bounded to the latest accepted typed
report inside the controller. After authority is established, that report enters the
unchanged LL-HS2 policy. Width remains observational. LL-HS3 receives the validated
desired height and DPR unchanged and performs at most one height-only mutation.

The coordinator now also contains acknowledgement exceptions. If policy
acknowledgement raises after a mutation result, the policy aborts terminally instead
of remaining apply-pending. There is still no retry or second native mutation.

## Authority flow

The transport launch ID is bound to `BrowserLaunchAuthority` before the real browser
launch. Both direct `Popen` and Windows `ShellExecuteExW` shortcut paths pass that ID
to the existing authority factory. The binding is one-shot and cleared after the
browser launch attempt, so it cannot leak into a later launch.

The LL-HS5 gate then requires Windows, webapp mode, Edge or Chrome, a LitLaunch-owned
managed profile, a creation-time-valid process tree, one new Chromium HWND stable for
three polls, and normal baseline geometry. Mutation revalidates the process tree and
exact HWND/PID around `SetWindowPos`. No title, URL, timing, nearest-process, default-
browser, or unmanaged-profile fallback grants authority.

## Coordinator and shutdown ownership

The controller owns the channel, one pending accepted report, coordinator, terminal
watcher, immutable baseline handles, and credential-free terminal snapshot. Terminal
policy state closes the channel and drops channel/coordinator references. Explicit
session shutdown clears the browser authority and closes coordinator/transport before
the backend cleanup request begins.

Shutdown is idempotent and bounded. A report after shutdown cannot reach policy, and
no mutation can occur after shutdown begins. Existing window monitoring, backend
ownership, shutdown hooks, port release checks, shortcut cleanup, and managed-profile
cleanup retain their previous behavior. LitLaunch still never terminates a browser
process.

## Native production evidence

Host:

- Windows 10.0.26200.0;
- Microsoft Edge 150.0.4078.65;
- Google Chrome 150.0.7871.116;
- Streamlit 1.57.0; and
- 96-DPI primary display.

Each probe used `StreamlitLauncher.start()` with the internal gate, the real backend
environment, a real managed browser profile, real browser launch, real LL-HS1 HTTP
endpoint, production LL-HS2/LL-HS3/LL-HS4/LL-HS5 collaborators, and an app-owned
browser measurement. Shortcut probes used the real temporary `.lnk` path. Twelve
unrelated Edge processes were present during the Edge runs and remained untouched.

| Browser | Launch | Authority | Viewport | Apply / ack | Cleanup |
| --- | --- | --- | --- | --- | --- |
| Edge | direct | exact process + stable HWND | 761 to 881 CSS px, 0 error | 1 / 1 | passed |
| Edge | shortcut | exact process + stable HWND | 761 to 881 CSS px, 0 error | 1 / 1 | passed |
| Chrome | direct | exact process + stable HWND | 761 to 881 CSS px, 0 error | 1 / 1 | passed |
| Chrome | shortcut | exact process + stable HWND | 761 to 881 CSS px, 0 error | 1 / 1 | passed |

All four preserved native left, top, and width. Each channel closed after policy
completion. Probe cleanup sent `WM_CLOSE` only to the exact authorized HWND; every
browser tree exited naturally, no browser process was killed, every probe window
closed, and all managed profiles and temporary shortcuts were removed.

## Failure behavior

Deterministic coverage proves:

- default-off, browser-mode, non-Windows, unsupported-browser, and unmanaged-profile
  paths do not activate;
- channel startup, backend startup, browser launch, baseline capture, authority
  ambiguity/loss, unsafe window state, and coordinator startup fail closed;
- wrong token, wrong origin, malformed schema, wrong source, stale sequence, and
  source conflict stop before mutation;
- no adapter reaches bounded timeout and closes the endpoint without mutation;
- early reports wait for exact authority rather than bypassing it;
- shutdown before quiet-period completion prevents late mutation;
- geometry drift, maximized state, mutation failure, and acknowledgement failure
  abort without retry; and
- base launch behavior remains usable whenever its own backend and browser launch are
  valid.

The existing LL-HS0 through LL-HS5 suites continue to prove each lower-layer failure
case. HS6 adds production controller, backend environment, browser binding, session
ordering, rollback, credential invalidation, and four native end-to-end probes.

## Security posture

- Activation is explicit, private, and default-off.
- Reserved metadata cannot be injected through ambient environment or `extra_env`.
- Transport remains loopback-only, exact-origin, token-authenticated, source-bound,
  schema-bounded, sequence-aware, rate-limited, and terminally closed.
- Credentials are confined to the child environment and live channel configuration.
- Internal snapshots contain counts, states, and bounded reasons, never credentials,
  raw process trees, or public HWND details.
- Browser process identity and exact HWND authority remain independent of untrusted
  report values.
- Native mutation remains one-shot, height-only, verified, and non-retryable.
- LitLaunch does not close or kill browser processes during normal operation; only
  the private validation harness closed its exact test HWND.

## Public-surface absence

The following remain unchanged and contain no host-sizing surface or claim:

- CLI help and command parser;
- `LauncherConfig` and profile schema;
- package root exports;
- launch plans and `inspect` output;
- runtime events and support reports;
- README and public documentation;
- package metadata and release notes; and
- version 1.0.10.

## Limitations

1. The capability is proven only for Windows managed-profile Edge and Chrome webapp
   launches. Other operating systems, browser mode, default-browser launch, tabs,
   other Chromium builds, and unmanaged profiles remain ineligible.
2. Exact authority and native geometry still depend on bounded Windows process,
   window, DPI, and work-area APIs. Access denial or future Chromium behavior changes
   produce a safe false-negative.
3. `ShellExecuteExW` may successfully open a shortcut without returning process
   authority. The app still launches, but host sizing remains disabled.
4. Process/HWND verification and `SetWindowPos` cannot form one atomic OS transaction;
   immediate pre/post checks detect drift but cannot eliminate the underlying race.
5. This pass proves a small app-owned adapter, not a released LitBridge handoff. The
   public contract, configuration, defaults, bounds, diagnostics, and documentation
   still require design review.

## Next gate

The project is ready for **LL-HS7 — Public Host-Sizing Surface Design**. That pass
should design the smallest default-off user contract and must not broaden the proven
Windows managed-Chromium initial-fit boundary.

**PRIVATE PRODUCTION ACTIVATION PROVEN**
