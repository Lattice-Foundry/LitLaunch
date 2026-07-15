"""Private immutable browser-process launch authority and Windows tree tracking."""

from __future__ import annotations

import ctypes
import math
import os
import secrets
from collections import defaultdict, deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from litlaunch.artifacts import is_litlaunch_owned
from litlaunch.browsers import BrowserKind

try:
    from ctypes import wintypes
except ImportError:  # pragma: no cover - non-Windows import safety.
    wintypes = None  # type: ignore[assignment]

TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MAX_WINDOWS_PROCESS_RECORDS = 4096
MAX_BROWSER_DESCENDANTS = 256
MAX_BROWSER_PROCESS_DEPTH = 12
MAX_PROCESS_IMAGE_CHARS = 32768


class BrowserAuthorityError(RuntimeError):
    """Raised when private browser authority metadata is malformed."""


class BrowserLaunchStrategy(str, Enum):
    """Private process-authority launch strategies."""

    DIRECT = "direct"
    WINDOWS_SHORTCUT = "windows_shortcut"


class BrowserProcessTreeStatus(str, Enum):
    """Fail-closed process-tree classifications."""

    ACTIVE = "active"
    ROOT_EXITED = "root_exited"
    LOST = "lost"
    PID_REUSED = "pid_reused"
    UNAVAILABLE = "unavailable"
    BOUNDED = "bounded"


@dataclass(frozen=True)
class BrowserLaunchAuthority:
    """One launch-bound, non-owning browser root process identity."""

    launch_id: str
    root_process_id: int
    root_creation_time_100ns: int
    browser_kind: BrowserKind
    executable_path: Path
    managed_profile_dir: Path
    launch_strategy: BrowserLaunchStrategy
    launched_at_monotonic: float

    def __post_init__(self) -> None:
        launch_id = str(self.launch_id).strip()
        if not launch_id or len(launch_id) > 256:
            raise BrowserAuthorityError("Browser launch authority ID is invalid.")
        object.__setattr__(self, "launch_id", launch_id)
        if (
            isinstance(self.root_process_id, bool)
            or not isinstance(self.root_process_id, int)
            or self.root_process_id <= 0
        ):
            raise BrowserAuthorityError("Browser root process ID is invalid.")
        if (
            isinstance(self.root_creation_time_100ns, bool)
            or not isinstance(self.root_creation_time_100ns, int)
            or self.root_creation_time_100ns <= 0
        ):
            raise BrowserAuthorityError("Browser root creation time is invalid.")
        if self.browser_kind not in {BrowserKind.EDGE, BrowserKind.CHROME}:
            raise BrowserAuthorityError("Browser authority requires Edge or Chrome.")
        executable = Path(self.executable_path)
        profile = Path(self.managed_profile_dir)
        if not str(executable).strip() or not str(profile).strip():
            raise BrowserAuthorityError("Browser authority paths are invalid.")
        object.__setattr__(self, "executable_path", executable)
        object.__setattr__(self, "managed_profile_dir", profile)
        launched_at = _finite_number(self.launched_at_monotonic)
        if launched_at < 0:
            raise BrowserAuthorityError("Browser launch time is invalid.")
        object.__setattr__(self, "launched_at_monotonic", launched_at)


@dataclass(frozen=True)
class WindowsProcessRecord:
    """One bounded process snapshot record used only for authority checks."""

    process_id: int
    parent_process_id: int
    creation_time_100ns: int | None
    executable_path: Path | None


@dataclass(frozen=True)
class WindowsProcessCapture:
    """One immutable process table capture with explicit truncation state."""

    records: tuple[WindowsProcessRecord, ...]
    truncated: bool = False


class WindowsProcessProvider(Protocol):
    """Private testable Windows process observation seam."""

    def capture(self) -> WindowsProcessCapture:
        """Capture a bounded local process table."""


@dataclass(frozen=True)
class BrowserProcessTreeSnapshot:
    """One launch-root and descendant authority observation."""

    status: BrowserProcessTreeStatus
    reason: str
    records: tuple[WindowsProcessRecord, ...] = ()
    browser_process_ids: frozenset[int] = frozenset()

    @property
    def active(self) -> bool:
        """Return whether exact browser ancestry remains usable."""

        return self.status in {
            BrowserProcessTreeStatus.ACTIVE,
            BrowserProcessTreeStatus.ROOT_EXITED,
        }


class WindowsProcessSnapshotProvider:
    """Capture process ancestry, image paths, and creation times through Win32."""

    is_windows = os.name == "nt"

    def __init__(self, *, max_records: int = MAX_WINDOWS_PROCESS_RECORDS) -> None:
        if max_records < 1:
            raise ValueError("Windows process snapshot bound must be positive.")
        self.max_records = max_records

    def capture(self) -> WindowsProcessCapture:
        if not self.is_windows or wintypes is None:
            raise BrowserAuthorityError(
                "Windows process authority is unavailable on this platform."
            )
        win_dll = getattr(ctypes, "WinDLL", None)
        if win_dll is None:
            raise BrowserAuthorityError("Windows process APIs are unavailable.")
        kernel32 = win_dll("kernel32", use_last_error=True)
        entries, truncated = _capture_process_entries(kernel32, self.max_records)
        records = tuple(
            _enrich_process_entry(kernel32, process_id, parent_process_id)
            for process_id, parent_process_id in entries
        )
        return WindowsProcessCapture(records, truncated)


