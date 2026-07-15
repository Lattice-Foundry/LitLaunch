# LL-HS2 Internal Host-Sizing Policy State Machine

- Date: 2026-07-14
- LitLaunch reference: 1.0.10
- Design references: `litbridge_host_sizing_consumption_recon.md`,
  `host_sizing_geometry_authority_spike.md`, and
  `host_sizing_transport_trust_foundation.md`
- Scope: private policy and fake collaborators only

## Verdict

**POLICY STATE MACHINE PROVEN**

LitLaunch can consume validated LL-HS1 report models and produce deterministic,
bounded initial-fit decisions without parsing transport input or touching a real
window. The policy independently enforces source and launch authority, opaque window
authority continuity, monotonic sequence handling, quiet-period stabilization,
height bounds, a minimum target delta, an overall deadline, one-apply behavior,
explicit apply acknowledgement, shutdown cancellation, and terminal state.

The engine remains private and inactive in normal launches. It has no HTTP, JSON,
authentication, browser discovery, native geometry, Win32, or mutation behavior.

## Architecture boundary

LL-HS2 establishes the third independently testable stage:

```text
Measurement
    -> Authentication and validation
    -> Policy decision
    -> Future mutation
```

The policy imports only the strongly typed `HostSizingReport` model from LL-HS1. It
does not start or close the channel, inspect headers, parse JSON, compare capability
tokens, or know endpoint configuration.

Window authority enters as an opaque status and identity. The policy does not know
whether that identity represents an HWND, browser process, or future authority
object. This lets LL-HS2 prove continuity and fail-closed behavior without weakening
LL-HS0's unresolved production authority gate.

## Initial-fit state machine

The private state machine uses these lifecycle states:

- `waiting`: no accepted report or exact authority yet
- `stabilizing`: material sizing input is inside the quiet period
- `apply_pending`: exactly one apply decision has been emitted and awaits a synchronous
  collaborator acknowledgement
- `complete`: the apply succeeded or no meaningful viewport change was required
- `aborted`: authority, collaborator, or an external safety gate failed
- `timed_out`: the overall decision deadline expired
- `shut_down`: runtime shutdown cancelled sizing

It emits immutable `wait`, `apply`, `ignore`, `abort`, and `complete` decisions. An
apply decision contains only the bounded desired CSS viewport height, normalized
requested height, current reported viewport height, opaque authority ID, source,
sequence, authenticated device-pixel ratio, and clamp reasons. It contains no native
handle or credentials.

## Stabilization

The internal quiet period is 250 ms and the overall deadline is 5 seconds. They remain
implementation constants rather than public controls.

The first report starts stabilization. A change to content height, content width,
desired host viewport height, or device-pixel ratio restarts the quiet period. A newer
report whose only relevant change is host viewport feedback is retained but does not
restart the timer. This matches LitBridge's duplicate suppression and prevents the
host viewport from creating a feedback loop.

The policy does not require duplicate reports. One report can stabilize and produce a
decision when exact authority is available.

Desired viewport width is intentionally ignored by the first height-only policy.

## Authority and sequencing

The first validated report binds the launch ID and source ID. A different launch or
source causes a terminal abort. Duplicate or older sequences are ignored without
replacing the latest accepted observation.

Exact window authority requires one non-empty opaque identity. Repeated observations
must retain that identity. A different exact identity, a return to pending after exact
authority, ambiguity, unsupported authority, or authority loss causes a terminal
abort.

All state transitions are protected by one reentrant lock. Concurrent reports leave
the highest accepted sequence as the current authority observation.

## Bounds and no-op completion

Desired viewport height is normalized to an integer with deterministic half-up
rounding. The internal hard CSS viewport range is 320 through 4,096 pixels. Optional
private configured bounds can narrow that range but cannot weaken it.

The decision records whether the hard minimum, hard maximum, configured minimum, or
configured maximum changed the requested target.

After clamping, a target within one CSS pixel of the current reported host viewport
completes without emitting an apply decision. This minimum-delta rule compares the
host target with the current host viewport only; it does not duplicate LitBridge's
content-measurement filtering.

## One-apply and terminal behavior

At the end of stabilization, exact authority and a valid latest report can produce at
most one `apply` decision. The state immediately becomes `apply_pending`, so later
reports cannot create another decision or a viewport feedback loop.

A mutation collaborator must acknowledge the decision synchronously:

- success transitions to `complete`
- failure transitions to `aborted`
- no acknowledgement before the overall deadline transitions to `timed_out`

Runtime shutdown and explicit external safety gates can cancel waiting,
stabilization, or apply-pending states. External gates carry reasons such as user
geometry change or unsupported window state, but LL-HS2 does not discover or inspect
those conditions itself.

No observation can revive a terminal policy.

## Fake mutation proof

The test collaborator records immutable apply decisions and returns a controlled
success or failure result. Tests prove:

- success receives exactly one decision and completes the policy
- failure receives exactly one decision and aborts the policy
- a pending decision cannot emit a second apply
- shutdown cancels a pending decision before acknowledgement
- a late acknowledgement fails closed at the overall deadline
- reports after apply or terminal completion cannot trigger mutation

The fake has no native or browser implementation.

## Validation coverage

Focused policy coverage includes:

- default and invalid internal policy values
- report-first and authority-first ordering
- stabilization without duplicate reports
- material content and desired-height changes
- viewport-only and width-only feedback
- stale sequences and concurrent sequence delivery
- launch, source, and opaque authority conflicts
- unsupported, ambiguous, pending, and lost authority
- hard bounds, narrower private bounds, clamp reasons, and integer normalization
- minimum viewport delta and no-op completion
- no-report, no-authority, stabilization, and apply-pending timeouts
- explicit abort and shutdown cancellation
- successful and failed fake mutation acknowledgements
- immutable decisions and snapshots
- direct consumption of an LL-HS1-retained typed report
- absence from public exports
- absence of transport activation, JSON parsing, browser discovery, geometry, and
  native mutation dependencies

Final results:

- `python -m pytest tests/test_host_sizing_policy.py -q`: 56 passed
- `python -m pytest`: 871 passed, including the real Streamlit smoke test
- `python -m ruff check .`: passed
- `python -m ruff format --check .`: passed for 119 files
- `python -m mypy src/litlaunch`: passed for 77 source files
- `python scripts/check_release.py`: passed; wheel and source distribution built,
  checked, installed, and reported version 1.0.10

## Limitations and next gate

- Normal LitLaunch launches do not construct the policy or activate LL-HS1 transport.
- No public profile, Python, CLI, inspect, event, or documentation contract exists.
- Opaque exact authority is supplied by tests; production launch authority remains
  unresolved for every launch path.
- External user-intent and window-state aborts are modeled but not observed.
- Decisions use CSS viewport heights only. Native conversion and monitor work-area
  clamping remain outside the policy.
- The fake acknowledgement seam is synchronous by design. A future native mutation
  coordinator must validate authority and geometry immediately before applying.

LL-HS3 may implement a separate Windows sizing capability and feed its results back
through this acknowledgement boundary. It must preserve exact authority, revalidate
window state and user intent immediately before mutation, and leave this policy free
of Win32 and geometry conversion.

**POLICY STATE MACHINE PROVEN**
