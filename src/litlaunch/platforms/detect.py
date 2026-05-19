"""Platform and runtime capability detection."""

from __future__ import annotations

import platform
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum


class OperatingSystem(str, Enum):
    """Normalized operating-system values."""

    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    UNKNOWN = "unknown"


class Architecture(str, Enum):
    """Normalized CPU architecture values."""

    X86 = "x86"
    X64 = "x64"
    ARM64 = "arm64"
    ARM = "arm"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PlatformInfo:
    """Detected platform and LitLaunch launch-capability metadata."""

    os: OperatingSystem
    architecture: Architecture
    python_version: str
    python_executable: str
    machine: str
    system: str
    release: str
    is_windows: bool
    is_macos: bool
    is_linux: bool
    supports_chromium_app_mode: bool
    supports_window_monitoring: bool
    supports_default_browser_open: bool
    notes: tuple[str, ...]

    def summary(self) -> str:
        """Return a concise deterministic platform summary."""

        return (
            f"{_display_os(self.os)} {self.architecture.value} / "
            f"Python {self.python_version}"
        )

    def as_dict(self) -> dict[str, object]:
        """Return stable diagnostics data."""

        return {
            "os": self.os.value,
            "architecture": self.architecture.value,
            "python_version": self.python_version,
            "python_executable": self.python_executable,
            "machine": self.machine,
            "system": self.system,
            "release": self.release,
            "is_windows": self.is_windows,
            "is_macos": self.is_macos,
            "is_linux": self.is_linux,
            "supports_chromium_app_mode": self.supports_chromium_app_mode,
            "supports_window_monitoring": self.supports_window_monitoring,
            "supports_default_browser_open": self.supports_default_browser_open,
            "notes": self.notes,
        }


class PlatformDetector:
    """Detect normalized platform capabilities using injectable providers."""

    def __init__(
        self,
        *,
        system_func: Callable[[], str] = platform.system,
        machine_func: Callable[[], str] = platform.machine,
        release_func: Callable[[], str] = platform.release,
        python_version_func: Callable[[], str] = platform.python_version,
        executable_provider: Callable[[], str] = lambda: sys.executable,
    ) -> None:
        self.system_func = system_func
        self.machine_func = machine_func
        self.release_func = release_func
        self.python_version_func = python_version_func
        self.executable_provider = executable_provider

    def detect(self) -> PlatformInfo:
        """Return normalized platform information and capability flags."""

        system = str(self.system_func() or "")
        machine = str(self.machine_func() or "")
        release = str(self.release_func() or "")
        python_version = str(self.python_version_func() or "")
        python_executable = str(self.executable_provider() or "")

        os_name = normalize_os(system)
        architecture = normalize_architecture(machine)
        notes = _build_notes(os_name, architecture)

        is_windows = os_name == OperatingSystem.WINDOWS
        is_macos = os_name == OperatingSystem.MACOS
        is_linux = os_name == OperatingSystem.LINUX
        is_known_desktop = is_windows or is_macos or is_linux

        return PlatformInfo(
            os=os_name,
            architecture=architecture,
            python_version=python_version,
            python_executable=python_executable,
            machine=machine,
            system=system,
            release=release,
            is_windows=is_windows,
            is_macos=is_macos,
            is_linux=is_linux,
            supports_chromium_app_mode=is_known_desktop,
            supports_window_monitoring=is_windows,
            supports_default_browser_open=is_known_desktop,
            notes=notes,
        )


def normalize_os(system_name: str) -> OperatingSystem:
    """Normalize platform.system() values."""

    normalized = system_name.strip().lower()
    if normalized == "windows":
        return OperatingSystem.WINDOWS
    if normalized == "darwin":
        return OperatingSystem.MACOS
    if normalized == "linux":
        return OperatingSystem.LINUX
    return OperatingSystem.UNKNOWN


def normalize_architecture(machine_name: str) -> Architecture:
    """Normalize platform.machine() values."""

    normalized = machine_name.strip().lower()
    if normalized in {"amd64", "x86_64"}:
        return Architecture.X64
    if normalized in {"arm64", "aarch64"}:
        return Architecture.ARM64
    if normalized in {"i386", "i686", "x86"}:
        return Architecture.X86
    if normalized.startswith("arm"):
        return Architecture.ARM
    return Architecture.UNKNOWN


def _build_notes(
    os_name: OperatingSystem,
    architecture: Architecture,
) -> tuple[str, ...]:
    notes: list[str] = []
    if os_name == OperatingSystem.UNKNOWN:
        notes.append("Unsupported or unknown operating system.")
    if architecture == Architecture.UNKNOWN:
        notes.append("Unknown CPU architecture.")
    if os_name == OperatingSystem.WINDOWS:
        notes.append("Window monitoring capability is currently Windows-first.")
    return tuple(notes)


def _display_os(os_name: OperatingSystem) -> str:
    if os_name == OperatingSystem.WINDOWS:
        return "Windows"
    if os_name == OperatingSystem.MACOS:
        return "macOS"
    if os_name == OperatingSystem.LINUX:
        return "Linux"
    return "Unknown"