class BrowserProcessTreeTracker:
    """Resolve only creation-time-valid descendants of one exact browser root."""

    def __init__(
        self,
        provider: WindowsProcessProvider | None = None,
        *,
        max_descendants: int = MAX_BROWSER_DESCENDANTS,
        max_depth: int = MAX_BROWSER_PROCESS_DEPTH,
    ) -> None:
        if max_descendants < 1 or max_depth < 1:
            raise ValueError("Browser process traversal bounds must be positive.")
        self.provider = provider or WindowsProcessSnapshotProvider()
        self.max_descendants = max_descendants
        self.max_depth = max_depth

    def capture(
        self,
        authority: BrowserLaunchAuthority,
    ) -> BrowserProcessTreeSnapshot:
        """Capture one bounded, PID-reuse-resistant launch process tree."""

        try:
            capture = self.provider.capture()
        except Exception:
            return BrowserProcessTreeSnapshot(
                BrowserProcessTreeStatus.UNAVAILABLE,
                "Windows process-tree capture failed.",
            )
        if capture.truncated:
            return BrowserProcessTreeSnapshot(
                BrowserProcessTreeStatus.BOUNDED,
                "Windows process table exceeded the authority capture bound.",
            )

        by_pid = {record.process_id: record for record in capture.records}
        root = by_pid.get(authority.root_process_id)
        if root is not None:
            if root.creation_time_100ns is None or root.executable_path is None:
                return BrowserProcessTreeSnapshot(
                    BrowserProcessTreeStatus.UNAVAILABLE,
                    "Browser root process identity could not be revalidated.",
                )
            if (
                root.creation_time_100ns != authority.root_creation_time_100ns
                or not _same_executable(
                    root.executable_path,
                    authority.executable_path,
                )
            ):
                return BrowserProcessTreeSnapshot(
                    BrowserProcessTreeStatus.PID_REUSED,
                    "Browser root PID no longer matches its creation-time identity.",
                )

        children: dict[int, list[WindowsProcessRecord]] = defaultdict(list)
        for record in capture.records:
            children[record.parent_process_id].append(record)
        selected: list[WindowsProcessRecord] = []
        if root is not None:
            selected.append(root)
        queue: deque[tuple[int, int]] = deque([(authority.root_process_id, 0)])
        visited = {authority.root_process_id}
        bounded = False
        while queue:
            parent_process_id, depth = queue.popleft()
            if depth >= self.max_depth:
                if children.get(parent_process_id):
                    bounded = True
                continue
            for child in children.get(parent_process_id, ()):
                if child.process_id in visited:
                    continue
                visited.add(child.process_id)
                if (
                    child.creation_time_100ns is None
                    or child.creation_time_100ns < authority.root_creation_time_100ns
                ):
                    continue
                selected.append(child)
                if len(selected) > self.max_descendants:
                    bounded = True
                    break
                queue.append((child.process_id, depth + 1))
            if bounded:
                break
        if bounded:
            return BrowserProcessTreeSnapshot(
                BrowserProcessTreeStatus.BOUNDED,
                "Browser descendant traversal exceeded its safety bound.",
            )

        browser_pids = frozenset(
            record.process_id
            for record in selected
            if record.creation_time_100ns is not None
            and _same_executable(record.executable_path, authority.executable_path)
        )
        if not browser_pids:
            return BrowserProcessTreeSnapshot(
                BrowserProcessTreeStatus.LOST,
                "No creation-time-valid browser root or descendant remains.",
            )
        status = (
            BrowserProcessTreeStatus.ACTIVE
            if root is not None
            else BrowserProcessTreeStatus.ROOT_EXITED
        )
        reason = (
            "Exact browser root and descendant authority retained."
            if root is not None
            else "Browser root exited; exact descendant authority retained."
        )
        return BrowserProcessTreeSnapshot(
            status,
            reason,
            tuple(selected),
            browser_pids,
        )


