# Installation

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

Install from PyPI:

```powershell
python -m pip install litlaunch
```

Verify the CLI entry points:

```powershell
litlaunch --help
python -m litlaunch --help
```

The module form is useful when the environment can import LitLaunch but the
console script directory is not on `PATH`.

## Python Versions

The local development environment currently uses Python 3.14.5. Package metadata
allows Python 3.10 and newer. CI currently checks Python 3.10 through 3.14 on
Windows, Linux, and macOS. Windows and Linux receive first-party manual
validation. macOS behavior is supported with lighter first-party validation
while community coverage broadens.

Do not assume packaged-app behavior has been validated unless the integration
notes for that packaging path say so.
