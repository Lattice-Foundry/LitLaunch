# Packaging Notes

LitLaunch is packaging-agnostic. It should support packaged Streamlit apps, but
it should not own packaging workflows.

## Current Position

Implemented:

- runtime command construction
- backend command provider seam
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

## Backend Command Providers

Packaged, frozen, or embedded apps can provide a command-only backend provider
to `StreamlitLauncher`. The provider receives the resolved host, port, URLs, and
configuration, then returns a shell-free command tuple. LitLaunch still starts
the process, injects shutdown environment variables, waits for health, launches
the browser target, and owns the `RuntimeSession`.

The packaged executable must:

- bind the requested host and port
- expose Streamlit's health endpoint at `/_stcore/health`
- exit when LitLaunch requests graceful shutdown or terminates the owned
  backend process

Do not use a backend command provider to start background services or browser
processes. It is a command construction seam, not a runner abstraction.

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
