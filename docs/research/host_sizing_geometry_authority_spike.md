# LL-HS0 Windows Geometry and Exact-Window Authority Spike

- Date: 2026-07-14
- LitLaunch reference: 1.0.10
- Design reference: `litbridge_host_sizing_consumption_recon.md`
- Scope: private engineering spike only

## Verdict

**PROVEN WITH LIMITATIONS**

LitLaunch can identify one launch-associated Edge or Chrome app-mode HWND with
sufficient authority for one privileged resize when it retains the launched browser
process identity and requires exactly one stable matching window.

LitLaunch can also convert a CSS viewport-height delta into a native outer-window
height delta using the target window's effective DPI. The conversion produced exact
viewport results at 96 DPI and sub-pixel rounding error at 144 DPI on the available
mixed-DPI Windows host.

The spike does not establish a production contract. The current production browser
launcher does not retain process identity, and shortcut-based icon launches do not
return a browser process handle. Production host sizing must solve that authority
metadata gap before it can mutate a window.

## Scope

LL-HS0 tested only the two prerequisites from the host-sizing recon:

1. Exact launch-associated Chromium app-window authority.
2. Measured CSS-viewport to native-window height conversion.

It did not add transport, a loopback endpoint, LitBridge integration, profile or CLI
configuration, public events, a supported Python API, continuous resizing, width
fitting, or production window mutation.

LitBridge was used only as a read-only design reference. It was not modified or added
as a dependency.

## Implementation shape

The spike adds two private modules:

- `src/litlaunch/_host_sizing_geometry.py` contains authority classification, native
  geometry values, pure conversion and clamping logic, a guarded one-shot mutation
  service, and the Windows geometry backend.
- `src/litlaunch/_host_sizing_spike.py` is an unsupported `python -m` harness. It
  launches a temporary managed-profile browser app window, measures the real viewport,
  runs the authority and geometry probes, emits JSON evidence, and cleans up its owned
  browser process and temporary profile.

Neither module is exported from `litlaunch`, `litlaunch.windowing`, or the public CLI.
The existing observation-only `WindowMonitor` and `WindowsWindowProvider` contracts
remain unchanged.

## Measurement method

The harness serves a short-lived loopback HTML page. The page reports only these
browser-native observations in its title:

- `window.innerHeight`
- `window.innerWidth`
- `window.devicePixelRatio`

The dynamic title is a measurement instrument, not a proposed production transport.
It avoids Streamlit DOM selectors, CDP, browser extensions, injected product scripts,
and LitBridge coupling.

The page title begins with a random per-run `LL-HS0` token. The token allows the spike
to distinguish its own temporary window from unrelated browser windows. The browser is
launched directly with a temporary LitLaunch-managed `--user-data-dir`, first-run
suppression, background mode disabled, and optional spike-only initial size/position
flags.

The harness defaults to dry-run. `--apply` is required before `SetWindowPos` can be
called.

## Exact-window authority model

The private authority classifier requires all of the following:

1. Windows platform support.
2. A unique expected title token.
3. A top-level HWND not present in the pre-launch baseline.
4. Chromium app-window class `Chrome_WidgetWin*`.
5. Exact Edge or Chrome process-name match.
6. A window PID belonging to the browser process tree launched by the harness.
7. Exactly one matching candidate.
8. The same unique HWND across three consecutive polls.

The result is one of:

- `exact`
- `none`
- `ambiguous`
- `unsupported`

Mutation is possible only for `exact`. More than one candidate returns `ambiguous`
immediately. A candidate that changes handles restarts stability. Missing process
identity returns `unsupported`, not a weaker title-only match.

### Authority evidence

Every successful Edge and Chrome run produced exactly one candidate with:

- a new HWND;
- the expected `Chrome_WidgetWin_1` class;
- the requested browser process name;
- a PID in the launched managed-profile process tree;
- the random measurement title token; and
- three stable observations.

Unrelated pre-existing browser processes were not selected or mutated. Each run
cleaned up the exact browser process tree it launched. No `LL-HS0` window or temporary
profile remained after testing.

### Authority limitation

The spike launches Chromium directly and retains the root PID. Normal LitLaunch
browser launching currently discards the object returned by `Popen`. The Windows icon
path launches through a `.lnk` using shell activation and likewise does not retain a
browser process handle.

Therefore, the production path cannot yet reproduce the spike's process-tree proof.
Before production mutation, browser launch metadata must expose a private process
authority value or an equally strong managed-profile identity check. Title, class,
timing, and baseline exclusion alone remain insufficient for privileged mutation.

The spike uses a PowerShell CIM process-tree query as test instrumentation. That is not
recommended as the production authority mechanism.

## Windows geometry seam

The private `WindowsGeometryBackend` uses:

