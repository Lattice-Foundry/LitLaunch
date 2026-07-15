# LL-HS4 Private End-to-End Host-Sizing Integration

- Date: 2026-07-14
- LitLaunch reference: 1.0.10
- Scope: private integration proof only

## Verdict

**PRIVATE INTEGRATION PROVEN WITH LIMITATIONS**

LitLaunch now has one private coordinator that connects authenticated LL-HS1 reports
to LL-HS2 decisions, LL-HS3 one-shot mutation, and policy acknowledgement. The
pipeline is deterministic, bounded, credential-free after transport, and terminal
after success, no-op, refusal, failure, timeout, or shutdown.

The coordinator is not imported by the production launcher, package root, CLI,
profiles, or public configuration. Normal LitLaunch users have no activation path and
no behavior change.

The remaining production blocker is exact browser-process authority for Windows
shortcut launches. Direct Chromium launches now retain their returned process ID in a
private non-owning snapshot. `os.startfile` shortcut activation returns no process
handle, so LitLaunch correctly refuses to infer ownership from a title, shortcut,
AppUserModelID, or visible window alone.

## Architecture

```text
Measured CSS dimensions and DPR
            |
            v
LL-HS1 authenticated loopback transport
  - token, launch ID, exact origin
  - strict schema and sequence gate
            |
            | accepted HostSizingReport only
            v
LL-HS2 initial-fit policy
  - stabilization, bounds, authority, terminal state
            |
            | one APPLY decision at most
            v
LL-HS3 trusted Windows mutation
  - exact HWND/PID and geometry revalidation
  - one bounded height-only native call at most
            |
            | HostSizingMutationResult
            v
LL-HS2 acknowledgement
  - complete or abort, never retry
```

`_host_sizing_runtime.py` contains orchestration only. It does not parse JSON,
authenticate tokens, calculate geometry, discover browser windows, call Win32, or
define policy. Those responsibilities remain in their independently tested layers.

## Report and trust flow

LL-HS1 owns HTTP, CORS, origin policy, capability-token comparison, launch-ID
comparison, strict schema validation, source binding, sequence acceptance, request
limits, and bounded report retention. Its accepted-report callback receives only a
frozen `HostSizingReport`. Authentication, malformed schema, source conflicts, stale
sequences, and rate limits never invoke the callback.

The coordinator serializes callback delivery into LL-HS2. Concurrent HTTP handlers
can complete callbacks in a different order than store acceptance, but LL-HS2's
monotonic sequence gate ensures an older accepted callback cannot replace a newer
decision input.

The coordinator owns the channel, policy, one mutation capability, exact immutable
authority, worker deadline, and shutdown. The channel closes after terminal policy
state or explicit shutdown. Partial startup closes any channel already created.

## Trusted DPR handoff

Device-pixel ratio originates with the browser measurement surface. Protocol v1 now
requires `device_pixel_ratio` as a finite number from 0.5 through 8.0. LL-HS1 validates
and freezes it with the report. LL-HS2 preserves it unchanged in the decision and
treats a DPR change as material sizing input.

LL-HS3 consumes DPR only from the typed apply decision. DPR is no longer duplicated in
window authority. The geometry layer compares the reported DPR with target-window DPI
and refuses mutation when they disagree. No layer infers DPR after transport.

## Decision and acknowledgement lifecycle

The private runtime permits these paths:

- no meaningful change: LL-HS2 completes without calling LL-HS3
- stable bounded target: exactly one `apply` decision reaches LL-HS3
- applied or native no-change: exactly one successful acknowledgement completes LL-HS2
- refusal, native failure, or unverified result: exactly one failed acknowledgement
  aborts LL-HS2
- timeout or shutdown before apply: channel closes without mutation
- later reports after terminal state: ignored and unable to mutate

There is no retry, continuous fitting loop, rollback attempt, or second mutation. A
malformed or exception-raising mutation collaborator is contained and acknowledged as
failure.

## Authority retention review

The production browser launcher previously discarded the object returned by direct
`Popen`. It now retains a private snapshot containing the positive root PID, explicit
Edge or Chrome kind, and `direct` strategy. This snapshot is non-owning and adds no
termination behavior or public result field.

The Windows icon shortcut path writes and opens a `.lnk` through `os.startfile`.
Windows does not return the browser process from that API. Shortcut metadata proves
launch intent and shell identity, not exact process ownership. This path therefore
retains no process authority.

Direct PID retention is necessary but not sufficient for activation. A future private
production integration still must retain the launched process tree, establish one
stable exact app-mode HWND inside it, capture immutable baseline geometry, and carry
that authority into the coordinator. The unsupported title-token and PowerShell CIM
spike mechanisms are not acceptable production substitutes.

## Deterministic proof

The LL-HS4 matrix covers:

- fake accepted transport into real policy and fake one-shot mutation
- real authenticated HTTP transport into real policy and the real LL-HS3 capability
  over fake native geometry
- rejected authentication stopping before policy and mutation
- success, no-op, configured clamp, authority loss, geometry drift, and native failure
- stale sequence, multiple reports, newest-report selection, and report after complete
- one mutation and one acknowledgement at most
- timeout and shutdown without late mutation
- authenticated DPR preservation through a 144-DPI conversion
- private direct-launch PID retention and fail-closed shortcut authority
- absence from package exports and production launcher activation

The real LL-HS1 browser CORS evidence and real LL-HS3 Edge/Chrome native evidence
remain valid at their layer boundaries. LL-HS4 does not claim a real browser run of
the complete production pipeline because production shortcut authority is unresolved.

## Validation evidence

- focused LL-HS0 through LL-HS4 and browser-authority matrix: 222 passed
- full `python -m pytest`: 965 passed, including the real Streamlit smoke test
- `python -m ruff check .`: passed
- `python -m ruff format --check .`: 123 files already formatted
- `python -m mypy src/litlaunch`: passed for 79 source files
- `python scripts/check_release.py`: passed; wheel and source distribution built,
  checked, installed, and reported version 1.0.10
- `git diff --check`: passed

## Remaining limitations

1. Windows shortcut activation has no exact process handle, so the common icon-enabled
   webapp launch path cannot yet construct production mutation authority.
2. Direct launch retains a root PID but is not yet wired to process-tree tracking,
   exact HWND acquisition, or normal runtime lifecycle.
3. The private measurement adapter and backend environment injection remain
   intentionally absent.
4. Host sizing remains Windows-only, Chromium app-mode-only, height-only, and
   initial-fit-only.
5. The Win32 identity checks and mutation call cannot be atomic; LL-HS3 detects drift
   before and after and fails closed, but cannot eliminate the operating-system race.

These limitations block public or production activation. They do not invalidate the
private transport-to-policy-to-mutation architecture proven here.

**PRIVATE INTEGRATION PROVEN WITH LIMITATIONS**
