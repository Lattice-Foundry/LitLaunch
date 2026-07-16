# LL-HS9 Windows and DPI Host-Sizing Validation Matrix

- Date: 2026-07-15
- LitLaunch reference: 1.0.11
- Baseline: `ce1c50c`
- Scope: Experimental public initial host sizing

## Verdict

**EXPERIMENTAL MATRIX PROVEN WITH LIMITATIONS**

**Recommendation: KEEP EXPERIMENTAL**

The available Windows 11 matrix proves one authenticated, bounded, height-only
initial fit across current Edge and Chrome, direct and Windows-shortcut launch
paths, 100% and 150% scaling, and a real mixed-DPI dual-monitor topology with a
negative-origin secondary monitor. Successful cases preserved width, top-left
position, activation, and Z-order; unsafe cases refused mutation; target browser
trees exited naturally; and managed profiles, shortcuts, channels, and windows
cleaned up.

The evidence does not meet the label-removal bar because Windows 10, 125% scaling,
additional taskbar placements, and an independent host remain untested.

## Contract reviewed

The validated public contract remains unchanged:

```text
host_sizing = off | initial
```

`off` remains the default. `initial` is eligible only for a loopback-hosted Windows
webapp launch with an explicit Edge or Chrome choice and a LitLaunch-managed browser
profile. One trusted frontend source may request one initial height fit. Width,
continuous fitting, ordinary browser tabs, external profiles, network-exposed apps,
and general window management remain out of scope.

The public handoff accessor returned the expected immutable launch ID, endpoint,
protocol, source ID, token-header name, and capability token to the probe app. Its
representation remained token-redacted. The frontend submitted reports through the
documented authenticated app-owned adapter boundary.

## Environment inventory

| Item | Observed value |
| --- | --- |
| Operating system | Windows 11 Pro 10.0.26200, build 26200 |
| Python | 3.14.5 |
| Streamlit | 1.57.0 |
| Microsoft Edge | 150.0.4078.65 |
| Google Chrome | 150.0.7871.116 |
| Taskbar placement | Bottom on both work areas |

The native probes used LitLaunch's per-monitor-v2 thread context. This was
load-bearing: a DPI-virtualized shell query reported both displays as 96 DPI, while
the production geometry backend correctly measured the target window's actual 96 or
144 DPI.

| Display | Native monitor bounds | Native work area | DPI | Scale | Topology |
| --- | --- | --- | ---: | ---: | --- |
| Primary | `(0, 0)-(3440, 1440)` | `(0, 0)-(3440, 1392)` | 96 | 100% | Primary |
| Secondary | `(3440, -301)-(7280, 1859)` | `(3440, -301)-(7280, 1787)` | 144 | 150% | Right of primary, negative Y origin |

Available and exercised:

- Windows 11;
- Edge and Chrome;
- direct managed-profile and Windows-shortcut managed-profile launches;
- 100% and 150% scaling;
- dual-monitor, mixed-DPI, and negative-origin placement;
- normal, maximized, fullscreen, minimized, and snapped/tiled states;
- user move, resize, and cross-monitor movement during stabilization; and
- work-area growth clamping on both monitors.

Unavailable and not claimed:

- Windows 10;
- 125%, 175%, and 200% scaling;
- a single-monitor host;
- top, left, or right taskbar placement; and
- a second independent Windows machine or browser-version generation.

## Probe method

Each success probe used ordinary public `LauncherConfig(host_sizing="initial")`, a
real Streamlit backend, the public handoff accessor, a browser-owned viewport
measurement, a real managed browser profile, and the production transport, policy,
process/HWND authority, geometry, and mutation path.

The probe recorded native DPI, browser `devicePixelRatio`, viewport heights, outer
window geometry, monitor and work area, process-tree authority, terminal runtime
events, activation, Z-order, channel closure, window closure, process-tree exit,
profile cleanup, and shortcut cleanup. Target windows were closed through their
exact HWND with `WM_CLOSE`; target browser processes were not killed.

The established acceptance tolerance is at most one CSS pixel. Native post-mutation
geometry must also match within one native pixel while left, top, and width remain
exactly unchanged.

