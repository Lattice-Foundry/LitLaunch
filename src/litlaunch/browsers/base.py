"""Base browser adapter boundary."""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from litlaunch.config import BrowserChoice
from litlaunch.exceptions import BrowserError
from litlaunch.platforms import PlatformDetector, PlatformInfo


class BrowserKind(str, Enum):
    """Supported browser capability kinds."""

    EDGE = "edge"
    CHROME = "chrome"
    DEFAULT = "default"


@dataclass(frozen=True)
class BrowserCapability:
    """Detected browser launch capability."""

    kind: BrowserKind
    name: str
    executable_path: str | None
    available: bool
    supports_app_mode: bool
    supports_full_browser: bool
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class BrowserResolution:
    """Result from resolving a browser preference against capabilities."""

    requested: BrowserChoice
    selected: BrowserCapability | None
    fallback_chain: tuple[BrowserCapability, ...]
    message: str


class BrowserAdapter(ABC):
    """Base class for shell-free browser launch command construction."""

    kind: BrowserKind
    name: str
    supports_app_mode: bool = False
    supports_full_browser: bool = False

    def __init__(
        self,
        executable_path: str | Path | None = None,
        *,
        which_func: Callable[[str], str | None] = shutil.which,
        env: Mapping[str, str] | None = None,
        path_exists_func: Callable[[Path], bool] | None = None,
    ) -> None:
        self.executable_path = str(executable_path) if executable_path else None
        self.which_func = which_func
        self.env = dict(env or {})
        self.path_exists_func = path_exists_func or Path.is_file

    @abstractmethod
    def detect(self, platform_info: PlatformInfo | None = None) -> BrowserCapability:
        """Detect this adapter's browser capability without launching it."""

    @abstractmethod
    def build_launch_command(
        self,
        url: str,
        *,
        title: str = "",
        extra_args: Sequence[str] = (),
    ) -> tuple[str, ...]:
        """Build a browser launch command without executing it."""

    def require_executable_path(self) -> str:
        """Return the configured browser executable path or raise."""

        if self.executable_path is None:
            raise BrowserError(f"{self.name} executable path is required.")
        return self.executable_path

    def _platform_info(self, platform_info: PlatformInfo | None) -> PlatformInfo:
        return platform_info or PlatformDetector().detect()

    def _find_by_names(self, names: Sequence[str]) -> str | None:
        for name in names:
            found = self.which_func(name)
            if found:
                return str(found)
        return None

    def _find_by_paths(self, paths: Sequence[Path]) -> str | None:
        for path in paths:
            if self.path_exists_func(path):
                return str(path)
        return None
