"""Module execution entry point for ``python -m litlaunch``."""

from __future__ import annotations

from litlaunch.cli import main

if __name__ == "__main__":  # pragma: no cover - exercised through subprocess
    raise SystemExit(main())