## Successful initial fits

All 20 canonical success lanes passed. `apply` means one native mutation;
`complete` means the requested height was already satisfied and no mutation was
needed.

| Browser | Launch | Display | Case | Before | Requested | Result | CSS error | Terminal |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| Edge | Direct | 100% primary | Grow | 811 | 931 | 931 | 0 | apply |
| Edge | Shortcut | 100% primary | Grow | 811 | 931 | 931 | 0 | apply |
| Chrome | Direct | 100% primary | Grow | 811 | 931 | 931 | 0 | apply |
| Chrome | Shortcut | 100% primary | Grow | 811 | 931 | 931 | 0 | apply |
| Edge | Direct | 100% primary | Shrink | 811 | 691 | 691 | 0 | apply |
| Edge | Shortcut | 100% primary | Shrink | 811 | 691 | 691 | 0 | apply |
| Chrome | Direct | 100% primary | Shrink | 811 | 691 | 691 | 0 | apply |
| Chrome | Shortcut | 100% primary | Shrink | 811 | 691 | 691 | 0 | apply |
| Edge | Direct | 100% primary | No-op | 811 | 811 | 811 | 0 | complete |
| Chrome | Shortcut | 100% primary | No-op | 811 | 811 | 811 | 0 | complete |
| Edge | Shortcut | 100% primary | Clamp | 341 | 2341 | 403 | 0 | apply |
| Chrome | Direct | 100% primary | Clamp | 341 | 2341 | 403 | 0 | apply |
| Edge | Direct | 150% secondary | Grow | 813 | 933 | 933 | 0 | apply |
| Edge | Shortcut | 150% secondary | Shrink | 813 | 693 | 693 | 0 | apply |
| Chrome | Direct | 150% secondary | Grow | 813 | 933 | 933 | 0 | apply |
| Chrome | Shortcut | 150% secondary | Shrink | 813 | 693 | 693 | 0 | apply |
| Edge | Direct | 150% secondary | Clamp | 343 | 2343 | 504 | 0.33 | apply |
| Chrome | Shortcut | 150% secondary | Clamp | 343 | 2343 | 504 | 0.33 | apply |
| Edge | Direct | 100% primary | Stale follow-up | 811 | 931 | 931 | 0 | apply |
| Chrome | Direct | 100% primary | Second source | 811 | 931 | 931 | 0 | apply |

The 150% clamp target was 503.67 CSS pixels after work-area conversion. The measured
504-pixel viewport is a 0.33 CSS-pixel rounding difference and remained inside both
the CSS and native tolerances.

### Geometry and lifecycle results

- Normal 100% probes began at outer bounds `(200, 120)-(1400, 970)`.
- Growth and shrink changed only outer and client height; left, top, outer width, and
  client width remained exact.
- Primary clamp probes began at `(300, 950)-(1300, 1330)` and ended exactly at the
  primary work-area bottom of 1392.
- Secondary clamp probes ended exactly at the secondary work-area bottom of 1787.
- Every 150% probe measured DPR 1.5 and target-window DPI 144; every 100% probe
  measured DPR 1.0 and DPI 96.
- Activation and Z-order were preserved in every normal success lane.
- Edge target process trees contained 15 observed processes and Chrome trees
  contained 9 in the representative runs; the selected window PID belonged to the
  exact retained launch tree in every case.
- The stale report and second-source conflict were rejected after the first accepted
  report without causing a second mutation.
- Each channel became terminal and rejected a later request, each exact target window
  closed, each target process tree reached `lost`, and all managed profiles and
  temporary shortcuts were removed.

## Fail-closed native matrix

