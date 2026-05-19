# Packaging Notes

LitLaunch is packaging-agnostic. It should support packaged Streamlit apps, but
it should not own packaging workflows.

## Current Position

Implemented:

- runtime command construction
- backend process ownership
- browser/app-mode launch
- graceful shutdown hooks
- diagnostics

Not implemented:

- PyInstaller recipes
- Nuitka recipes
- installer creation
- shortcut generation
- packaged resource discovery helpers
- TestPyPI/PyPI publishing automation

## PyInstaller / Nuitka

Future notes should cover:

- locating the Streamlit app entrypoint
- including static/assets files
- ensuring Streamlit is available in the packaged environment
- browser launch behavior from packaged executables
- shutdown endpoint behavior

Do not assume packaged behavior is validated until a smoke checklist exists.

## uv / pipx

Future notes should cover:

- installing LitLaunch CLI
- running source-checkout examples
- isolating app dependencies from launcher tooling

## Windows Shortcuts

Future notes should cover:

- command line target
- working directory
- icon handling
- app-mode browser preference
- monitor-window opt-in

LitLaunch should remain the runtime layer beneath those workflows, not the
installer framework.

