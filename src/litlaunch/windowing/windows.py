"""Windows Chromium window capture using stable Win32 APIs."""

from __future__ import annotations

import ctypes
import time
from collections.abc import Callable, Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any

from litlaunch._protocols import ClockProvider
from litlaunch.browsers import BrowserKind
from litlaunch.platforms import PlatformDetector, PlatformInfo
from litlaunch.windowing.base import WindowInfo, WindowTarget
from litlaunch.windowing.noop import NoopWindowMonitor
from litlaunch.windowing.polling import PollingWindowMonitor

_wintypes: Any
try:
    from ctypes import wintypes as _wintypes
except ImportError:  # pragma: no cover - exercised on non-Windows hosts.
    _wintypes = None

wintypes: Any = _wintypes

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
WM_SETICON = 0x0080
ICON_SMALL = 0
ICON_BIG = 1
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010

_WinDLL = getattr(ctypes, "WinDLL", None)


class WindowsWindowProvider:
    """Capture visible top-level Windows desktop windows.

    This provider uses stable Win32 APIs available on Windows 10 and Windows 11:
    EnumWindows, IsWindowVisible, GetWindowTextW, GetClassNameW,
    GetWindowThreadProcessId, OpenProcess, QueryFullProcessImageNameW, and
    CloseHandle. It never controls, closes, or owns windows or processes.
    """

    def __init__(
        self,
        *,
        user32: object | None = None,
        kernel32: object | None = None,
        is_windows: bool | None = None,
        process_name_provider: Callable[[int], str | None] | None = None,
    ) -> None:
        self.is_windows = _is_windows() if is_windows is None else bool(is_windows)
        self.process_name_provider = process_name_provider
        self.user32: Any | None
        self.kernel32: Any | None
        if self.is_windows:
            self.user32 = user32 or _load_windows_dll("user32")
            self.kernel32 = kernel32 or self._load_kernel32()
        else:
            self.user32 = user32
            self.kernel32 = kernel32

    def capture(self, target: WindowTarget | None = None) -> tuple[WindowInfo, ...]:
        """Return visible top-level windows.

        The target parameter is accepted for compatibility with the generic
        window capture protocol; Windows enumeration itself is target-agnostic.
        """

        if not self.is_windows or self.user32 is None:
            return ()

        windows: list[WindowInfo] = []
        enum_proc = _enum_windows_proc(self._capture_window, windows)

        try:
            self.user32.EnumWindows(enum_proc, 0)
        except (AttributeError, OSError):
            return ()

        return tuple(windows)

    def _capture_window(self, hwnd: int, windows: list[WindowInfo]) -> bool:
        user32 = self.user32
        if user32 is None:
            return True
        try:
            if not user32.IsWindowVisible(hwnd):
                return True

            title = self._get_window_text(hwnd)
            class_name = self._get_class_name(hwnd)
            if not title and not class_name:
                return True

            pid = self._get_window_pid(hwnd)
            process_name = self._get_process_name(pid) if pid else None
            windows.append(
                WindowInfo(
                    handle=str(int(hwnd)),
                    title=title,
                    class_name=class_name,
                    pid=pid,
                    process_name=process_name,
                )
            )
        except (OSError, ValueError):
            return True
        return True

    def _get_window_text(self, hwnd: int) -> str:
        user32 = self.user32
        if user32 is None:
            return ""
        try:
            length = int(user32.GetWindowTextLengthW(hwnd))
        except AttributeError:
            length = 0
        buffer = ctypes.create_unicode_buffer(max(length + 1, 512))
        try:
            user32.GetWindowTextW(hwnd, buffer, len(buffer))
        except (AttributeError, OSError):
            return ""
        return buffer.value

    def _get_class_name(self, hwnd: int) -> str:
        user32 = self.user32
        if user32 is None:
            return ""
        buffer = ctypes.create_unicode_buffer(256)
        try:
            user32.GetClassNameW(hwnd, buffer, len(buffer))
        except (AttributeError, OSError):
            return ""
        return buffer.value

    def _get_window_pid(self, hwnd: int) -> int | None:
        user32 = self.user32
        if user32 is None:
            return None
        pid = _DWORD()
        try:
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        except (AttributeError, OSError):
            return None
        return int(pid.value) or None

    def _get_process_name(self, pid: int) -> str | None:
        if self.process_name_provider is not None:
            return self.process_name_provider(pid)
        if self.kernel32 is None:
            return None
        handle = None
        try:
            handle = self.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION,
                False,
                pid,
            )
            if not handle:
                return None

            buffer = ctypes.create_unicode_buffer(32768)
            size = _DWORD(len(buffer))
            ok = self.kernel32.QueryFullProcessImageNameW(
                handle,
                0,
                buffer,
                ctypes.byref(size),
            )
            if not ok:
                return None
            return _basename_without_extension(buffer.value)
        except (AttributeError, OSError):
            return None
        finally:
            if handle:
                with suppress(AttributeError, OSError):
                    self.kernel32.CloseHandle(handle)

    def _load_kernel32(self) -> Any | None:
        if self.process_name_provider is not None:
            return None
        return _load_windows_dll("kernel32")


