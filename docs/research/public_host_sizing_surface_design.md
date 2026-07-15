# LL-HS7 Public Host-Sizing Surface Design

- Date: 2026-07-15
- LitLaunch reference: 1.0.10
- Scope: public-surface design only; no activation or implementation

## Verdict

**GO WITH LIMITATIONS**

LitLaunch has earned a small Experimental public surface for one initial height fit
of a local Windows webapp window. It has not earned general automatic sizing,
continuous fitting, browser-tab control, cross-platform support, or public access to
its transport and native authority machinery.

The exact launch-time setting should be:

```toml
host_sizing = "initial"
```

Omission means off. The only accepted values should initially be `off` and `initial`,
with `off` retained as an explicit value so CLI and profile overrides are possible.
No timing, source, transport, window, or viewport-bound knobs should be public.

## User model

### Intended user

The feature is for developers building local-first product applications that use
Streamlit as a runtime shell and have one frontend surface capable of reporting a
complete desired host viewport height. Typical consumers are:

- full-surface Svelte or other component applications;
- LitBridge Surface Mode applications with one authoritative top-level surface;
- local desktop-like tools launched in LitLaunch webapp mode; and
- LitPack-style applications whose product shell owns its layout.

The user is an integration developer, not an ordinary viewer. They understand the
application's complete host layout and can deliberately connect one product-owned
measurement source to the LitLaunch handoff.

### Users who do not benefit

Most Streamlit applications do not need host sizing. Standard dashboards, multipage
apps, ordinary browser-tab launches, hosted applications, and applications that
already fit comfortably in a normal browser window should leave it off. Enabling
webapp mode alone does not imply that content-driven window sizing is desirable.

### Users who should not enable it

Host sizing should not be enabled for:

- LAN-facing, hosted, remote, or multi-user Streamlit deployments;
- browser mode, default-browser launches, tabs, or unmanaged browser profiles;
- applications that need continuous fitting or width control;
- applications with competing top-level sizing surfaces;
- applications that cannot calculate a complete desired host viewport height; or
- workflows where the user expects to retain full manual control of initial window
  geometry.

## Default behavior

The default must remain **off**.

Neither `webapp` mode nor any application framework should enable host sizing
implicitly. A resize is visible native-window behavior, and most Streamlit apps do
not provide the required measurement contract. Automatic activation would therefore
turn a specialized integration into a surprising default and would create timeout
work on launches that can never submit a report.

Surface Mode should not imply activation either. LitLaunch does not detect or depend
on LitBridge, and LitBridge should not detect LitLaunch. The application opts in at
both boundaries: launch configuration requests `initial`, and one app-owned frontend
surface submits a desired host viewport.

There should be no environment-variable activation fallback. Environment metadata is
a child-process handoff after LitLaunch has already authorized the feature, not an
alternative public configuration path.

## Public configuration recommendation

### Canonical setting

Use one enum-like launch setting everywhere:

```toml
[profiles.studio]
app_path = "app.py"
mode = "webapp"
browser = "edge"
host_sizing = "initial"
```

The value describes a policy rather than a boolean capability:

| Value | Meaning |
| --- | --- |
| `off` | Do not create a sizing channel or attempt host mutation. This is the default. |
| `initial` | Accept one authoritative report and attempt at most one height fit. |

A boolean should be rejected because `true` does not say what behavior was requested
and becomes ambiguous as soon as another policy is considered. A nested table should
also be rejected for the first release because users do not need to tune internal
timing, limits, or authority behavior.

### Consistent launch surfaces

The same semantic value should be available through existing launch entry points:

```powershell
litlaunch app.py --mode webapp --browser edge --host-sizing initial
litlaunch --profile studio --host-sizing off
```

```python
LauncherConfig(
    "app.py",
    mode="webapp",
    browser="edge",
    host_sizing="initial",
)
```

Profiles should be the recommended path because host sizing normally accompanies a
repeatable product-app integration, but direct CLI and Python launches should not
have different capability models.

The implementation should add a string enum such as `HostSizingPolicy` with only
`OFF` and `INITIAL`, plus one `LauncherConfig.host_sizing` field. It should not add a
public configuration dataclass for the private policy engine.

### Plan and inspect behavior

Launch plans and `litlaunch inspect` should report the requested policy and a
credential-free eligibility summary. They should never display endpoint URLs,
capability tokens, launch IDs, raw process trees, HWNDs, or report bodies.

Useful plan states are:

- `off`;
- `initial / eligible by configuration`;
- `initial / unsupported on this platform or launch mode`; and
- `initial / runtime authority required`.

Static incompatibility should be visible before launch. Exact process and window
authority can only be resolved at runtime and should not be guessed during inspect.

## Python API recommendation

Host sizing is launch-time policy. Applications must not enable, disable, reset, or
re-run the policy after the runtime starts. The public launch API should therefore
expose only `LauncherConfig.host_sizing` and its enum.