def create_browser_launch_authority(
    *,
    root_process_id: int,
    browser_kind: BrowserKind,
    executable_path: str | Path,
    command: Sequence[str],
    launch_strategy: BrowserLaunchStrategy,
    launched_at_monotonic: float,
    root_creation_time_100ns: int | None = None,
    root_record_provider: Callable[[int], WindowsProcessRecord | None] | None = None,
    launch_id: str | None = None,
) -> BrowserLaunchAuthority | None:
    """Create authority only for a LitLaunch-owned managed Chromium profile."""

    if browser_kind not in {BrowserKind.EDGE, BrowserKind.CHROME}:
        return None
    profile = _managed_profile_from_command(command)
    if profile is None or not is_litlaunch_owned(profile):
        return None
    executable = Path(executable_path)
    creation_time = root_creation_time_100ns
    if creation_time is None:
        provider = root_record_provider or query_windows_process_record
        record = provider(root_process_id)
        if record is None or not _same_executable(
            record.executable_path,
            executable,
        ):
            return None
        creation_time = record.creation_time_100ns
    if creation_time is None or creation_time <= 0:
        return None
    return BrowserLaunchAuthority(
        launch_id=launch_id or secrets.token_urlsafe(18),
        root_process_id=root_process_id,
        root_creation_time_100ns=creation_time,
        browser_kind=browser_kind,
        executable_path=executable,
        managed_profile_dir=profile,
        launch_strategy=launch_strategy,
        launched_at_monotonic=launched_at_monotonic,
    )


def query_windows_process_record(process_id: int) -> WindowsProcessRecord | None:
    """Query one process without retaining an OS handle."""

    if os.name != "nt" or wintypes is None:
        return None
    win_dll = getattr(ctypes, "WinDLL", None)
    if win_dll is None:
        return None
    kernel32 = win_dll("kernel32", use_last_error=True)
    return _enrich_process_entry(kernel32, process_id, 0)


def _managed_profile_from_command(command: Sequence[str]) -> Path | None:
    prefix = "--user-data-dir="
    for argument in command:
        value = str(argument).strip()
        if value.casefold().startswith(prefix):
            profile = value.split("=", 1)[1].strip().strip('"')
            return Path(profile) if profile else None
    return None


def _same_executable(observed: Path | None, expected: Path) -> bool:
    if observed is None:
        return False
    return os.path.normcase(os.path.abspath(str(observed))) == os.path.normcase(
        os.path.abspath(str(expected))
    )


def _finite_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BrowserAuthorityError("Browser launch time must be finite.")
    result = float(value)
    if not math.isfinite(result):
        raise BrowserAuthorityError("Browser launch time must be finite.")
    return result


def _process_entry_type() -> type[ctypes.Structure]:
    assert wintypes is not None

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    return ProcessEntry32W


def _capture_process_entries(
    kernel32: Any,
    max_records: int,
) -> tuple[tuple[tuple[int, int], ...], bool]:
    assert wintypes is not None
    entry_type = _process_entry_type()
    create_snapshot = kernel32.CreateToolhelp32Snapshot
    create_snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    create_snapshot.restype = wintypes.HANDLE
    snapshot = create_snapshot(TH32CS_SNAPPROCESS, 0)
    invalid_handle = ctypes.c_void_p(-1).value
    if not snapshot or int(snapshot) == invalid_handle:
        raise BrowserAuthorityError("Could not capture Windows process table.")
    try:
        first = kernel32.Process32FirstW
        next_entry = kernel32.Process32NextW
        first.argtypes = [wintypes.HANDLE, ctypes.POINTER(entry_type)]
        next_entry.argtypes = [wintypes.HANDLE, ctypes.POINTER(entry_type)]
        first.restype = wintypes.BOOL
        next_entry.restype = wintypes.BOOL
        entry = entry_type()
        entry.dwSize = ctypes.sizeof(entry_type)
        if not first(snapshot, ctypes.byref(entry)):
            return (), False
        records: list[tuple[int, int]] = []
        truncated = False
        while True:
            if len(records) >= max_records:
                truncated = True
                break
            records.append((int(entry.th32ProcessID), int(entry.th32ParentProcessID)))
            if not next_entry(snapshot, ctypes.byref(entry)):
                break
        return tuple(records), truncated
    finally:
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL
        close_handle(snapshot)


def _enrich_process_entry(
    kernel32: Any,
    process_id: int,
    parent_process_id: int,
) -> WindowsProcessRecord:
    assert wintypes is not None
    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    handle = open_process(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
    if not handle:
        return WindowsProcessRecord(process_id, parent_process_id, None, None)
    try:
        creation_time = _creation_time_from_handle(kernel32, handle)
        executable_path = _image_path_from_handle(kernel32, handle)
        return WindowsProcessRecord(
            process_id,
            parent_process_id,
            creation_time,
            executable_path,
        )
    finally:
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL
        close_handle(handle)


def _creation_time_from_handle(kernel32: Any, handle: object) -> int | None:
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
        handle,
        ctypes.byref(creation),
        ctypes.byref(exit_time),
        ctypes.byref(kernel_time),
        ctypes.byref(user_time),
    ):
        return None
    value = (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
    return value if value > 0 else None


def _image_path_from_handle(kernel32: Any, handle: object) -> Path | None:
    assert wintypes is not None
    buffer = ctypes.create_unicode_buffer(MAX_PROCESS_IMAGE_CHARS)
    size = wintypes.DWORD(len(buffer))
    query = kernel32.QueryFullProcessImageNameW
    query.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    query.restype = wintypes.BOOL
    if not query(handle, 0, buffer, ctypes.byref(size)):
        return None
    value = buffer.value[: int(size.value)]
    return Path(value) if value else None
