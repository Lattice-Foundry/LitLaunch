# Experimental Initial Host Sizing

LitLaunch can perform one bounded initial height fit for an eligible local
Windows webapp window. The feature is Experimental and off by default.

It is intended for product-style Streamlit apps whose trusted frontend can
calculate the complete host viewport height needed for the initial layout.
LitLaunch owns authentication, stabilization, exact window authority, native
height mutation, and cleanup. The application owns measurement and geometry
interpretation.

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

Browser mode, default-browser selection, external `--user-data-dir` profiles,
network-exposed hosts, and unsupported window states do not resize. The app
still launches normally.

## Enable Initial Sizing

Profiles are the recommended surface:

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

The direct CLI and Python configuration use the same policy:

```powershell
litlaunch app.py --mode webapp --browser chrome --host-sizing initial
```

```python
from litlaunch import LauncherConfig, StreamlitLauncher

config = LauncherConfig(
    "app.py",
    mode="webapp",
    browser="edge",
    host_sizing="initial",
)
session = StreamlitLauncher(config).start()
```

The only values are `off` and `initial`. Omission means `off`. An explicit
`--host-sizing off` can override a profile for one launch.

## Obtain The Frontend Handoff

The app process can request short-lived handoff metadata after LitLaunch has
authorized host sizing:

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

Pass that mapping only to the trusted top-level frontend that owns sizing.
Do not log, persist, cache, place in a URL, or include it in static build
artifacts. Frontend exposure grants one bounded sizing capability for that
launch. Code already running inside the app process can read the same launch
environment, so the handoff is not an application-security boundary.

The accessor returns `None` when host sizing is inactive or no valid
LitLaunch-managed child handoff exists. Its returned object is immutable, and
its representation redacts the capability token.

## App-Owned Reference Adapter

The frontend sends authenticated reports directly to LitLaunch. This small
TypeScript pattern is framework-neutral and intentionally remains app-owned:

```ts
type HostSizingHandoff = {
  endpoint: string;
  launchId: string;
  protocol: number;
  sourceId: string;
  tokenHeader: string;
  capabilityToken: string;
};

type ContentSize = {
  height: number;
  width?: number;
};

type HostSizingObservation = {
  sequence: number;
  devicePixelRatio: number;
  content: ContentSize;
  hostViewport: {
    height: number;
    width?: number;
  };
};

export function createHostSizingReporter(handoff: HostSizingHandoff) {
  return async function reportInitialHostSize(
    observation: HostSizingObservation,
    desiredHostViewportHeight: number,
  ): Promise<void> {
    if (
      !Number.isFinite(observation.content.height) ||
      !Number.isFinite(observation.hostViewport.height) ||
      !Number.isFinite(observation.devicePixelRatio) ||
      !Number.isFinite(desiredHostViewportHeight)
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
            height: desiredHostViewportHeight,
          },
        }),
      });
    } catch {
      // Host sizing is optional; the base app remains usable.
    }
  };
}
```

The application must supply the complete desired host viewport height.
Component content height alone is not a native window target because the host
viewport may include app shell, spacing, headers, or other product-owned
layout.

For LitBridge, wire one top-level `onContentSize` callback to this adapter:

```ts
const reportHostSize = createHostSizingReporter(hostSizingHandoff);

const app = createLitBridgeApp({
  resize: {
    root: ".studio-app",
    fit: "content",
    onContentSize(size) {
      if (size.hostViewportHeight === undefined) {
        return;
      }
      const desiredHostViewportHeight = size.height + appOwnedShellHeight;
      void reportHostSize(
        {
          sequence: size.sequence,
          devicePixelRatio: window.devicePixelRatio,
          content: { height: size.height, width: size.width },
          hostViewport: {
            height: size.hostViewportHeight,
            width: size.hostViewportWidth,
          },
        },
        desiredHostViewportHeight,
      );
    },
  },
});
```

LitBridge is optional. Any trusted frontend can use the same report contract.
LitLaunch does not import LitBridge, inject page scripts, or infer complete
host geometry from component measurements.

## Runtime Behavior

The frontend may submit updated measurements while the initial layout settles.
LitLaunch retains monotonic reports from the one designated source, waits for
the bounded quiet period, and attempts at most one height-only change. Width,
position, activation, Z-order, and monitor placement are preserved.

After the attempt completes, times out, aborts, or fails safely, the sizing
channel closes permanently for that launch. Later content changes do not
resize the window.

User movement, resizing, snapping, maximizing, minimizing, authority loss, an
unsafe target, or native refusal causes LitLaunch to leave the window
unchanged. These outcomes do not stop the backend or close the app.

## Diagnostics

Use plan and report tools to inspect the credential-free configured state:

```powershell
litlaunch report --profile studio --open
litlaunch inspect --profile studio --json
```

Plans and reports show the requested policy and static eligibility. Runtime
event logs may record coarse outcomes such as channel ready, report accepted,
applied, timed out, skipped, or failed safely. They never include the
capability token, endpoint credentials, launch authority, process tree, or
window handle.

## Limits

Initial host sizing is not continuous fitting, width fitting, browser-tab
control, browser automation, a general window manager, hosted-app behavior, or
an application security feature. Current evidence covers Edge and Chrome on
one Windows 11 host at 96 DPI. Broader Windows versions, display scaling, and
mixed-DPI setups remain part of the Experimental maturity boundary.
