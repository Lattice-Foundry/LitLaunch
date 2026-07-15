"""Private Windows shell activation that can retain launch process identity."""

from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from ctypes import wintypes
except ImportError:  # pragma: no cover - non-Windows import safety.
    wintypes = None  # type: ignore[assignment]

SEE_MASK_NOCLOSEPROCESS = 0x00000040
SEE_MASK_NOASYNC = 0x00000100
SEE_MASK_FLAG_NO_UI = 0x00000400
SEE_MASK_UNICODE = 0x00004000
SW_SHOWNORMAL = 1


class WindowsShellLaunchError(RuntimeError):
    """Raised when Windows cannot activate the requested shell item."""


@dataclass(frozen=True)
class WindowsShellProcess:
    """Process identity extracted from a short-lived ShellExecute handle."""

    process_id: int
    creation_time_100ns: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.process_id, bool)
            or not isinstance(self.process_id, int)
            or self.process_id <= 0
        ):
            raise WindowsShellLaunchError("Shell process ID is invalid.")
        if (
            isinstance(self.creation_time_100ns, bool)
            or not isinstance(self.creation_time_100ns, int)
            or self.creation_time_100ns <= 0
        ):
            raise WindowsShellLaunchError("Shell process creation time is invalid.")


def open_windows_shortcut_with_process(path: Path) -> WindowsShellProcess | None:
    """Open one shortcut and return exact process identity when Windows supplies it."""

    if os.name != "nt" or wintypes is None:
        raise WindowsShellLaunchError(
            "Windows shortcut shell activation is unavailable on this platform."
        )
    shortcut = Path(path)
    if shortcut.suffix.casefold() != ".lnk" or not shortcut.is_file():
        raise WindowsShellLaunchError("Windows shortcut path is invalid or missing.")

    win_dll = getattr(ctypes, "WinDLL", None)
    if win_dll is None:
        raise WindowsShellLaunchError("Windows shell APIs are unavailable.")
    shell32 = win_dll("shell32", use_last_error=True)
    kernel32 = win_dll("kernel32", use_last_error=True)
    info_type = _shell_execute_info_type()
    info = info_type()
    info.cbSize = ctypes.sizeof(info_type)
    info.fMask = (
        SEE_MASK_NOCLOSEPROCESS
        | SEE_MASK_NOASYNC
        | SEE_MASK_FLAG_NO_UI
        | SEE_MASK_UNICODE
    )
    info.lpVerb = "open"
    info.lpFile = str(shortcut)
    info.nShow = SW_SHOWNORMAL

    shell_execute = shell32.ShellExecuteExW
    shell_execute.argtypes = [ctypes.POINTER(info_type)]
    shell_execute.restype = wintypes.BOOL
    if not shell_execute(ctypes.byref(info)):
        error = ctypes.get_last_error()
        raise WindowsShellLaunchError(
            f"Windows shortcut shell activation failed with error {error}."
        )

    process_handle = info.hProcess
    if not process_handle:
        return None
    try:
        process_id = _process_id_from_handle(kernel32, process_handle)
        creation_time = _creation_time_from_handle(kernel32, process_handle)
        if process_id is None or creation_time is None:
            return None
        return WindowsShellProcess(process_id, creation_time)
    finally:
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL
        close_handle(process_handle)


def _shell_execute_info_type() -> type[ctypes.Structure]:
    assert wintypes is not None

    class ShellExecuteInfoW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", ctypes.c_ulong),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", wintypes.LPVOID),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hIconOrMonitor", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    return ShellExecuteInfoW


def _process_id_from_handle(kernel32: Any, process_handle: object) -> int | None:
    assert wintypes is not None
    get_process_id = kernel32.GetProcessId
    get_process_id.argtypes = [wintypes.HANDLE]
    get_process_id.restype = wintypes.DWORD
    process_id = int(get_process_id(process_handle))
    return process_id if process_id > 0 else None


def _creation_time_from_handle(kernel32: Any, process_handle: object) -> int | None:
    assert wintypes is not None
    creation = wintypes.FILETIME()
    exit_time = wintypes.FILETIME()
    kernel_time = wintypes.FILETIME()
    user_time = wintypes.FILETIME()
    get_process_times = kernel32.GetProcessTimes
    get_process_times.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    get_process_times.restype = wintypes.BOOL
    if not get_process_times(
        process_handle,
        ctypes.byref(creation),
        ctypes.byref(exit_time),
        ctypes.byref(kernel_time),
        ctypes.byref(user_time),
    ):
        return None
    value = (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
    return value if value > 0 else None