| Browser | Launch | Condition | Outcome | Native mutation |
| --- | --- | --- | --- | ---: |
| Chrome | Direct | Fullscreen at discovery | Ineligible | 0 |
| Edge | Direct | Maximized during stabilization | Skipped | 0 |
| Chrome | Shortcut | Minimized during stabilization | Skipped | 0 |
| Edge | Shortcut | Snapped before report | Skipped | 0 |
| Chrome | Direct | User move during stabilization | Skipped | 0 |
| Edge | Direct | User resize during stabilization | Skipped | 0 |
| Chrome | Shortcut | Move from 96-DPI primary to 144-DPI secondary | Skipped | 0 |
| Edge | Direct | Window shutdown before quiet period | Runtime closed | 0 |
| Chrome | Direct | Missing frontend adapter | Timed out | 0 |
| Edge | Direct | Wrong capability token | Timed out after rejection | 0 |
| Chrome | Direct | Malformed report | Timed out after rejection | 0 |

The app remained usable until the probe deliberately closed its exact window.
User-induced geometry was left as the user set it; LitLaunch did not attempt to undo
maximize, minimize, snap, move, resize, or monitor transition. Cleanup remained
complete in every canonical failure lane.

The shutdown probe initially used an invalid test ordering that stopped the runtime
while intentionally holding the managed Edge window open, then closed the window
after cleanup had already run. That ordering demonstrated the documented
best-effort profile policy rather than production monitored-webapp shutdown. The
probe was corrected to close the exact app window during the quiet period and then
stop the runtime, matching production lifecycle order; no profile remained.

## Deterministic failure coverage

Existing focused tests supplement the native matrix for cases that should not be
forced through a live desktop session. They cover:

- default-off behavior and no transport activation;
- unsupported OS, browser mode, automatic or unsupported browser choice, external
  profile, and non-loopback host;
- wrong origin, wrong token, malformed and non-finite reports, stale sequence,
  second-source conflict, rate limiting, and channel closure;
- ambiguous HWND, title-only candidates, lost authority, PID reuse, pre-existing
  windows, and unstable authority;
- fullscreen, minimized, maximized, snapped, geometry drift, monitor transition,
  and DPR mismatch refusal;
- timeout, shutdown, mutation failure, capture failure, and post-mutation
  verification failure; and
- terminal-state permanence with no retry or second mutation.

These tests use fake collaborators where deliberately causing a native API or
authority failure would be unsafe or nondeterministic. Browser-version-specific
assumptions were not added to the automated suite.

## Existing-browser isolation

Edge probes ran while unrelated Edge activity already existed: 15 pre-existing Edge
processes and one visible unrelated Edge window. The unrelated window remained open
and unchanged after every target launch; target authority was limited to the retained
managed-profile launch tree.

An independent Chrome isolation control kept another app-mode Chrome window open in
a separate profile while a nine-process LitLaunch target tree completed a real fit.
The control HWND and geometry were identical before and after the target launch. The
target and control windows were closed separately through their exact HWNDs, and no
unrelated process was terminated.

## Findings

No LitLaunch implementation defect was reproduced, so this pass changes no runtime
or test code. One aggregate success run recorded a single transient harness failure;
the four candidate no-op and clamp lanes were rerun independently and all passed.
The failure did not reproduce and did not identify a product condition suitable for
a regression test.

Validation expands the public evidence boundary from one 96-DPI context to one real
100%/150% mixed-DPI Windows 11 host. It does not expand the supported contract.

## Remaining limitations

1. Windows 10 parity remains unproven.
2. The required 125% lane remains unproven; 175% and 200% were also unavailable.
3. Only bottom taskbars were available. Top, left, and right work-area shapes remain
   untested.
4. The available topology was dual-monitor. A single-monitor host and other monitor
   arrangements were not independently exercised.
5. Live native API failure, post-mutation verification failure, ambiguous HWND, and
   lost-authority behavior remain deterministic-test evidence rather than forced
   desktop failures.
6. Evidence comes from one Windows 11 host and current Edge/Chrome versions. Future
   browser process behavior may still fail closed.

## Experimental-label decision

The feature clears the available Windows 11, Edge, Chrome, direct, shortcut, 100%,
150%, mixed-DPI, negative-origin, grow, shrink, clamp, no-op, user-intent,
isolation, security, and cleanup lanes. It does not clear Windows 10 or 125%, both of
which are load-bearing criteria for removing the label.

**EXPERIMENTAL MATRIX PROVEN WITH LIMITATIONS**

**KEEP EXPERIMENTAL**