- `GetWindowRect` for outer bounds;
- `GetClientRect` for client-area evidence;
- `GetWindowPlacement` for show state;
- `GetDpiForWindow` for target-window effective DPI;
- `MonitorFromWindow` for the current monitor;
- `GetMonitorInfoW` for monitor and work-area bounds;
- `IsIconic` for minimized state;
- `IsZoomed` for maximized state; and
- `SetWindowPos` for one height-only mutation.

It temporarily enters `DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2` on the calling
thread with `SetThreadDpiAwarenessContext`, then restores the previous thread context.
It does not change process-wide DPI awareness.

`SetWindowPos` uses flags that preserve position, Z-order, owner Z-order, and activation.
The current width is passed unchanged. Post-apply geometry is captured again and must
confirm unchanged left, top, and width plus the planned height within one native pixel.

## Geometry formula

For a normal authorized window:

```text
css_delta = desired_viewport_height_css - current_viewport_height_css

dpi_scale = target_window_dpi / 96

native_delta = round(css_delta * dpi_scale)

requested_outer_height = current_outer_height + native_delta

target_outer_height = min(
    requested_outer_height,
    work_area_bottom - current_outer_top,
)

expected_viewport_height_css =
    current_viewport_height_css
    + (target_outer_height - current_outer_height) / dpi_scale
```

The formula intentionally uses a delta. It does not assume the Win32 client area is the
browser viewport and does not attempt to calculate browser chrome directly.

The observed client area and viewport were different in every app-mode test. On the
96-DPI runs, a native client height of 792 corresponded to a CSS viewport height of
761. This confirms that `GetClientRect` cannot be substituted for an actual browser
viewport observation.

The measured `devicePixelRatio` must match `GetDpiForWindow() / 96` within a small
tolerance. A mismatch fails closed because browser zoom or DPI virtualization may be
active.

## Safety gates

The spike refuses mutation when:

- authority is not `exact`;
- the title token is missing;
- launched process identity is unavailable;
- the window is minimized, maximized, fullscreen, or conservatively recognized as
  snapped;
- DPI is invalid or inconsistent with `devicePixelRatio`;
- the window top is outside the monitor work area;
- no usable work-area height remains;
- requested values are non-finite, non-positive, or above the hard spike limit;
- window geometry, monitor, DPI, work area, client size, or state changes between
  authority capture and apply; or
- post-apply position, width, or height does not match the plan.

The requested viewport height is clamped to a private 320 CSS-pixel minimum. Excess
height is clamped to the current monitor work area while preserving top-left position.
The spike does not center or move the window to gain additional space.

Common half, third, two-third, and half-height work-area partitions are treated as
snapped when their edges align within a DPI-scaled tolerance. This is deliberately
conservative but is not a complete Windows Snap Layout state API.

## Test environment

### Browsers

| Browser | Version | Launch form |
| --- | --- | --- |
| Microsoft Edge | 150.0.4078.65 | Chromium app mode, managed temporary profile |
| Google Chrome | 150.0.7871.116 | Chromium app mode, managed temporary profile |

No support claim is made for other Chromium builds or ordinary browser tabs.

### Displays

| Display | Native monitor bounds | Native work area | DPI | Scale |
| --- | --- | --- | --- | --- |
| Primary | `(0, 0)-(3440, 1440)` | `(0, 0)-(3440, 1392)` | 96 | 100% |
| Secondary | `(3440, -301)-(7280, 1859)` | `(3440, -301)-(7280, 1787)` | 144 | 150% |

This is a real mixed-DPI layout. The secondary monitor has a non-zero horizontal
origin and negative vertical origin.

The available machine did not provide 120-DPI/125% or 192-DPI/200% displays.

## Measured results

### Edge and Chrome at 96 DPI

Both browsers produced the same normal-window geometry from the spike's 1200 by 800
initial outer size:

- viewport before: 761 CSS px high;
- outer before: 800 native px high;
- desired viewport: 900 CSS px high;
- CSS delta: +139;
- native delta: +139;
- outer after: 939 native px high;
- viewport after: 900 CSS px high;
- measured error: 0 CSS px;
- width and top-left: unchanged.

Both browsers were also measured shrinking from a 1333 CSS-pixel viewport to 900:

- CSS/native delta: -433;
- outer before: 1372 native px high;
- outer after: 939 native px high;
- viewport after: 900 CSS px high;
- measured error: 0 CSS px.

### Work-area clamping at 96 DPI

Both Edge and Chrome were asked for a 1600 CSS-pixel viewport from the 761 CSS-pixel
starting viewport.

- unconstrained outer target: 1639 native px;
- available height below fixed top: 1382 native px;
- clamped outer target: 1382 native px;
- final outer bottom: work-area bottom 1392;
- expected viewport after clamp: 1343 CSS px;
- measured viewport: 1343 CSS px;
- measured error: 0 CSS px;
- left, top, and width: unchanged.

### Edge and Chrome at 144 DPI

Both browsers were launched directly on the 150% secondary monitor.

