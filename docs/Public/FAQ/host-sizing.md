# Experimental Host-Sizing FAQ

## What policies are available?

`off` disables sizing and is the default. `initial` allows one stabilized
sizing attempt near startup. `continuous` keeps authenticated sizing authority
for meaningful later content growth and shrink until the runtime stops.

## Which policy should I use?

Use `initial` when the application layout settles once. Use `continuous` for
apps with route changes, expandable tools, or other trusted content that can
change height after launch.

## How do I enable it?

Set `host_sizing = "initial"` or `host_sizing = "continuous"` in a profile, or
pass the matching `--host-sizing` value. Omission means `off`.

## Why is it off by default?

The app must deliberately provide a complete desired host viewport height, and
the feature changes native window geometry. Default-off behavior avoids
guessing about product-owned layout.

## Does continuous resize on every frontend update?

No. Reports must be authenticated, launch-bound, source-bound, and
monotonically sequenced. LitLaunch ignores duplicates, stale reports, and target
jitter at or below one CSS pixel, then stabilizes meaningful changes before a
native attempt.

## Does it resize width or move the window?

No. Both policies are height-only and preserve width and position. Host sizing
is not general window management.

## What happens if fitting is unavailable?

The app remains open and usable, and the window stays unchanged. Unsupported
launches, missing reports, unsafe window states, user geometry changes,
authority loss, timeouts, and native refusal all fail safely.

## Which launches are supported?

Current scope is Windows webapp mode with an explicit Edge or Chrome selection,
a LitLaunch-managed browser profile, a loopback app host, and one trusted
frontend adapter. Browser tabs, unmanaged profiles, network-exposed apps, and
width fitting are outside the feature.

## Why is it Experimental?

Current evidence covers Edge and Chrome, direct and shortcut launches, and 100%
and 150% mixed-DPI Windows 11 displays. Windows 10, 125% scaling, alternate
taskbar layouts, and independent Windows hosts remain unproven.

## Does it require a specific frontend framework?

No. Any trusted frontend that can report a complete host-relative content
measurement can use the documented report contract. LitLaunch does not import,
detect, or require any particular frontend library.

## How should the handoff be handled?

Forward it only to the trusted frontend surface for the current launch. Do not
log, persist, cache, place it in a URL, or embed it into static frontend assets.
See the [host-sizing guide](../Guides/host-sizing.md) for the audited adapter
pattern.
