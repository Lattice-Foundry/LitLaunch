"""Internal LL-HS0 authority and Windows geometry spike primitives.

This module is intentionally private and unsupported. It proves whether a future
host-sizing feature is viable without changing the observation-only window monitor.
"""

from __future__ import annotations

import ctypes
import math
import os
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Protocol

from litlaunch.browsers import BrowserKind
from litlaunch.windowing.base import WindowInfo, WindowTarget
from litlaunch.windowing.title_match import window_matches_browser_kind
from litlaunch.windowing.windows import WindowsWindowProvider

_wintypes: Any
try:
    from ctypes import wintypes as _wintypes
except ImportError:  # pragma: no cover - exercised on non-Windows hosts.
    _wintypes = None

wintypes: Any = _wintypes

BASE_DPI = 96
MIN_VIEWPORT_HEIGHT_CSS = 320
MAX_VIEWPORT_HEIGHT_CSS = 4096
MONITOR_DEFAULTTONEAREST = 2
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
SNAP_TOLERANCE_NATIVE = 4

_WinDLL = getattr(ctypes, "WinDLL", None)


class WindowAuthorityStatus(str, Enum):
    """Internal LL-HS0 authority classifications."""

    EXACT = "exact"
    NONE = "none"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class WindowAuthorityProbe:
    """Fail-closed authority result for one launch-associated app window."""

    status: WindowAuthorityStatus
    window: WindowInfo | None
    candidates: tuple[WindowInfo, ...]
    reason: str
    stable_polls: int = 0


@dataclass(frozen=True)
class NativeRect:
    """Native physical-pixel rectangle."""

    left: int
    top: int
    right: int
    bottom: int

    def __post_init__(self) -> None:
        if self.right < self.left or self.bottom < self.top:
            raise ValueError("native rectangle coordinates are invalid.")

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


class WindowGeometryState(str, Enum):
    """Window states relevant to the LL-HS0 mutation gate."""

    NORMAL = "normal"
    MINIMIZED = "minimized"
    MAXIMIZED = "maximized"
    FULLSCREEN = "fullscreen"
    SNAPPED = "snapped"


@dataclass(frozen=True)
class WindowGeometry:
    """One DPI-consistent native geometry observation."""

    handle: int
    outer: NativeRect
    client_width: int
    client_height: int
    dpi: int
    monitor_handle: int
    monitor: NativeRect
    work_area: NativeRect
    show_command: int
    state: WindowGeometryState


@dataclass(frozen=True)
class HeightResizePlan:
    """One bounded CSS-viewport to native-window height plan."""

    safe: bool
    reason: str
    current_viewport_height_css: float
    requested_viewport_height_css: float
    effective_viewport_height_css: float
    css_delta: float
    native_delta: int
    requested_outer_height: int
    target_outer_height: int
    target_outer_width: int
    expected_viewport_height_css: float
    clamp_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class GeometryApplyResult:
    """Result from the spike's single guarded native mutation."""

    applied: bool
    reason: str
    baseline: WindowGeometry
    pre_apply: WindowGeometry
    after: WindowGeometry | None
    plan: HeightResizePlan


class GeometryBackend(Protocol):
    """Private native geometry seam used by the spike and deterministic fakes."""

    def capture(self, handle: int) -> WindowGeometry:
        """Capture one physical-pixel window geometry snapshot."""

    def set_outer_size(self, handle: int, *, width: int, height: int) -> None:
        """Resize without moving, activating, or changing Z-order."""


class GeometryProbeError(RuntimeError):
    """Raised when stable native geometry cannot be established."""


