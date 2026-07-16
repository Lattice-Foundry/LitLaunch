# Experimental Host-Sizing FAQ

## What does initial host sizing do?

It lets one trusted frontend surface request one bounded height fit after a
local Windows webapp opens. LitLaunch preserves the window's width, position,
activation, Z-order, and monitor placement.

## How do I enable it?

Set `host_sizing = "initial"` in a profile or pass `--host-sizing initial`.
The only policies are `off` and `initial`, and omission means `off`.

## Why is it off by default?

The app must deliberately provide a complete desired host viewport height, and
the feature changes native window geometry. Default-off behavior keeps ordinary
launches unchanged and avoids guessing about product-owned layout.

## What does initial mean?

The frontend may report while its first layout settles. LitLaunch then makes at
most one sizing attempt and permanently closes that launch's sizing channel.
Later content changes do not resize the window.

## Does it resize width or move the window?

No. The policy is height-only and preserves width and position. It is not
continuous fitting or general window management.

## What happens if fitting is unavailable?

The app remains open and usable, and the window stays unchanged. Unsupported
launches, missing reports, unsafe window states, user geometry changes,
authority loss, timeouts, and native refusal all fail safely.

## Which launches are supported?

Current scope is Windows webapp mode with an explicit Edge or Chrome selection,
a LitLaunch-managed browser profile, a loopback app host, and one trusted
frontend adapter. Browser tabs, unmanaged profiles, network-exposed apps,
width fitting, and continuous fitting are outside the feature.

## Why is it Experimental?

Current evidence covers Edge and Chrome, direct and shortcut launches, and 100%
and 150% mixed-DPI Windows 11 displays. Windows 10, 125% scaling, alternate
taskbar layouts, and independent Windows hosts remain unproven.

## Does it require LitBridge?

No. LitBridge can supply app measurements, but any trusted frontend can use the
documented report contract. LitLaunch does not import or detect LitBridge.

## How should the handoff be handled?

Forward it only to the trusted frontend surface for the current launch. Do not
log, persist, cache, place it in a URL, or embed it into static frontend assets.
See the [initial host-sizing guide](../Guides/host-sizing.md) for the audited
adapter pattern.
