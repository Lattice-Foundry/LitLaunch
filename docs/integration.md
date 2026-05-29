# Integration

LitLaunch is designed to sit underneath real Streamlit application workflows:
source checkouts, packaged app launchers, internal dashboards, and local-first
desktop-style tools. Integration should keep LitLaunch focused on runtime
ownership while the downstream application owns product policy, packaging, and
user-facing support decisions.

## Core Integration Shape

- Build a `LauncherConfig` or profile from app-specific settings.
- Let LitLaunch own backend process startup, health checks, browser launch,
  graceful shutdown, diagnostics, and reports.
- Register app cleanup through LitLaunch shutdown hooks when needed.
- Keep packaging, installer creation, auth, reverse proxies, and app-specific
  resource discovery outside LitLaunch.

## Notes

- [RoleThread Lite](integration/rolethread.md) describes a concrete product-app
  integration shape.
- [Packaging Notes](integration/packaging_notes.md) describes the runtime seams
  packaged apps can use without treating LitLaunch as a packaging framework.