def classify_window_authority(
    windows: Iterable[WindowInfo],
    *,
    baseline_handles: Iterable[str],
    browser_kind: BrowserKind,
    title_token: str,
    launch_pids: Iterable[int],
    is_windows: bool = True,
) -> WindowAuthorityProbe:
    """Classify exact authority without changing passive monitor behavior."""

    if not is_windows:
        return WindowAuthorityProbe(
            status=WindowAuthorityStatus.UNSUPPORTED,
            window=None,
            candidates=(),
            reason="Exact app-window authority is only probed on Windows.",
        )

    normalized_token = title_token.strip().casefold()
    if not normalized_token:
        return WindowAuthorityProbe(
            status=WindowAuthorityStatus.UNSUPPORTED,
            window=None,
            candidates=(),
            reason="A non-empty unique title token is required.",
        )

    baseline = {str(handle).strip() for handle in baseline_handles}
    owned_pids = {int(pid) for pid in launch_pids if int(pid) > 0}
    if not owned_pids:
        return WindowAuthorityProbe(
            status=WindowAuthorityStatus.UNSUPPORTED,
            window=None,
            candidates=(),
            reason="No launched browser process identity is available.",
        )

    new_windows = tuple(window for window in windows if window.handle not in baseline)
    chromium_windows = tuple(
        window
        for window in new_windows
        if window.class_name.startswith("Chrome_WidgetWin")
        and window_matches_browser_kind(window, browser_kind)
    )
    title_matches = tuple(
        window
        for window in chromium_windows
        if normalized_token in window.title.casefold()
    )
    candidates = tuple(
        window
        for window in title_matches
        if window.pid is not None and window.pid in owned_pids
    )

    if len(candidates) == 1:
        window = candidates[0]
        return WindowAuthorityProbe(
            status=WindowAuthorityStatus.EXACT,
            window=window,
            candidates=candidates,
            reason=(
                "Exactly one new Chromium app window matched the unique title "
                f"token, browser kind, and launched process tree: HWND {window.handle}."
            ),
            stable_polls=1,
        )
    if len(candidates) > 1:
        handles = ", ".join(window.handle for window in candidates)
        return WindowAuthorityProbe(
            status=WindowAuthorityStatus.AMBIGUOUS,
            window=None,
            candidates=candidates,
            reason=f"Multiple launch-associated app windows matched: {handles}.",
        )

    return WindowAuthorityProbe(
        status=WindowAuthorityStatus.NONE,
        window=None,
        candidates=(),
        reason=(
            "No exact app window matched. "
            f"new={len(new_windows)}, chromium={len(chromium_windows)}, "
            f"title={len(title_matches)}, launch_process=0."
        ),
    )