The application does need a safe way to pass LitLaunch's per-launch handoff to its
trusted frontend. Do not make the reserved environment names the primary application
API. A later implementation pass should add one narrow accessor in a dedicated
module, conceptually:

```python
from litlaunch.host_sizing import get_host_sizing_handoff

handoff = get_host_sizing_handoff()
```

The accessor should return `None` when host sizing is inactive and otherwise return a
short-lived, redaction-safe object that can be serialized only for the trusted
top-level frontend. Its representation must omit the capability token. It must not
expose mutation, policy, channel lifecycle, arbitrary source IDs, or a Python method
for submitting reports.

This accessor is preferable to documenting raw environment access because it keeps
reserved names and parsing rules internal, provides one place to enforce redaction,
and lets LitLaunch evolve the child-process handoff without breaking applications.
The frontend payload remains sensitive launch capability data and must never be
logged, persisted, placed in a URL, or sent to secondary components.

## LitBridge integration recommendation

LitLaunch should not import LitBridge, and LitBridge should not gain a LitLaunch
dependency. `onContentSize` remains the correct generic measurement seam:

```ts
const app = createLitBridgeApp({
  resize: {
    root: ".studio-app",
    fit: "content",
    onContentSize(size) {
      hostSizing.report(size, desiredHostViewportHeight(size));
    },
  },
});
```

The example is intentionally conceptual. The application owns
`desiredHostViewportHeight(...)` because LitBridge measures its component surface,
not the complete Streamlit page or browser viewport. LitLaunch must never reinterpret
`content.height` as the desired host viewport height.

For the first public release, the host reporter should remain an application-owned,
framework-neutral adapter built from a maintained LitLaunch example. LitLaunch
should not publish a Svelte-specific helper, inject page scripts, or ask LitBridge to
name LitLaunch. One proof adapter is not enough evidence for a durable JavaScript
package API.

After two independent real applications use the same adapter shape, LitLaunch may
extract a tiny framework-neutral frontend helper. That helper would own protocol
serialization, headers, sequence forwarding, and failure isolation; it would still
leave desired viewport calculation and `onContentSize` wiring with the application.

## Security posture

Public activation must preserve the private proof's fail-closed boundaries:

- default off and explicit launch-time opt-in;
- Windows webapp mode only;
- explicit Edge or Chrome resolution only;
- a LitLaunch-owned ephemeral browser profile;
- a loopback application host and literal loopback sizing endpoint;
- one exact application origin;
- one per-launch capability token and launch ID;
- one fixed authoritative source per launch;
- bounded schema, body size, dimensions, rate, sequence, and lifetime;
- exact process-tree and HWND authority independent of report content;
- one height-only mutation with no retry; and
- endpoint closure at terminal state or before runtime shutdown.

Trust modes should not create a second eligibility model. Eligibility should depend
on the actual loopback host and proven launch conditions. `development`,
`strict_local`, or `internal_network` may describe a loopback launch, but any
non-loopback backend binding makes host sizing ineligible regardless of exposure
acknowledgement. The feature must not operate over LAN merely because LitLaunch is
allowed to launch the app there.

Browser mode, default-browser resolution, external `--user-data-dir`, unsupported
browsers, and non-Windows systems must never fall back to approximate authority.
They should continue launching the base app but emit one concise warning when the
user explicitly requested host sizing. Silent ignore would make a visible feature
look unreliable; failing the whole application would make an optional presentation
policy too powerful.

Runtime inability to establish exact authority, a missing report, user geometry
changes, unsafe window state, or native refusal should skip sizing and leave the app
running. Standard output should stay quiet unless the requested feature is known to
be unsupported. Verbose output, runtime events, and support reports may record a
bounded credential-free status and reason.

## User experience

With `host_sizing = "initial"`, the expected experience is:

1. The app launches normally in a managed Chromium webapp window.
2. The trusted frontend reports its measured content and complete desired host
   viewport.
3. LitLaunch waits for a short quiet period while exact window authority remains
   valid.
4. LitLaunch attempts one height-only fit, preserving width, position, activation,
   Z-order, monitor, and normal window state.
5. Sizing becomes terminal and the private endpoint closes.

The target is clamped to hard policy and monitor work-area bounds. A target already
within the minimum delta completes without visible movement. Content changes after
completion do nothing. The policy never follows later rerenders, navigation, dialogs,
or user-driven resizing.

If the user moves, resizes, snaps, maximizes, minimizes, or otherwise changes the
window while the initial fit is stabilizing, LitLaunch should respect that intent and
abort the sizing attempt. If no valid report arrives before the bounded timeout, the
window remains unchanged and the app continues.

## Documentation plan

The eventual public documentation should be small and task-oriented:

1. **Overview**: one initial height fit for local Windows product apps, default off.
2. **Requirements**: Windows, webapp mode, Edge or Chrome, managed profile, loopback
   host, one trusted reporting surface.
3. **Enablement**: profile, CLI, and `LauncherConfig` examples using only `initial`.
4. **Application handoff**: safe bootstrap access and the app-owned desired viewport
   responsibility.
