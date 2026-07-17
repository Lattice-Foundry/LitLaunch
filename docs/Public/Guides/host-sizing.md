# Experimental Host Sizing

LitLaunch can fit the height of an eligible local Windows webapp window from
trusted frontend measurements. The feature is Experimental and off by default.

Three policies are available:

- `off` disables host sizing and is the default;
- `initial` accepts one stabilized sizing attempt near startup, then closes
  sizing authority; and
- `continuous` keeps sizing authority for the runtime session and accepts later
  meaningful content-fit updates.

Use `initial` for apps whose layout settles once. Use `continuous` for product
apps with route changes, expandable tools, or other trusted content that may
grow or shrink after launch.

The frontend owns browser and application geometry measurement. LitLaunch owns
authentication, sequencing, stabilization, exact window authority, native
height calculation, work-area clamping, mutation verification, and cleanup.

## Requirements

Every requirement must be met:

- Windows;
- `mode = "webapp"`;
- an explicit `browser = "edge"` or `browser = "chrome"`;
- the LitLaunch-managed temporary browser profile;
- a loopback app host such as `127.0.0.1`;
- one trusted frontend surface designated as the sizing authority;
- a normal, unsnapped app window; and
- a complete desired host viewport height reported in CSS pixels.

Both direct and generated-shortcut launches are supported when they retain
LitLaunch's exact managed browser-process and window authority.

Browser mode, default-browser selection, external `--user-data-dir` profiles,
network-exposed hosts, and unsupported window states do not resize. The app
still launches normally.

## Choose A Policy

Profiles are the recommended surface:

```toml
[profiles.studio]
app_path = "app.py"
title = "Studio"
mode = "webapp"
browser = "edge"
host_sizing = "continuous"
```

```powershell
litlaunch --profile studio
```

The direct CLI and Python configuration use the same policy:

```powershell
litlaunch app.py --mode webapp --browser chrome --host-sizing continuous
```

```python
from litlaunch import LauncherConfig, StreamlitLauncher

config = LauncherConfig(
    "app.py",
    mode="webapp",
    browser="edge",
    host_sizing="continuous",
)
session = StreamlitLauncher(config).start()
```

Replace `continuous` with `initial` for one sizing attempt. Omission means
`off`, and `--host-sizing off` can override a profile for one launch.

## Obtain The Frontend Handoff

The app process can request short-lived handoff metadata after an eligible
launch activates its private reporting channel:

```python
from litlaunch.host_sizing import get_host_sizing_handoff


def host_sizing_bootstrap():
    handoff = get_host_sizing_handoff()
    if handoff is None:
        return None
    return {
        "endpoint": handoff.endpoint,
        "launchId": handoff.launch_id,
        "protocol": handoff.protocol,
        "sourceId": handoff.source_id,
        "tokenHeader": handoff.token_header,
        "capabilityToken": handoff.capability_token,
    }
```

Pass that mapping only to the trusted top-level frontend that owns sizing. Do
not log, persist, cache, place it in a URL, or include it in static build
artifacts. The capability belongs only to the current launch.

The accessor returns `None` when host sizing is inactive or no valid
LitLaunch-managed child handoff exists. Its returned object is immutable, and
its representation redacts the capability token.

## App-Owned Reference Adapter

The frontend sends authenticated reports directly to LitLaunch from the exact
loopback app origin. The same report contract supports both `initial` and
`continuous`; later reports use increasing sequence values.

