# Release Notes

## What's New

- Cleaner app-window launches: LitLaunch now hides Streamlit's default toolbar
  chrome by default, with `--show-streamlit-chrome` when you want it back.

- Better webapp isolation: Chromium app-mode launches use temporary browser
  profiles by default, keeping local app sessions from stepping on each other.

- More reliable close-to-shutdown behavior: app-window and browser-window
  monitoring now handles small title differences more gracefully.

- Smoother defaults for plain Streamlit apps: closing a monitored app window no
  longer treats missing custom cleanup hooks like an error.

- Product-style app icons: profiles, shortcuts, diagnostics, and Windows webapp
  launches can use `app_icon` for a more polished local app identity.

- Stronger Windows icon handling: LitLaunch uses shortcut and live window icon
  strategies to improve Edge and Chrome app-window presentation.

- Cleaner generated artifacts: project-local reports, shortcuts, temporary
  profiles, and temporary browser shortcuts stay organized under `.litlaunch/`.

- Better profile and shortcut workflows: repeatable local launches are easier
  to configure, inspect, and turn into project-local shortcuts.

- Stronger diagnostics and support surfaces: inspect/report workflows remain
  local, shareable after review, and focused on practical runtime posture.

- Better shutdown confidence: optional cleanup hooks are still available for
  apps that need them, while the normal path stays simple.

- Tighter release quality: stricter type checking and release hygiene checks
  now guard the package before publication.

- Cleaner public repository hygiene: internal working notes are organized away
  from public package artifacts.
