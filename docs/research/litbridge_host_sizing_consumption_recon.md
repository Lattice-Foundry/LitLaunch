# LitBridge Host-Sizing Consumption Recon

- Date: 2026-07-14
- LitLaunch reference: 1.0.10
- LitBridge reference: `0d5e6ec Expose surface content size to hosts`
- LitBridge versions: Python 1.0.0rc2, frontend 1.0.0-rc.2

## Executive verdict

**GO WITH PREREQUISITES**

LitLaunch is the right layer to own an optional host-window sizing policy. LitBridge
should continue to measure and report its rendered surface, while the application
chooses whether to connect that report to LitLaunch. Neither package needs a direct
dependency on the other.

The capability should not move directly into implementation yet. Three questions
must be proven first:

1. LitLaunch must identify exactly one launch-associated app-mode window before it
   performs a privileged mutation. The current monitor can observe a likely window,
   but app-mode matching can choose among multiple candidates.
2. A Windows geometry spike must prove reliable conversion from a desired browser
   viewport height in CSS pixels to a native outer-window height across Edge, Chrome,
   display scaling, and mixed-DPI monitors.
3. The application integration must provide a complete desired host viewport height,
   or enough generic host geometry to derive one. LitBridge's current surface report
   measures component content, not the full Streamlit page or browser viewport.

If those prerequisites cannot be met without Streamlit DOM selectors, browser source
changes, remote debugging, or ambiguous window selection, the feature should be
deferred rather than approximated.

## Scope and ownership

The intended boundary is sound:

| Layer | Owns | Does not own |
| --- | --- | --- |
| LitBridge | Measuring a rendered component surface and reporting changes | Browser-window policy, native handles, host transport |
| Application | Product layout, opt-in, sizing authority, host geometry adapter, preferred bounds | Native window mutation |
| LitLaunch | Launch lifecycle, app-mode discovery, trust policy, bounds, native host mutation, diagnostics | Product layout, Streamlit internals, LitBridge measurement |

The application must opt in at both ends: LitLaunch enables a host-sizing policy, and
the application explicitly designates one frontend surface as the sizing authority.
The feature remains absent when either side is not configured.

## Current LitLaunch window ownership

### What LitLaunch owns

LitLaunch strongly owns the Streamlit backend process and its lifecycle. It starts the
backend, checks health, records runtime events, requests shutdown, applies termination
fallbacks, releases the port, and cleans up launch artifacts.

For webapp launches, LitLaunch can also own temporary artifacts such as its managed
Chromium profile and Windows shortcut. Those artifacts are not equivalent to owning
the browser process or every browser window.

### What LitLaunch observes

LitLaunch launches browser and webapp experiences but intentionally does not retain or
manage a browser process as part of `RuntimeSession`. The browser abstractions return
launch metadata and cleanup callbacks, not a durable browser process or window
controller.

Window monitoring is explicitly observation-only. On Windows, LitLaunch enumerates
visible top-level windows, excludes the pre-launch baseline, and matches by browser,
title, URL hints, process, and stability. It watches the selected app window for close
so the backend can stop. Browser-mode monitoring similarly observes a newly opened
browser window and does not control it.

### Existing presentation mutation

Webapp mode already contains narrow best-effort Windows presentation mutations for a
custom icon and app identity after the app window is observed. This proves that a
stable HWND can sometimes be used for presentation policy. It does not establish a
general ownership right, and it should not be treated as a resize abstraction.

This creates a real architectural tension: the monitor and provider contracts promise
observation only, while a callback currently performs a small presentation mutation.
Host sizing should resolve that tension explicitly instead of adding another mutation
inside the monitor callback.

### Current capability conclusion

LitLaunch cannot resize a window today. There is no native sizing protocol, no
`SetWindowPos` path, no viewport-to-window conversion, and no policy state machine.

The current app-mode candidate selection is adequate for passive close monitoring but
is not authoritative enough for privileged sizing. A resize implementation must refuse
to act unless exactly one new, stable, matching app-mode window is identified.

Ordinary browser tabs and browser-mode windows remain outside this capability. The
first implementation should apply only to managed-profile Chromium webapp windows on
Windows.

## LitBridge sizing contract

LitBridge's `autoResize(...)` reporter has the following properties:

- It is frontend-local and instance-scoped.
- It can report as soon as the bridge is active and its root is measurable, before the
  overall application has reached a final visual state.
