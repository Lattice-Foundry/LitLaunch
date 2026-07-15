# LL-HS3 Trusted Windows Host-Sizing Mutation Capability

- Date: 2026-07-14
- LitLaunch reference: 1.0.10
- Design references: `litbridge_host_sizing_consumption_recon.md`,
  `host_sizing_geometry_authority_spike.md`,
  `host_sizing_transport_trust_foundation.md`, and
  `host_sizing_policy_state_machine.md`
- Scope: private one-shot Windows mutation capability only

## Verdict

**WINDOW MUTATION CAPABILITY PROVEN WITH LIMITATIONS**

LitLaunch can apply exactly one LL-HS2-approved height decision to exactly one
authorized managed-profile Edge or Chrome app window. The capability requires strong
immutable authority, revalidates window identity and geometry immediately before
mutation, performs one bounded non-moving `SetWindowPos`, verifies identity and native
geometry afterward, and returns a terminal non-retryable result suitable for LL-HS2
acknowledgement.

Real Edge and Chrome probes passed for growth, shrink, monitor work-area clamping, 96
DPI, and 144 DPI. Deliberate authority, geometry, placement, and window-state failures
were refused without the approved mutation.

The capability remains disconnected from normal launches. LL-HS4 later completed the
private device-pixel-ratio handoff, but production browser-process authority is not
complete across every launch path. This result does not authorize transport
activation or public configuration.

## Reusable LL-HS0 primitives

The following LL-HS0 primitives are safe behind the new private capability:

- immutable `NativeRect` and `WindowGeometry` snapshots
- explicit normal, minimized, maximized, fullscreen, and snapped states
- target-window DPI and browser device-pixel-ratio consistency checks
- CSS viewport delta to native outer-height conversion
- current monitor work-area clamping
- width and top-left preservation
- thread-scoped per-monitor-v2 DPI awareness
- geometry comparison before mutation
- native geometry capture and `SetWindowPos` backend seams

Geometry-change detection now also includes full monitor bounds and the Windows show
command. This closes two stale-authority cases that the spike did not originally
compare.

The following remain unsupported spike instrumentation:

- the temporary viewport measurement page
- title-token signaling
- PowerShell CIM process-tree polling
- direct temporary-profile browser launch
- the `python -m litlaunch._host_sizing_spike` CLI
- JSON evidence rendering and manual probe controls

The harness now routes its `--apply` path through LL-HS2 and the LL-HS3 capability so
native evidence exercises the production-shaped seam. None of the harness mechanisms
are imported by the capability.

## Exact mutation authority

`WindowSizingAuthority` is immutable and requires:

- a non-empty opaque authority ID matching the LL-HS2 apply decision
- one positive HWND matching the immutable geometry baseline
- explicit Edge or Chrome browser kind
- one positive top-level window PID inside a retained launched-process set
- at least three stable exact-authority observations
- an explicitly managed browser profile
- explicit Chromium app mode
- positive native window, client, monitor, and work-area geometry

The authority factory promotes only an exact LL-HS0 probe. It rejects missing or
unstable authority, default-browser authority, wrong browser process, non-Chromium
window class, missing process identity, process-set mismatch, invalid geometry, and
unsafe profile or mode claims.

Immediately before native geometry capture, `WindowsWindowAuthorityVerifier`
enumerates visible top-level windows and requires exactly one strict Chromium
candidate inside the retained launch-process set. That candidate must still match the
authorized HWND and PID. The same verification runs again after mutation.

No title match is treated as sufficient mutation authority.

## One-shot mutation sequence

One `TrustedWindowsWindowSizer` instance is permanently consumed by its first apply
call, including a refused or failed call. Concurrent callers are serialized, and only
one can reach identity verification or native APIs.

The apply sequence is:

1. Require a typed LL-HS2 `apply` decision in `apply_pending` state.
2. Require matching opaque authority ID and complete source/sequence metadata.
3. Require the desired CSS viewport height and authenticated DPR to remain inside
   their policy and protocol bounds.
4. Revalidate one exact launch-associated Edge or Chrome HWND and PID.
5. Capture current physical Windows geometry.
6. Compare HWND, outer and client geometry, DPI, monitor, work area, show command, and
   window state with the immutable authority baseline.
7. Require a normal window and matching browser DPR versus target-window DPI.
8. Convert the CSS viewport delta to a native outer-height delta.
9. Clamp the target below the fixed top edge to the current monitor work area.
10. Call `SetWindowPos` once with width preserved and flags that prevent movement,
    activation, Z-order change, and owner Z-order change.
11. Capture native geometry and revalidate exact window identity again.
12. Require unchanged left, top, width, client width, DPI, monitor, work area, and show
    state plus the bounded target height within one native pixel.

The capability does not center, move, activate, close, minimize, maximize, retitle,
or terminate windows or browser processes.

## Result and acknowledgement contract

Every routine outcome is represented by an immutable `HostSizingMutationResult`:

