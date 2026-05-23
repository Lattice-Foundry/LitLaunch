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
- lightweight profile shortcut script generation

Not implemented:

- PyInstaller recipes
- Nuitka recipes
- installer creation
- packaged resource discovery helpers
- TestPyPI/PyPI publishing automation

## Backend Command Providers

Packaged, frozen, or embedded apps can provide a command-only backend provider
to `StreamlitLauncher`. The provider receives the resolved host, port, URLs, and
configuration, then returns a shell-free command tuple. LitLaunch still starts
the process, injects shutdown environment variables, waits for health, launches
the browser target, and owns the `RuntimeSession`.

This is not turnkey PyInstaller, Nuitka, or cx_Freeze support. It is the runtime
extension seam those packaging workflows can use once the packaged executable
has been built to behave like a Streamlit backend.

The packaged executable must:

- bind the requested host and port
- expose Streamlit's health endpoint at `/_stcore/health`
- exit when LitLaunch requests graceful shutdown or terminates the owned
  backend process

Do not use a backend command provider to start background services or browser
processes. It is a command construction seam, not a runner abstraction.
`BackendCommand.description` is for human-readable diagnostics.
`BackendCommand.backend_kind` is optional metadata, not behavior policy.

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

## Profile Shortcuts

LitLaunch can generate lightweight project-local shortcuts for existing
profiles:

```powershell
litlaunch create shortcut --profile my-webapp
litlaunch create shortcut --profile my-webapp --dry-run
litlaunch create shortcut --profile my-webapp --kind script
```

The profile wizard can also offer shortcut creation after a profile is written.
Generated shortcuts are written under `.litlaunch/shortcuts/` in the app root
by default, so packaged-project repositories can ignore generated launch
artifacts with a single `.litlaunch/` entry.
Generated shortcuts are native project-local artifacts by default: `.lnk` on
Windows, `.desktop` on Linux, and a small `.app` bundle on macOS. Use
`--kind script` for `.bat`, `.sh`, or `.command` fallback scripts. macOS shortcut
support is beta until broader community validation expands.

Shortcuts are not installer artifacts, do not register with desktop menus, and
are not automatically placed on the Desktop, Start Menu, Dock, or distro-specific
launchers.

LitLaunch should remain the runtime layer beneath those workflows, not the
packaging or installer system.