- `height` is the measured component surface content extent, including the root's
  vertical offset, rendered height, and bottom padding.
- `width`, when present, is the corresponding horizontal surface extent.
- `hostViewportWidth` and `hostViewportHeight` are the readable parent viewport when
  available, otherwise the component iframe viewport.
- Reports are coalesced through one animation frame.
- Reports with unchanged dimensions, or changes of one CSS pixel or less, are
  suppressed.
- Callback failures are isolated.
- Observation stops on destroy, preventing late callbacks.
- Multiple reporter instances operate independently.

The sizing `sequence` is local to one reporter instance and increases only when that
instance emits a report. It is not LitBridge's action/render `client_sequence`, and it
must never share validation or ordering rules with application actions. Stale sizing
reports should be rejected only within the bound `(launch_id, source_id)` sizing
authority.

Two contract details shape the host policy:

1. LitLaunch cannot wait for a fixed number of identical reports because LitBridge
   suppresses duplicates. A quiet period after the latest material content change is
   the appropriate stabilization rule.
2. Resizing the host changes viewport dimensions and may cause another report even
   when content dimensions are unchanged. The first policy should apply once and then
   terminate so it cannot enter a viewport-content feedback loop.

## Dimension gap

LitBridge reports a component surface, not a complete native window target. Its
`height` does not include all Streamlit page space, component placement above or below
the surface, browser app-mode chrome, native non-client borders, or taskbar work-area
constraints.

LitLaunch therefore must not treat `content.height` as a browser viewport height or an
outer-window height. Doing so would produce a plausible number with the wrong
semantics.

The app-owned adapter should provide one of these generic values:

- a complete `desiredHostViewportHeight`, preferred for the first version; or
- explicit host shell geometry that lets the adapter derive that value without
  LitLaunch inspecting Streamlit markup.

The adapter may use product-owned layout information, but the design should not depend
on unstable Streamlit CSS selectors or cross-origin DOM access. LitBridge Surface Mode
compatibility itself describes Streamlit layout selectors as best-effort, so they are
not a suitable foundation for privileged host mutation.

Width should be preserved in the first version. Height-only fitting is easier to
explain, less disruptive, and sufficient to prove the model.

## Transport evaluation

| Option | Assessment | Decision |
| --- | --- | --- |
| Loopback HTTP POST | One-way, low latency, standard-library host, easy to test, independent of Streamlit state. Requires strict authentication and CORS handling. | **Recommended** |
| WebSocket or SSE | Adds a persistent connection and lifecycle complexity without a need for host-to-page streaming. | Reject for v1 |
| Streamlit component value/action | Couples sizing to application transport, reruns, ordering, and state that LitBridge intentionally avoids. | Reject |
| Chrome DevTools Protocol | Can expose window bounds, but requires remote debugging, browser-specific target discovery, and a larger security surface. Relevant methods are experimental. | Reject for v1 |
| Browser extension or injected bridge | Adds deployment, permission, support, and browser coupling. | Reject |
| Window title or URL signaling | Low bandwidth, observable, spoofable, and conflicts with title monitoring. | Reject |
| Generic app-owned host callback | Preserves package independence and makes opt-in explicit. It still needs a transport. | **Recommended adapter boundary** |
| Leave reports for a future native host | Safest fallback if native geometry or browser security prerequisites fail. | Retain as defer path |

### Recommended transport

LitLaunch should create a short-lived, loopback-only HTTP endpoint before starting the
backend. It should generate a high-entropy per-launch capability token and launch ID,
redact the token through existing diagnostics infrastructure, and expose the channel
configuration to the launched application through environment variables.

The application deliberately forwards the non-secret integration configuration into
its product-owned frontend configuration and provides the capability token only to the
designated adapter. The adapter sends authenticated JSON reports directly to the
LitLaunch loopback endpoint. It must not use Streamlit component values, actions,
session state, or reruns.

The endpoint should be closed as soon as sizing reaches a terminal state or the launch
shuts down.

An illustrative report is:

```json
{
  "protocol": 1,
  "launch_id": "opaque-launch-id",
  "source_id": "primary-surface",
  "sequence": 7,
  "device_pixel_ratio": 1.0,
  "content": {
    "height": 742,
    "width": 1180
  },
  "host_viewport": {
    "height": 812,
    "width": 1280
  },
  "desired_host_viewport": {
    "height": 790
  }
}
```

