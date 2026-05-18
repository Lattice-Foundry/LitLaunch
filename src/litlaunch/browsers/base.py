"""Base browser adapter boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path

from litlaunch.exceptions import BrowserError


class BrowserAdapter(ABC):
    """Base class for shell-free browser launch command construction."""

    name: str
    supports_app_mode: bool = False

    def __init__(self, executable_path: str | Path | None = None) -> None:
        self.executable_path = Path(executable_path) if executable_path else None

    @abstractmethod
    def build_launch_command(
        self,
        url: str,
        *,
        title: str,
        extra_args: Sequence[str] = (),
    ) -> tuple[str, ...]:
        """Build a browser launch command without executing it."""

    def require_executable_path(self) -> Path:
        """Return the configured browser executable path or raise."""

        if self.executable_path is None:
            raise BrowserError(f"{self.name} executable path is required.")
        return self.executable_path