def wait_for_exact_window_authority(
    provider: WindowsWindowProvider,
    *,
    baseline_handles: Iterable[str],
    browser_kind: BrowserKind,
    title_token: str,
    launch_pid_provider: Callable[[], Iterable[int]],
    timeout_seconds: float = 10.0,
    poll_interval_seconds: float = 0.1,
    stable_poll_count: int = 3,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> WindowAuthorityProbe:
    """Wait for one exact candidate to remain unique across stable polls."""

    if timeout_seconds <= 0 or poll_interval_seconds <= 0:
        raise ValueError("authority timeouts and intervals must be positive.")
    if stable_poll_count < 1:
        raise ValueError("stable_poll_count must be at least one.")

    deadline = clock() + timeout_seconds
    target = WindowTarget(title_token)
    stable_handle: str | None = None
    stable_polls = 0
    last = WindowAuthorityProbe(
        WindowAuthorityStatus.NONE,
        None,
        (),
        "No authority observation has completed.",
    )

    while clock() <= deadline:
        last = classify_window_authority(
            provider.capture(target),
            baseline_handles=baseline_handles,
            browser_kind=browser_kind,
            title_token=title_token,
            launch_pids=launch_pid_provider(),
            is_windows=provider.is_windows,
        )
        if last.status == WindowAuthorityStatus.AMBIGUOUS:
            return last
        if last.status == WindowAuthorityStatus.UNSUPPORTED:
            return last
        if last.status == WindowAuthorityStatus.EXACT and last.window is not None:
            if last.window.handle == stable_handle:
                stable_polls += 1
            else:
                stable_handle = last.window.handle
                stable_polls = 1
            if stable_polls >= stable_poll_count:
                return replace(
                    last,
                    reason=f"{last.reason} Stable for {stable_polls} polls.",
                    stable_polls=stable_polls,
                )
        else:
            stable_handle = None
            stable_polls = 0
        sleeper(poll_interval_seconds)

    return replace(
        last,
        status=WindowAuthorityStatus.NONE,
        window=None,
        reason=f"Exact app-window authority was not established: {last.reason}",
        stable_polls=stable_polls,
    )


def plan_height_resize(
    geometry: WindowGeometry,
    *,
    current_viewport_height_css: float,
    desired_viewport_height_css: float,
    device_pixel_ratio: float,
    minimum_viewport_height_css: int = MIN_VIEWPORT_HEIGHT_CSS,
) -> HeightResizePlan:
    """Plan one height-only mutation using target-window effective DPI."""

    values = (
        current_viewport_height_css,
        desired_viewport_height_css,
        device_pixel_ratio,
    )
    if not all(math.isfinite(float(value)) for value in values):
        return _unsafe_plan(
            "Viewport values and device-pixel ratio must be finite.",
            current_viewport_height_css,
            desired_viewport_height_css,
            geometry,
        )
    if current_viewport_height_css <= 0 or desired_viewport_height_css <= 0:
        return _unsafe_plan(
            "Viewport heights must be positive.",
            current_viewport_height_css,
            desired_viewport_height_css,
            geometry,
        )
    if desired_viewport_height_css > MAX_VIEWPORT_HEIGHT_CSS:
        return _unsafe_plan(
            f"Desired viewport height exceeds {MAX_VIEWPORT_HEIGHT_CSS} CSS pixels.",
            current_viewport_height_css,
            desired_viewport_height_css,
            geometry,
        )
    if geometry.state != WindowGeometryState.NORMAL:
        return _unsafe_plan(
            f"Window state is unsuitable for resizing: {geometry.state.value}.",
            current_viewport_height_css,
            desired_viewport_height_css,
            geometry,
        )
    if geometry.dpi < BASE_DPI:
        return _unsafe_plan(
            f"Target-window DPI is invalid: {geometry.dpi}.",
            current_viewport_height_css,
            desired_viewport_height_css,
            geometry,
        )

    dpi_scale = geometry.dpi / BASE_DPI
    if abs(device_pixel_ratio - dpi_scale) > 0.05:
        return _unsafe_plan(
            "Browser devicePixelRatio is inconsistent with target-window DPI; "
            "browser zoom or DPI virtualization may be active.",
            current_viewport_height_css,
            desired_viewport_height_css,
            geometry,
        )
    if geometry.outer.top < geometry.work_area.top:
        return _unsafe_plan(
            "Window top is outside the current monitor work area.",
            current_viewport_height_css,
            desired_viewport_height_css,
            geometry,
        )

    clamp_reasons: list[str] = []
    effective_desired = max(
        float(minimum_viewport_height_css),
        float(desired_viewport_height_css),
    )
    if effective_desired != desired_viewport_height_css:
        clamp_reasons.append("minimum_viewport_height")

    css_delta = effective_desired - float(current_viewport_height_css)
    native_delta = round(css_delta * dpi_scale)
    requested_outer_height = geometry.outer.height + native_delta
    maximum_outer_height = geometry.work_area.bottom - geometry.outer.top
    if maximum_outer_height <= 0:
        return _unsafe_plan(
            "No usable work-area height remains below the current window top.",
            current_viewport_height_css,
            desired_viewport_height_css,
            geometry,
        )

    target_outer_height = min(requested_outer_height, maximum_outer_height)
    if target_outer_height != requested_outer_height:
        clamp_reasons.append("monitor_work_area")
    if target_outer_height <= 0:
        return _unsafe_plan(
            "Calculated native outer-window height is invalid.",
            current_viewport_height_css,
            desired_viewport_height_css,
            geometry,
        )

    applied_native_delta = target_outer_height - geometry.outer.height
    expected_viewport = (
        float(current_viewport_height_css) + applied_native_delta / dpi_scale
    )
    return HeightResizePlan(
        safe=True,
        reason=(
            "Height-only resize is safe for this snapshot."
            if not clamp_reasons
            else "Height-only resize is safe after bounded clamping."
        ),
        current_viewport_height_css=float(current_viewport_height_css),
        requested_viewport_height_css=float(desired_viewport_height_css),
        effective_viewport_height_css=effective_desired,
        css_delta=css_delta,
        native_delta=native_delta,
        requested_outer_height=requested_outer_height,
        target_outer_height=target_outer_height,
        target_outer_width=geometry.outer.width,
        expected_viewport_height_css=expected_viewport,
        clamp_reasons=tuple(clamp_reasons),
    )


def geometry_changed(
    baseline: WindowGeometry,
    current: WindowGeometry,
) -> bool:
    """Return whether user/system geometry changed before spike application."""

    return (
        baseline.handle != current.handle
        or baseline.outer != current.outer
        or baseline.client_width != current.client_width
        or baseline.client_height != current.client_height
        or baseline.dpi != current.dpi
        or baseline.monitor_handle != current.monitor_handle
        or baseline.monitor != current.monitor
        or baseline.work_area != current.work_area
        or baseline.show_command != current.show_command
        or baseline.state != current.state
    )


class HostSizingGeometryProbe:
    """Apply at most one guarded spike resize through a private native seam."""

    def __init__(self, backend: GeometryBackend) -> None:
        self.backend = backend

    def apply(
        self,
        *,
        handle: int,
        baseline: WindowGeometry,
        plan: HeightResizePlan,
    ) -> GeometryApplyResult:
        """Refuse stale snapshots, then apply one non-moving height mutation."""

        pre_apply = self.backend.capture(handle)
        if not plan.safe:
            return GeometryApplyResult(
                False,
                plan.reason,
                baseline,
                pre_apply,
                None,
                plan,
            )
        if geometry_changed(baseline, pre_apply):
            return GeometryApplyResult(
                False,
                "Window geometry changed after authority capture; refusing mutation.",
                baseline,
                pre_apply,
                None,
                plan,
            )
        if pre_apply.state != WindowGeometryState.NORMAL:
            return GeometryApplyResult(
                False,
                f"Window state changed to {pre_apply.state.value}; refusing mutation.",
                baseline,
                pre_apply,
                None,
                plan,
            )

        if plan.target_outer_height == pre_apply.outer.height:
            return GeometryApplyResult(
                False,
                "Window is already at the planned outer height.",
                baseline,
                pre_apply,
                pre_apply,
                plan,
            )

        self.backend.set_outer_size(
            handle,
            width=plan.target_outer_width,
            height=plan.target_outer_height,
        )
        after = self.backend.capture(handle)
        preserved = (
            after.outer.left == pre_apply.outer.left
            and after.outer.top == pre_apply.outer.top
            and after.outer.width == pre_apply.outer.width
        )
        height_matches = abs(after.outer.height - plan.target_outer_height) <= 1
        if not preserved or not height_matches:
            return GeometryApplyResult(
                False,
                "Native resize completed but post-apply geometry did not match "
                "the plan.",
                baseline,
                pre_apply,
                after,
                plan,
            )
        return GeometryApplyResult(
            True,
            "Applied one height-only resize with position, width, Z-order, and "
            "activation preserved.",
            baseline,
            pre_apply,
            after,
            plan,
        )


class WindowsGeometryBackend:
    """Private LL-HS0 Win32 geometry backend using thread-scoped DPI context."""

    def __init__(
        self,
        *,
        user32: object | None = None,
        is_windows: bool | None = None,
    ) -> None:
        self.is_windows = os.name == "nt" if is_windows is None else bool(is_windows)
        if self.is_windows:
            self.user32: Any = user32 or _load_windows_dll("user32")
        else:
            self.user32 = user32

    def capture(self, handle: int) -> WindowGeometry:
        """Capture physical coordinates without process-wide DPI changes."""

        if not self.is_windows or self.user32 is None:
            raise GeometryProbeError("Windows geometry probing is unavailable.")
        hwnd = _hwnd(handle)
        with _per_monitor_v2_thread_context(self.user32):
            outer_value = _RECT()
            client_value = _RECT()
            placement = _WINDOWPLACEMENT()
            placement.length = ctypes.sizeof(_WINDOWPLACEMENT)
            _require_call(self.user32.GetWindowRect(hwnd, ctypes.byref(outer_value)))
            _require_call(self.user32.GetClientRect(hwnd, ctypes.byref(client_value)))
            _require_call(self.user32.GetWindowPlacement(hwnd, ctypes.byref(placement)))
            dpi = int(self.user32.GetDpiForWindow(hwnd))
            if dpi <= 0:
                raise GeometryProbeError("GetDpiForWindow returned no DPI.")
            monitor_handle = self.user32.MonitorFromWindow(
                hwnd,
                MONITOR_DEFAULTTONEAREST,
            )
            monitor_id = _pointer_value(monitor_handle)
            if monitor_id == 0:
                raise GeometryProbeError("MonitorFromWindow returned no monitor.")
            monitor_info = _MONITORINFO()
            monitor_info.cbSize = ctypes.sizeof(_MONITORINFO)
            _require_call(
                self.user32.GetMonitorInfoW(
                    _handle(monitor_id),
                    ctypes.byref(monitor_info),
                )
            )
            minimized = bool(self.user32.IsIconic(hwnd))
            maximized = bool(self.user32.IsZoomed(hwnd))

        outer = _native_rect(outer_value)
        client = _native_rect(client_value)
        monitor = _native_rect(monitor_info.rcMonitor)
        work_area = _native_rect(monitor_info.rcWork)
        if minimized:
            state = WindowGeometryState.MINIMIZED
        elif maximized:
            state = WindowGeometryState.MAXIMIZED
        elif _rects_near(outer, monitor, tolerance=SNAP_TOLERANCE_NATIVE):
            state = WindowGeometryState.FULLSCREEN
        elif looks_snapped(outer, work_area, dpi=dpi):
            state = WindowGeometryState.SNAPPED
        else:
            state = WindowGeometryState.NORMAL

        return WindowGeometry(
            handle=int(handle),
            outer=outer,
            client_width=client.width,
            client_height=client.height,
            dpi=dpi,
            monitor_handle=monitor_id,
            monitor=monitor,
            work_area=work_area,
            show_command=int(placement.showCmd),
            state=state,
        )

    def set_outer_size(self, handle: int, *, width: int, height: int) -> None:
        """Use SetWindowPos without move, activation, or Z-order mutation."""

        if not self.is_windows or self.user32 is None:
            raise GeometryProbeError("Windows geometry probing is unavailable.")
        if width <= 0 or height <= 0:
            raise GeometryProbeError("Native target dimensions must be positive.")
        flags = SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOOWNERZORDER
        with _per_monitor_v2_thread_context(self.user32):
            _require_call(
                self.user32.SetWindowPos(
                    _hwnd(handle),
                    _handle(0),
                    0,
                    0,
                    int(width),
                    int(height),
                    flags,
                )
            )


def looks_snapped(outer: NativeRect, work_area: NativeRect, *, dpi: int) -> bool:
    """Conservatively identify common Windows half/third/quarter snap layouts."""

    tolerance = max(SNAP_TOLERANCE_NATIVE, round(dpi / 24))
    work_width = work_area.width
    work_height = work_area.height
    if work_width <= 0 or work_height <= 0:
        return False

    touches_horizontal_edge = _near(outer.left, work_area.left, tolerance) or _near(
        outer.right,
        work_area.right,
        tolerance,
    )
    touches_vertical_edge = _near(outer.top, work_area.top, tolerance) or _near(
        outer.bottom,
        work_area.bottom,
        tolerance,
    )
    full_height = _near(outer.top, work_area.top, tolerance) and _near(
        outer.bottom,
        work_area.bottom,
        tolerance,
    )
    full_width = _near(outer.left, work_area.left, tolerance) and _near(
        outer.right,
        work_area.right,
        tolerance,
    )
    width_ratio = outer.width / work_width
    height_ratio = outer.height / work_height
    common_width = any(
        abs(width_ratio - ratio) <= 0.03 for ratio in (1 / 3, 1 / 2, 2 / 3)
    )
    common_height = abs(height_ratio - 1 / 2) <= 0.03
    return (full_height and touches_horizontal_edge and common_width) or (
        full_width and touches_vertical_edge and common_height
    )


def _unsafe_plan(
    reason: str,
    current_viewport_height_css: float,
    desired_viewport_height_css: float,
    geometry: WindowGeometry,
) -> HeightResizePlan:
    return HeightResizePlan(
        safe=False,
        reason=reason,
        current_viewport_height_css=float(current_viewport_height_css),
        requested_viewport_height_css=float(desired_viewport_height_css),
        effective_viewport_height_css=float(desired_viewport_height_css),
        css_delta=0.0,
        native_delta=0,
        requested_outer_height=geometry.outer.height,
        target_outer_height=geometry.outer.height,
        target_outer_width=geometry.outer.width,
        expected_viewport_height_css=float(current_viewport_height_css),
    )


def _rects_near(first: NativeRect, second: NativeRect, *, tolerance: int) -> bool:
    return all(
        _near(left, right, tolerance)
        for left, right in zip(
            (first.left, first.top, first.right, first.bottom),
            (second.left, second.top, second.right, second.bottom),
            strict=True,
        )
    )


def _near(first: int, second: int, tolerance: int) -> bool:
    return abs(first - second) <= tolerance


@contextmanager
def _per_monitor_v2_thread_context(user32: Any) -> Iterator[None]:
    setter = getattr(user32, "SetThreadDpiAwarenessContext", None)
    if setter is None:
        raise GeometryProbeError(
            "SetThreadDpiAwarenessContext is unavailable; physical geometry is unsafe."
        )
    try:
        setter.argtypes = [ctypes.c_void_p]
        setter.restype = ctypes.c_void_p
    except AttributeError:
        pass
    target = ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
    previous = setter(target)
    if not previous:
        raise GeometryProbeError("Could not enter per-monitor-v2 thread DPI context.")
    try:
        yield
    finally:
        setter(previous)


def _native_rect(value: Any) -> NativeRect:
    return NativeRect(
        int(value.left),
        int(value.top),
        int(value.right),
        int(value.bottom),
    )


def _require_call(result: object) -> None:
    if not result:
        error = ctypes.get_last_error() if hasattr(ctypes, "get_last_error") else 0
        raise GeometryProbeError(f"Win32 geometry call failed with error {error}.")


def _pointer_value(value: object) -> int:
    raw_value: Any = getattr(value, "value", value)
    try:
        return int(raw_value or 0)
    except (TypeError, ValueError):
        return 0


def _hwnd(value: int) -> Any:
    if wintypes is not None:
        return wintypes.HWND(int(value))
    return ctypes.c_void_p(int(value))


def _handle(value: int) -> Any:
    if wintypes is not None:
        return wintypes.HANDLE(int(value))
    return ctypes.c_void_p(int(value))


def _load_windows_dll(name: str) -> Any | None:
    if _WinDLL is None:
        return None
    dll = _WinDLL(name, use_last_error=True)
    with suppress(AttributeError):
        dll.MonitorFromWindow.restype = ctypes.c_void_p
    return dll


_LONG = ctypes.c_long
_DWORD = ctypes.c_ulong
_UINT = ctypes.c_uint


class _POINT(ctypes.Structure):
    _fields_ = [("x", _LONG), ("y", _LONG)]


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", _LONG),
        ("top", _LONG),
        ("right", _LONG),
        ("bottom", _LONG),
    ]


class _WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [
        ("length", _UINT),
        ("flags", _UINT),
        ("showCmd", _UINT),
        ("ptMinPosition", _POINT),
        ("ptMaxPosition", _POINT),
        ("rcNormalPosition", _RECT),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", _DWORD),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", _DWORD),
    ]