- `applied`: one native height mutation was performed and verified
- `no_change`: the bounded native target already matched current outer height
- `refused`: a safety or authority gate failed before mutation
- `failed`: native mutation was attempted or native verification could not complete

Results explicitly report whether mutation was attempted. No result is retryable.
Only `applied` and `no_change` acknowledge LL-HS2 successfully. Refused, failed, and
unverified mutation results acknowledge failure, making the policy terminal without a
second mutation attempt.

## Deterministic proof

The LL-HS3 test matrix covers:

- exact authority promotion and immutable authority validation
- stable-poll, process-set, browser-kind, app-mode, and managed-profile requirements
- sole-candidate HWND/PID verification before and after mutation
- valid growth and shrink
- 96-DPI and 144-DPI conversion
- hard and monitor work-area bounds
- native no-change acknowledgement without `SetWindowPos`
- malformed, stale-state, and authority-mismatched LL-HS2 decisions
- minimized, maximized, fullscreen, and snapped refusal
- DPI/DPR mismatch
- user or system geometry, monitor, work-area, show-state, and window-state changes
- pre-capture, native-call, and post-capture failures
- post-apply position, width, height, DPI, monitor, state, and identity mismatches
- one-shot behavior under sequential and concurrent calls
- direct LL-HS2 success and failure acknowledgement
- exact non-moving, non-activating `SetWindowPos` flags
- private exports and absence of transport activation or general window controls

Final results:

- `python -m pytest tests/test_host_sizing_window.py -q`: 73 passed
- focused LL-HS0 through LL-HS3 matrix: 150 passed
- `python -m pytest`: 946 passed, including the real Streamlit smoke test
- `python -m ruff check .`: passed
- `python -m ruff format --check .`: passed for 121 files
- `python -m mypy src/litlaunch`: passed for 78 source files
- `python scripts/check_release.py`: passed; wheel and source distribution built,
  checked, installed, and reported version 1.0.10

## Native Edge and Chrome evidence

The unsupported owned-browser harness exercised the new capability directly.

### Growth at 96 DPI

Edge and Chrome each produced one process-bound HWND stable for three polls. Both
grew from a 761 CSS-pixel viewport to 900 CSS pixels:

- outer height: 800 to 939 native pixels
- measured viewport error: 0 CSS pixels
- left, top, and width: unchanged
- post-apply state: normal
- post-apply identity: exact

### Shrink at 96 DPI

Edge and Chrome each shrank from a 1,333 CSS-pixel viewport to 900 CSS pixels:

- outer height: 1,372 to 939 native pixels
- left, top, and width: unchanged
- measured viewport error: 0 CSS pixels

### Mixed DPI

Edge and Chrome each ran on the available 144-DPI display with DPR 1.5:

- viewport: 763 to 900 CSS pixels
- native height delta: 206 pixels
- expected rounding error: 0.333 CSS pixels
- measured error remained within one CSS pixel
- native position and width remained unchanged

An initial second-monitor placement put the native top above the work-area top after
Chromium scaling. The capability refused before mutation. Moving the owned test window
inside the work area allowed the exact same mutation path to pass.

### Work-area clamp

Edge and Chrome were asked for a 1,600 CSS-pixel viewport. Both clamped to the current
monitor work-area bottom:

- final viewport: 1,343 CSS pixels
- final outer bottom: 1,392 native pixels
- work-area bottom: 1,392 native pixels
- left, top, and width: unchanged

### Fail-closed probes

- A controlled 50-native-pixel geometry change after authority capture was detected;
  the approved resize was not attempted.
- Edge maximized was rejected by the unsuitable-state gate without mutation.
- Chrome fullscreen created two launch-associated Chromium candidates before apply;
  exact identity verification refused the mutation.
- No owned probe window or temporary profile remained after the runs.

## Limitations and integration gate

1. LL-HS4 retains a direct Chromium launch PID privately, but Windows shortcut
   activation through `os.startfile` still supplies no exact process identity.
2. LL-HS4 carries a bounded authenticated device-pixel ratio through transport and
   policy into this capability. The native layer still refuses DPR and target-window
   DPI disagreement.
3. The title token and PowerShell process tree remain harness-only and cannot become
   production authority shortcuts.
4. Real 120-DPI and 192-DPI displays were unavailable. Pure tests cover conversion,
   but those manual matrix entries remain open.
5. Real minimized and Snap Layout interactions remain unproven. Deterministic tests
   prove refusal, and false-positive refusal is preferred.
6. Win32 identity verification and `SetWindowPos` are separate calls, so Windows does
   not provide a fully atomic identity-and-mutation transaction. Immediate geometry
   checks and post-verification reduce this race and fail closed on detected drift.
7. A native call that succeeds but cannot be verified is reported failed and is never
   retried. The capability cannot safely undo an unverified system-level mutation.
8. The capability is Windows-only, Chromium app-mode-only, height-only, and initial
   fit-only.

Normal launches must not activate host sizing until exact production browser-process
authority is available for the selected launch strategy.

**WINDOW MUTATION CAPABILITY PROVEN WITH LIMITATIONS**