```ts
type HostSizingHandoff = {
  endpoint: string;
  launchId: string;
  protocol: number;
  sourceId: string;
  tokenHeader: string;
  capabilityToken: string;
};

type HostSizingObservation = {
  sequence: number;
  devicePixelRatio: number;
  content: {
    height: number;
    width?: number;
  };
  hostViewport: {
    height: number;
    width?: number;
  };
  desiredHostViewportHeight: number;
};

export function createHostSizingReporter(handoff: HostSizingHandoff) {
  return async function reportHostSize(
    observation: HostSizingObservation,
  ): Promise<void> {
    if (
      !Number.isFinite(observation.content.height) ||
      !Number.isFinite(observation.hostViewport.height) ||
      !Number.isFinite(observation.devicePixelRatio) ||
      !Number.isFinite(observation.desiredHostViewportHeight)
    ) {
      return;
    }

    try {
      await fetch(handoff.endpoint, {
        method: "POST",
        mode: "cors",
        cache: "no-store",
        credentials: "omit",
        headers: {
          "Content-Type": "application/json",
          [handoff.tokenHeader]: handoff.capabilityToken,
        },
        body: JSON.stringify({
          protocol: handoff.protocol,
          launch_id: handoff.launchId,
          source_id: handoff.sourceId,
          sequence: observation.sequence,
          device_pixel_ratio: observation.devicePixelRatio,
          content: observation.content,
          host_viewport: observation.hostViewport,
          desired_host_viewport: {
            height: observation.desiredHostViewportHeight,
          },
        }),
      });
    } catch {
      // Host sizing is optional; the base app remains usable.
    }
  };
}
```

The desired height must be the complete host-relative viewport target.
Component height alone is insufficient because the app shell may include
headers, spacing, or other product-owned layout.

Wire the reporter to whatever authoritative top-level content-size signal your
frontend already produces. Map that surface's host-relative content-bottom
measurement directly to the desired host viewport height rather than recreating
iframe offsets or DOM geometry in LitLaunch:

```ts
const reportHostSize = createHostSizingReporter(hostSizingHandoff);

// Called by your app's own top-level content-size observer.
function onContentSize(size) {
  if (
    size.hostViewportHeight === undefined ||
    size.hostContentBottom === undefined
  ) {
    return;
  }
  void reportHostSize({
    sequence: size.sequence,
    devicePixelRatio: window.devicePixelRatio,
    content: { height: size.height, width: size.width },
    hostViewport: {
      height: size.hostViewportHeight,
      width: size.hostViewportWidth,
    },
    desiredHostViewportHeight: size.hostContentBottom,
  });
}
```

Any trusted frontend that can report a complete host-relative content-bottom
measurement works. LitLaunch does not inspect the DOM, inject page scripts, or
infer browser geometry from constants.

## Runtime Behavior

Both policies retain only monotonically increasing reports from the one source
identified by the handoff. Duplicate, stale, malformed, unauthenticated, and
cross-launch reports are refused. Material input waits through a short quiet
period, and target differences at or below one CSS pixel do not mutate the
window.

With `initial`, the first stabilized sizing attempt completes the policy and
closes the channel. Later route or content changes cannot resize the window.

With `continuous`, a successful attempt returns the policy to an active waiting
state. Later meaningful growth or shrink measurements can produce another
height-only attempt until runtime shutdown. Each attempt revalidates the exact
browser process, HWND, normal window state, and last verified geometry.

Width, position, activation, Z-order, and monitor placement are preserved.
User movement or resizing, snapping, maximizing, minimizing, authority loss,
an unsafe target, or native refusal stops sizing safely without stopping the
backend or closing the app. LitLaunch never retries a native mutation.

## Diagnostics

Use plan and report tools to inspect the credential-free configured state:

```powershell
litlaunch report --profile studio --open
litlaunch inspect --profile studio --json
```

Plans and reports show the requested policy and static eligibility. Runtime
event logs contain only coarse lifecycle outcomes and bounded counts. They do
not include capability tokens, endpoint credentials, launch IDs, report bodies,
process trees, authority IDs, or window handles. Routine continuous resizes do
not add normal console noise.

## Limits

Host sizing is not width fitting, browser-tab control, browser automation,
general window management, hosted-app behavior, or an application-security
feature. `continuous` is content-fit policy for one exact LitLaunch-owned app
window, not arbitrary window control.

Current evidence covers Edge and Chrome on one Windows 11 host with 100% and
150% mixed-DPI displays, including a negative-origin secondary monitor.
Windows 10, 125% scaling, additional monitor/taskbar layouts, and independent
hosts remain part of the Experimental maturity boundary.

See the [host-sizing FAQ](../FAQ/host-sizing.md) for concise behavior and scope
answers.