5. **LitBridge example**: `onContentSize` wiring without package coupling.
6. **Behavior**: one resize after stabilization; no response to later content changes.
7. **Security**: local capability token, exact-origin transport, sensitive bootstrap,
   no LAN or hosted use.
8. **Limitations**: Experimental, Windows-only, height-only, managed Edge/Chrome,
   normal unsnapped windows.
9. **Troubleshooting**: eligibility checks, no-report timeout, user-geometry abort,
   authority unavailable, and where sanitized diagnostics appear.
10. **Non-goals**: no responsive window manager, browser automation, layout engine,
    or application security boundary.

The README should eventually receive only a short Experimental mention and a link to
the guide. CLI reference, profile reference, browser support, security, inspect, and
runtime-events documentation should carry the exact behavioral details.

## Migration strategy

The first implementation pass should promote the existing private activation path
instead of creating a parallel runtime:

1. Add `HostSizingPolicy` and the one `LauncherConfig` field with `off` as default.
2. Load the same value from profiles and CLI without exposing private policy config.
3. Convert `initial` into the existing per-launch activation collaborator.
4. Add the redaction-safe application handoff accessor while keeping environment
   names private.
5. Surface credential-free requested, eligibility, and terminal states through plans,
   inspect, verbose output, events, and reports.
6. Preserve every existing static gate, runtime fail-closed path, and cleanup order.
7. Add one real product integration before describing the feature as supported.

Existing users require no migration because omission remains off and normal launches
must be byte-for-byte equivalent at the configuration boundary. Private harnesses can
move to `host_sizing="initial"` only after the public path proves parity, then the
constructor-only gate can be removed.

If a future policy is added, it should be a new explicit value rather than a new
boolean or a reinterpretation of `initial`. Unknown values must fail configuration
validation.

## Examples

### Recommended profile

```toml
[profiles.studio]
app_path = "app.py"
title = "Studio"
mode = "webapp"
browser = "edge"
host_sizing = "initial"
```

```powershell
litlaunch --profile studio
```

### Temporary direct opt-in

```powershell
litlaunch app.py --mode webapp --browser chrome --host-sizing initial
```

### Explicit profile override

```powershell
litlaunch --profile studio --host-sizing off
```

### Unsupported intent

This configuration should launch the browser-mode app without sizing and report that
the requested policy is unsupported:

```powershell
litlaunch app.py --mode browser --host-sizing initial
```

It must not resize a guessed browser window or tab.

## Feature maturity

The first public release should be labeled **Experimental**.

The architecture, failure handling, and native mutation path are proven, including
real Edge and Chrome direct and shortcut launches. The evidence is nevertheless from
one Windows host, one 96-DPI display context, current browser versions, and a proof
adapter rather than a released product integration.

Experimental exposure is appropriate because every failure degrades to an unchanged
window and the base app remains usable. Calling it Supported would require at least:

- repeatable Windows 10 and Windows 11 validation;
- 100%, 125%, 150%, and mixed-DPI monitor coverage;
- normal-window behavior across common work-area and multi-monitor layouts;
- current Edge and Chrome regression coverage on more than one machine;
- one real product-app integration using the public handoff; and
- confirmation that public diagnostics are useful without exposing credentials or
  low-level window identity.

An RC label is less clear for a capability inside a stable package. Experimental is a
feature-level maturity statement and can remain until the support matrix is earned.

## Future expansion

Future work may add a framework-neutral reporter helper after repeated integrations
prove its shape. Cross-platform native hosts, another explicit one-shot policy, or
width fitting may be researched independently, but none should weaken `initial` or
expand its eligibility by fallback.

Continuous fitting, user-resize detection, arbitrary bounds, timing controls, custom
source IDs, and unmanaged profiles should not be placed on a roadmap merely because
private primitives could support them. Each would need its own user case and proof.

## Non-goals

The public feature is not:

- a general window manager;
- continuous responsive sizing;
- browser-tab or arbitrary-window control;
- a Streamlit page-layout detector;
- a LitBridge-specific launcher;
- a replacement for application-owned layout calculations;
- browser automation or remote debugging;
- a hosted, LAN, authentication, authorization, or security feature;
- a way to move, center, maximize, minimize, snap, close, or kill browser windows; or
- a public transport, token, process, HWND, geometry, or `SetWindowPos` API.

## Final recommendation

Proceed with a public implementation pass, but expose the capability as Experimental
and preserve the proven boundary exactly.

The entire user-facing launch policy is:

```text
host_sizing = off | initial
```

`off` is the default. `initial` is explicit, Windows-only, webapp-only,
managed-Edge/Chrome-only, loopback-only, height-only, one-shot, bounded, and
fail-soft. LitLaunch owns transport, trust, stabilization, exact authority, mutation,
cleanup, and credential-free diagnostics. The application owns whether to opt in,
which single surface reports, and the complete desired host viewport height.

That is enough public power for the evidence currently available, and no more.

**GO WITH LIMITATIONS**