The capability token belongs in a custom request header, never in the URL, body,
events, or diagnostic bundle.

Browser local-network protections continue to evolve. The endpoint must support CORS
preflight, use an exact allowed application origin, and be manually verified against
the current supported Edge and Chrome versions. Wildcard origins are not acceptable.

## Recommended architecture

```text
LitBridge surface observer
        |
        | generic SurfaceContentSize callback
        v
Application-owned host-sizing adapter
        |
        | authenticated loopback HTTP POST
        v
LitLaunch host-sizing channel
        |
        | validate, bind authority, debounce, clamp, apply policy
        v
LitLaunch WindowSizer capability
        |
        | exact launch-associated HWND only
        v
Windows app-mode window
```

### Host-side channel

The channel should follow the lifecycle and capability-token precedent already used by
LitLaunch's local shutdown integration, but in the opposite direction. It should have
a dedicated protocol, schema, bounds, rate limits, and shutdown state.

The channel receives observations. It does not directly resize. Valid reports are
handed to a small policy state machine that can reach one terminal decision: applied,
skipped, timed out, conflicted, or shut down.

### Application adapter

The first integration should be documented as a small app-owned TypeScript adapter.
LitLaunch should not ship a JavaScript package until at least two independent product
integrations demonstrate a stable shared contract.

The adapter has three jobs:

1. Receive LitBridge's generic `SurfaceContentSize` callback.
2. Add the application's source identity and desired host viewport geometry.
3. POST the bounded report to the LitLaunch channel.

LitBridge does not import, detect, or name LitLaunch. LitLaunch does not import or
depend on LitBridge.

### Native mutation seam

Add a separate, narrow `WindowSizer` or `WindowController` capability rather than
adding mutation methods to `WindowMonitor` or `WindowProvider`. The controller may
resize one authorized normal app-mode HWND. It must not close windows, move arbitrary
windows, kill browser processes, or turn observation into general browser ownership.

The authority object should be created only after the discovery layer proves there is
exactly one new, stable candidate associated with this launch. Ambiguity disables host
sizing while leaving normal launch and close monitoring intact.

## Trust and security model

Window resizing is a privileged host mutation. The design should enforce all of the
following:

- Default off and explicit profile or Python API opt-in.
- Webapp mode only.
- Windows, Edge, and Chrome only for the first implementation.
- Configured backend host must be loopback. Disable host sizing for wildcard,
  LAN-facing, or other network-exposed launches.
- LitLaunch-managed ephemeral browser profile required. External profiles can carry
  unknown zoom, window state, and browser policy.
- Endpoint binds to literal loopback, never a wildcard interface.
- Per-launch cryptographically random capability token in a custom request header.
- Exact CORS application-origin allowlist and explicit preflight handling.
- Versioned JSON schema, finite numeric values, integer normalization, and a small
  request-body limit.
- Hard viewport bounds in addition to configured bounds and monitor work-area clamps.
- Monotonic sequence checks per bound source.
- Report frequency and total-report limits even though LitBridge already coalesces.
- One source authority per launch. A conflicting source terminates sizing rather than
  competing for the window.
- No action after the policy completes or shutdown begins.
- Token and endpoint credentials added to redaction rules and omitted from events.

A local process could still connect to a loopback endpoint if it obtains or guesses the
port. The high-entropy capability token prevents practical blind spoofing. JavaScript
inside the launched application that receives the token can submit reports, so the
token authenticates the launched app capability, not the moral intent of every script
inside that app. The remaining risk is bounded by one source, one resize, strict size
limits, a short endpoint lifetime, and local-only eligibility.

## Recommended policy model

### First policy: initial fit

The first and only public policy should be `initial`:

1. Wait for an exact, stable app-window authority and a valid sizing report.
2. Start or reset a short quiet-period timer when a material content dimension changes.
3. Do not reset stabilization for a report whose only change is host viewport size.
4. At the end of the quiet period, validate window state and user intent again.
5. Apply at most one height resize.
6. Close the channel and stop sizing immediately.

A quiet period near 250 ms and an overall deadline near 5 seconds are reasonable
starting points for the implementation spike. They should begin as tested internal
constants, not public knobs.