- viewport before: 763 CSS px high;
- outer before: 1200 native px high;
- `devicePixelRatio`: 1.5;
- `GetDpiForWindow`: 144;
- desired viewport: 900 CSS px high;
- CSS delta: +137;
- calculated native delta: round(137 x 1.5) = 206;
- outer after: 1406 native px high;
- expected viewport: 900.333 CSS px;
- measured viewport: 900 CSS px;
- measured error: 0.333 CSS px;
- native left: 3680 before and after;
- native top: -300 before and after;
- native width: 1800 before and after.

This proves the thread-scoped physical-coordinate path across the available mixed-DPI
monitor boundary and negative monitor origin.

### Window-state rejection

- Edge launched maximized was captured with `show_command=3` and state `maximized`.
  The plan was unsafe and no mutation occurred.
- Chrome launched fullscreen exactly covered the monitor bounds and was classified
  `fullscreen`. The plan was unsafe and no mutation occurred.
- Chromium ignored the spike's `--start-minimized` flag in app mode, so minimized
  state was not manually proven on this host. Deterministic tests cover the rejection
  rule.
- Snapped-state rejection is covered by deterministic common-layout tests. A real
  Windows Snap Layout interaction was not automated or claimed as manual proof.

### Pre-apply external change

The harness performed a controlled external 50-native-pixel height change after the
baseline plan but before the guarded apply call.

The second geometry snapshot detected both outer and client height changes. The spike
returned:

```text
Window geometry changed after authority capture; refusing mutation.
```

No planned host-sizing resize followed. This proves the underlying observation needed
to respect a user move, resize, monitor transition, or state change during future
stabilization.

## Deterministic coverage

The focused spike tests cover:

- exact, none, ambiguous, and unsupported authority;
- baseline, browser kind, unique title, and launched-process filtering;
- same-HWND stable polling;
- immediate ambiguity failure;
- CSS delta conversion at 96 and 144 DPI;
- DPI and `devicePixelRatio` mismatch rejection;
- minimum viewport and monitor work-area clamping;
- non-zero and negative monitor coordinates;
- minimized, maximized, fullscreen, and snapped rejection;
- conservative snap recognition;
- pre-apply geometry-change detection;
- width and position preservation;
- native post-apply verification;
- non-Windows backend rejection;
- measurement-title parsing; and
- dry-run defaults and JSON-safe output.

Native browser runs supplement these tests; they are not the only proof.

## Limitations

1. **Production launch authority is not wired.** Browser process identity is retained
   by the harness but not by the current `BrowserLauncher`, especially when Windows
   shortcut launch is used for custom icons.
2. **The unique title token is spike instrumentation.** Production authority cannot
   require an application to expose a launch secret or overload title-based signaling.
3. **Process-tree discovery is spike-only.** PowerShell CIM polling is suitable for
   evidence collection, not the recommended product seam.
4. **Only 96 and 144 DPI were available.** The 120 and 192 DPI cases remain in the
   manual matrix.
5. **Monitor placement was tested at launch, not after a live drag.** A pre-apply
   geometry-change simulation proves fail-closed detection, but a real cross-monitor
   drag remains manual follow-up.
6. **Minimized and snapped states were not manually exercised.** Chromium ignored its
   minimized startup flag, and no snap automation was introduced. Pure tests prove the
   rejection logic, not every shell transition.
7. **Only default managed-profile zoom was tested.** A DPI/`devicePixelRatio` mismatch
   intentionally refuses the resize.
8. **Snap recognition is heuristic.** There is no complete stable Win32 API that labels
   every Snap Layout arrangement. False-positive refusal is safer than mutation.
9. **The measurement page is not transport.** It exists only to establish real
   before/after viewport evidence.

## Required follow-up before production mutation

Before a future host-sizing policy can call the private geometry seam, LitLaunch must:

1. retain or derive a private launch-process authority for direct and shortcut-based
   managed-profile app-mode launches;
2. require exactly one stable new HWND in that authority boundary;
3. refuse mutation when process identity cannot be established;
4. validate 120 and 192 DPI when those displays are available;
5. manually exercise a real cross-monitor move, minimize/restore, and Snap Layout; and
6. keep the mutation capability separate from observation-only monitoring.

No current evidence requires CDP, browser extensions, Streamlit DOM selectors, or
process-wide DPI changes.

## LL-HS1 decision

**LL-HS1 authenticated loopback transport and trust foundation may begin.**

Transport can be implemented and tested without production window mutation. LL-HS1
should carry sizing observations only and terminate safely without a native action.
The browser process-authority gap must be resolved before transport is connected to a
production `WindowSizer` in the later native-mutation pass.

## Final verdict

Exact-window authority and CSS-to-native height conversion are feasible without
fragile browser or Streamlit techniques. The measured geometry result is strong across
Edge, Chrome, 96 DPI, 144 DPI, mixed monitors, negative origin, growth, shrink, and
work-area clamping. Current production launch metadata and the untested DPI/shell-state
matrix limit the support claim.

**PROVEN WITH LIMITATIONS**