class WindowsChromiumWindowMonitor(PollingWindowMonitor):
    """Polling monitor for Windows Chromium app-mode top-level windows."""

    def __init__(
        self,
        provider: WindowsWindowProvider | None = None,
        *,
        clock: ClockProvider = time,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.provider = provider or WindowsWindowProvider()
        super().__init__(
            self._capture_chromium_windows,
            clock=clock,
            sleeper=sleeper,
        )

    def _capture_chromium_windows(self, target: WindowTarget) -> Sequence[WindowInfo]:
        return tuple(
            window
            for window in self.provider.capture(target)
            if is_chromium_window(window, target.browser_kind)
        )


def create_window_monitor(
    platform_info: PlatformInfo | None = None,
    *,
    provider: WindowsWindowProvider | None = None,
    clock: ClockProvider = time,
    sleeper: Callable[[float], None] = time.sleep,
) -> WindowsChromiumWindowMonitor | NoopWindowMonitor:
    """Return the default window monitor for the current platform."""

    info = platform_info or PlatformDetector().detect()
    if info.is_windows and info.supports_window_monitoring:
        return WindowsChromiumWindowMonitor(
            provider=provider,
            clock=clock,
            sleeper=sleeper,
        )
    return NoopWindowMonitor()


def is_chromium_window(
    window: WindowInfo,
    browser_kind: BrowserKind | None = None,
) -> bool:
    """Return whether a captured window looks like Chromium/Edge/Chrome."""

    class_name = window.class_name.strip()
    process_name = _normalize_process_name(window.process_name or "")

    class_matches = class_name.startswith("Chrome_WidgetWin")
    process_matches = _process_name_matches_chromium(process_name, browser_kind)
    return class_matches or process_matches


def apply_windows_window_icon(
    handle: str | int,
    icon_path: str | Path,
    *,
    user32: object | None = None,
    is_windows: bool | None = None,
) -> bool:
    """Best-effort Win32 icon override for one already-created window."""

    if not (_is_windows() if is_windows is None else is_windows):
        return False
    path = Path(icon_path)
    if path.suffix.lower() != ".ico" or not path.is_file():
        return False
    resolved_user32: Any = user32 or _load_windows_dll("user32")
    if resolved_user32 is None:
        return False
    try:
        hwnd = int(handle)
    except (TypeError, ValueError):
        return False

    applied = False
    for icon_type, size in ((ICON_SMALL, 16), (ICON_BIG, 32)):
        try:
            icon = resolved_user32.LoadImageW(
                None,
                str(path),
                IMAGE_ICON,
                size,
                size,
                LR_LOADFROMFILE,
            )
            if not icon:
                continue
            resolved_user32.SendMessageW(hwnd, WM_SETICON, icon_type, icon)
        except (AttributeError, OSError, TypeError, ValueError):
            continue
        applied = True
    return applied


def _process_name_matches_chromium(
    process_name: str,
    browser_kind: BrowserKind | None,
) -> bool:
    if not process_name:
        return False
    if browser_kind == BrowserKind.EDGE:
        return process_name in {"msedge", "microsoft-edge", "microsoft-edge-stable"}
    if browser_kind == BrowserKind.CHROME:
        return process_name in {
            "chrome",
            "google-chrome",
            "google-chrome-stable",
            "chromium",
            "chromium-browser",
        }
    return process_name in {
        "chrome",
        "chromium",
        "chromium-browser",
        "google-chrome",
        "google-chrome-stable",
        "msedge",
        "microsoft-edge",
        "microsoft-edge-stable",
    }


def _normalize_process_name(process_name: str) -> str:
    normalized = process_name.strip().lower()
    if normalized.endswith(".exe"):
        return normalized[:-4]
    return normalized


def _basename_without_extension(path: str) -> str:
    normalized = path.replace("/", "\\").rsplit("\\", 1)[-1]
    if normalized.lower().endswith(".exe"):
        return normalized[:-4]
    return normalized


def _enum_windows_proc(
    callback: Callable[[int, list[WindowInfo]], bool],
    windows: list[WindowInfo],
) -> object:
    def wrapped(hwnd: int, lparam: int) -> bool:
        return bool(callback(int(hwnd), windows))

    if not hasattr(ctypes, "WINFUNCTYPE"):
        return wrapped

    prototype = ctypes.WINFUNCTYPE(_BOOL(), _HWND(), _LPARAM())
    return prototype(wrapped)


def _is_windows() -> bool:
    return _WinDLL is not None


def _load_windows_dll(name: str) -> Any | None:
    if _WinDLL is None:
        return None
    return _WinDLL(name, use_last_error=True)


def _DWORD(value: int = 0) -> Any:
    if wintypes is not None:
        return wintypes.DWORD(value)
    return ctypes.c_ulong(value)


def _BOOL() -> Any:
    if wintypes is not None:
        return wintypes.BOOL
    return ctypes.c_int


def _HWND() -> Any:
    if wintypes is not None:
        return wintypes.HWND
    return ctypes.c_void_p


def _LPARAM() -> Any:
    if wintypes is not None:
        return wintypes.LPARAM
    return ctypes.c_long