The host should not wait for N equal reports because equal reports are deduplicated by
LitBridge. A host minimum-delta rule is useful only when comparing the desired target
with the current window; it should not recreate LitBridge's measurement filtering.

### Deferred policies

`fit-until-user-resize` is attractive but requires reliable distinction between a user
resize, a system snap, a DPI transition, and LitLaunch's own mutation. It should remain
deferred until that state can be observed without guesswork.

Continuous fitting should not be implemented as a default or as an undocumented
escape hatch. It is prone to oscillation, viewport feedback, and conflict with user
intent.

## Native geometry and DPI

The report uses CSS pixels while Windows APIs operate in coordinates affected by the
calling process's DPI awareness and the target monitor. A safe conversion must be
proven rather than inferred.

The likely conversion for a normal managed-profile app window is:

1. Capture current native outer-window bounds.
2. Capture the current browser viewport in CSS pixels from the report.
3. Calculate the desired viewport-height delta in CSS pixels.
4. Convert that delta with the target window's effective DPI.
5. Add the converted delta to the current outer height, preserving the browser's
   current non-client area.
6. Clamp the result to the current monitor's work area.
7. Apply one `SetWindowPos` mutation that preserves width, top-left position, Z-order,
   and activation state.

The prerequisite spike must verify `GetWindowRect`, `GetClientRect`,
`GetWindowPlacement`, `GetDpiForWindow`, `MonitorFromWindow`, `GetMonitorInfo`, and
`SetWindowPos` behavior. DPI awareness must be scoped carefully; LitLaunch should not
change process-wide DPI awareness after UI-related APIs have already been used.

Browser zoom also affects the CSS-to-native relationship. The first version should
require LitLaunch's managed browser profile and test its default zoom. Host sizing
should be disabled for an external profile or detected non-default zoom until the
conversion is proven.

## Window state and multi-monitor rules

Automatic sizing should act only on a normal, unsnapped app-mode window.

- Minimized: skip.
- Maximized: skip.
- Fullscreen: skip.
- Snapped or tiled: skip when reliably detected; otherwise abort if geometry changes
  after authority is established and before application.
- Moved or manually resized during stabilization: abort and respect user intent.
- Multiple monitors: preserve the current monitor and top-left position.
- Mixed DPI: use target-window DPI and verify manually before support is declared.
- Oversized target: clamp height to the current monitor's work area.
- Width: preserve current width in v1.
- Centering: do not recenter or move the window for cosmetic reasons.

The current monitor should be selected from the target HWND, and bounds should use the
monitor work area rather than full display bounds so taskbars and reserved desktop
areas remain usable.

If the target cannot fit without an arbitrary move, prefer a smaller clamped height or
skip the mutation. Host sizing must never strand controls off screen.

## Multiple surfaces and authority

Only one explicitly designated top-level surface may control sizing for a launch.

The application decides which surface is authoritative and assigns a stable
`source_id`. The first valid source binds the session. Reports from a different source
cause an authority-conflict terminal state; LitLaunch must not aggregate, alternate,
or choose whichever report arrived last.

Hidden components, islands, dialogs, and page-local secondary surfaces should not be
wired to the host channel. If an application needs to aggregate product layout, it
must do that in its own frontend and submit one desired host viewport result.

## Minimal configuration surface

Host sizing should be absent and off by default. A minimal profile form is:

```toml
[profiles.my-app.host_sizing]
policy = "initial"
min_viewport_height = 480
max_viewport_height = 1200
```

The corresponding Python configuration should expose the same policy and optional
bounds. Omitting the table means off. `initial` is the only accepted non-off policy in
the first version.

Bounds are desired browser viewport heights in CSS pixels. Native hard limits and the
monitor work-area clamp always take precedence. Width preservation, quiet period,
deadline, report limits, and maximum automatic updates should remain implementation
policy rather than public configuration until experience proves users need control.

A CLI flag is not recommended for v1 because this capability also requires deliberate
frontend application wiring. Profiles and the Python API are the clearer product-app
integration surfaces. A CLI option can be considered after the contract is stable.

`inspect` and launch plans should report whether host sizing is off or eligible, its
policy, bounds, provider, and any deterministic ineligibility reason. They must not
show token or endpoint credentials.

## Observability

Useful structured runtime events include:

- `host_sizing_channel_ready`
- `host_sizing_report_accepted`
- `host_sizing_report_clamped`
- `host_sizing_authority_conflict`
- `host_sizing_resize_applied`
- `host_sizing_resize_skipped`
- `host_sizing_timed_out`
- `host_sizing_complete`

Invalid token, malformed report, stale sequence, and rate-limit events should be
aggregated or rate-limited so a bad page cannot pollute diagnostics.

Normal console output should remain quiet. An explicit but deterministically invalid
configuration may receive one concise warning. Missing reports, transport failures,
unsupported window states, and successful application belong in verbose output and
diagnostic events unless support experience proves otherwise.

Event details may include policy, source ID, sequence, requested and applied dimensions,
clamp reason, browser, monitor work area, DPI, and terminal reason. They must never
include the capability token.

## Failure and fallback behavior

Host sizing is an optional presentation enhancement. Every failure path must preserve
a normal usable launch.

If LitBridge is absent, the adapter is not registered, no report arrives, transport
fails, validation rejects a report, the browser is unsupported, the HWND is ambiguous,
the user changes the window, or shutdown begins, LitLaunch should stop host sizing and
continue normal runtime behavior. It should not retry indefinitely or emit repeated
console warnings.

No sizing failure should alter backend health, shutdown, port selection, browser close
monitoring, or runtime reporting.

## Browser and platform posture

The first supported target should be Windows app-mode windows launched through
LitLaunch's managed Chromium path:

- Microsoft Edge: prerequisite manual validation required.
- Google Chrome: prerequisite manual validation required.
- Other Chromium browsers: unsupported until individually validated.
- Browser mode and default-browser tabs: excluded.
- macOS and Linux: excluded until a native window provider and ownership model exist.

Chrome DevTools Protocol has experimental methods for obtaining browser windows and
setting bounds, but enabling remote debugging would add browser-specific authority and
security concerns. It is not justified for this feature while a narrow native HWND
path remains viable.

## Validation strategy

### Unit tests

- Versioned report schema and body limits.
- Token comparison and redaction.
- Finite dimensions, integer normalization, hard bounds, and configured clamps.
- Monotonic sequence handling per source.
- One-source authority and conflict termination.
- Quiet-period stabilization without requiring duplicate reports.
- Viewport-only report handling.
- One-application policy and terminal states.
- Manual geometry change, unsupported state, timeout, and shutdown cancellation.
- No mutation after completion or shutdown.

### Integration tests

- Loopback endpoint lifecycle and random port assignment.
- Authentication success and failure.
- Exact CORS origin and preflight behavior.
- A representative LitBridge-shaped report delivered by an app adapter.
- Policy execution through a fake `WindowSizer`.
- Missing report, malformed report, transport failure, and authority conflict fallback.
- Normal launch and shutdown remain unaffected.

### Windows and browser validation

- Edge and Chrome app-mode launches.
- Grow and shrink from different initial heights.
- Normal, minimized, maximized, fullscreen, snapped, and restored states.
- User move or resize during stabilization.
- Single-monitor 100%, 125%, 150%, and 200% scaling where available.
- Mixed-DPI monitor transitions.
- Taskbar on different edges and reduced work areas.
- Content growth and shrink before the quiet period.
- Viewport feedback report after LitLaunch applies the resize.
- Shutdown while a resize is pending.
- Managed profile default zoom and external-profile ineligibility.

Real-browser automation may support this matrix, but fakes and unit tests should prove
the policy independently. Manual visual validation remains required for native window
state and mixed-DPI behavior.

## First-version non-goals

- Arbitrary page-controlled window movement.
- Continuous automatic resizing.
- Width fitting.
- Ordinary browser tabs or uncontrolled browser windows.
- Cross-machine or LAN sizing messages.
- LitBridge as a LitLaunch dependency.
- LitLaunch as a LitBridge dependency.
- Streamlit action, value, session-state, or rerun transport.
- Streamlit source changes or fragile DOM/CSS selectors.
- Multi-surface aggregation.
- Generic responsive-layout behavior.
- Browser extensions or remote-debugging requirements.
- macOS or Linux native window sizing.
- Replacement for application-owned CSS and layout.

## Implementation roadmap

### LL-HS0: geometry and authority spike

Build a non-public Windows spike that proves exact single-window selection and
CSS-viewport-to-native-window conversion in Edge and Chrome. Exercise normal state,
work-area clamping, DPI scaling, mixed monitors, and user geometry changes. Do not add
a public configuration surface. Failure to produce repeatable results is a stop gate.

