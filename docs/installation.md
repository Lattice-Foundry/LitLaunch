# Installation

LitLaunch is currently in pre-beta internal integration and TestPyPI rehearsal
readiness.

## Source Checkout

For development:

```powershell
git clone https://github.com/LatticeFoundry/litlaunch
cd litlaunch
python -m pip install -e .[dev]
```

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
allows Python 3.10 and newer. CI currently checks Python 3.10, 3.12, and 3.14 on
Windows, Linux, and macOS.

Do not assume packaged-app behavior has been validated unless the integration
notes for that packaging path say so.

