# Installation

LitLaunch is currently in beta stabilization and TestPyPI rehearsal readiness.

## Source Checkout

For development:

```powershell
git clone https://github.com/Lattice-Foundry/LitLaunch
cd LitLaunch
python -m pip install -e .[dev]
```

Rerun the editable install after changing package versions or build metadata.
Editable-install metadata is generated during installation, so stale local
metadata can make `importlib.metadata.version("litlaunch")` report an older
version than `litlaunch.__version__` until the package is reinstalled.

Run checks:

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python scripts/check_release.py
```

## Package Install

After publication:

```powershell
python -m pip install litlaunch
```

## Python Versions

The local development environment currently uses Python 3.14.5. Package metadata
allows Python 3.10 and newer. CI currently checks Python 3.10 through 3.14 on
Windows, Linux, and macOS.

Do not assume packaged-app behavior has been validated unless the integration
notes for that packaging path say so.