### LL-HS1: transport and trust foundation

Add the loopback host-sizing channel, per-launch capability token, protocol schema,
origin policy, environment handoff, redaction, lifecycle cleanup, and fake-client
tests. Do not mutate windows in this pass.

### LL-HS2: policy state machine

Implement source authority, sequence validation, quiet-period stabilization, bounds,
clamps, timeout, one-application behavior, terminal states, and shutdown cancellation
against a fake controller.

### LL-HS3: Windows sizing capability

Introduce the separate exact-HWND `WindowSizer`, native work-area and state checks,
DPI conversion, user-intent abort rules, and Edge/Chrome manual validation. Preserve
the observation-only window monitor contract.

### LL-HS4: reference app adapter

Document and validate an app-owned TypeScript adapter that receives LitBridge's
generic callback, derives the complete desired host viewport height, and posts one
authorized source. Keep both packages independent. Use an integration testbed rather
than either product's production source when practical.

### LL-HS5: diagnostics and public contract

Add concise events, inspect/report representation, troubleshooting guidance, profile
and Python API documentation, and the full Windows manual matrix. Decide whether
repeated consumer demand justifies a small frontend helper package or CLI option.

## Go/no-go answers

| Question | Answer |
| --- | --- |
| Is LitLaunch the right consumer? | Yes. Host-window policy belongs with runtime launch and native presentation governance. |
| Can it consume reports without direct LitBridge coupling? | Yes, through an app-owned adapter and authenticated loopback endpoint. |
| Can resizing be safe and unsurprising? | Potentially, if it is local, bounded, height-only, initial-fit-only, exact-window-only, and aborts on user or window-state changes. |
| Can it remain optional? | Yes. Both LitLaunch policy and app adapter wiring are explicit opt-ins. |
| Is initial fit sufficient for v1? | Yes. It provides the main presentation benefit without continuous feedback or user conflict. |
| Does LitLaunch currently have enough ownership? | Not yet. It has discovery and narrow presentation precedent, but needs exact authority and a separate mutation capability. |
| Is a frontend package justified now? | No. Start with a documented app-owned adapter and reconsider after multiple integrations. |
| Should this wait for a future native host? | Only if the Windows geometry or authority spikes fail without unsupported techniques. |

## Final recommendation

Proceed with **GO WITH PREREQUISITES**.

The recommended architecture is an application-designated LitBridge sizing authority
that sends a complete desired host viewport height to a short-lived, authenticated
LitLaunch loopback endpoint. LitLaunch validates the report, waits for one quiet
startup interval, and applies at most one bounded height change through a separate
Windows `WindowSizer` acting on exactly one launch-associated managed-profile webapp
window.

The recommended transport is HTTP POST to literal loopback with a per-launch
capability token, exact-origin CORS, a small versioned schema, strict bounds, one source,
and a terminal channel lifecycle.

The recommended policy is default-off, explicit opt-in, Windows Chromium webapp only,
height-only initial fit, preserve width and position, clamp to the monitor work area,
and abort on ambiguity, unsupported state, manual geometry changes, timeout, or
shutdown.

The first engineering work must be LL-HS0. No public API should be committed until it
proves exact window authority and reliable CSS-to-native geometry across supported
browsers and DPI configurations.

## External references

- [Chrome DevTools Protocol Browser domain](https://chromedevtools.github.io/devtools-protocol/tot/Browser/)
- [Fetch standard](https://fetch.spec.whatwg.org/)
- [Chrome Local Network Access](https://developer.chrome.com/blog/local-network-access)
- [Chrome Private Network Access preflights](https://developer.chrome.com/blog/private-network-access-preflight)
- [Microsoft GetWindowRect](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowrect)
- [Microsoft GetClientRect](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getclientrect)
- [Microsoft GetWindowPlacement](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowplacement)
- [Microsoft SetWindowPos](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowpos)
- [Microsoft MonitorFromWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-monitorfromwindow)
- [Microsoft GetMonitorInfo](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getmonitorinfoa)
- [Microsoft GetDpiForWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getdpiforwindow)
- [Microsoft high-DPI desktop development](https://learn.microsoft.com/en-us/windows/win32/hidpi/high-dpi-desktop-application-development-on-windows)
