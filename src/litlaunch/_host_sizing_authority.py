"""Private production-shaped browser process and exact HWND eligibility gate."""

from __future__ import annotations

import math
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from litlaunch._browser_authority import (
    BrowserLaunchAuthority,
    BrowserProcessTreeSnapshot,
    BrowserProcessTreeTracker,
)
from litlaunch._host_sizing_geometry import (
    GeometryBackend,
    WindowAuthorityProbe,
    WindowAuthorityStatus,
    WindowGeometryState,
    WindowsGeometryBackend,
)
from litlaunch._host_sizing_window import (
    HostSizingWindowError,
    WindowAuthorityVerification,
    WindowSizingAuthority,
    WindowsWindowAuthorityVerifier,
    create_window_sizing_authority,
)
from litlaunch.artifacts import is_litlaunch_owned
from litlaunch.browsers import BrowserKind
from litlaunch.config import LaunchMode
from litlaunch.windowing import WindowInfo
from litlaunch.windowing.windows import WindowsWindowProvider

HOST_SIZING_AUTHORITY_TIMEOUT_SECONDS = 5.0
HOST_SIZING_AUTHORITY_POLL_SECONDS = 0.05
HOST_SIZING_AUTHORITY_STABLE_POLLS = 3


class PrivateHostSizingEligibilityStatus(str, Enum):
    """Internal fail-closed activation-gate outcomes."""

    ELIGIBLE = "eligible"
    DISABLED = "disabled"
    UNSUPPORTED = "unsupported"
    AUTHORITY_UNAVAILABLE = "authority_unavailable"
    NO_WINDOW = "no_window"
    AMBIGUOUS = "ambiguous"
    UNSTABLE = "unstable"
    UNSAFE_WINDOW = "unsafe_window"
    SHUT_DOWN = "shut_down"


@dataclass(frozen=True)
class HostSizingAuthorityCollectionConfig:
    """Private bounded exact-window collection timing."""

    timeout_seconds: float = HOST_SIZING_AUTHORITY_TIMEOUT_SECONDS
    poll_interval_seconds: float = HOST_SIZING_AUTHORITY_POLL_SECONDS
    stable_poll_count: int = HOST_SIZING_AUTHORITY_STABLE_POLLS

    def __post_init__(self) -> None:
        timeout = _positive_finite(self.timeout_seconds, "timeout")
        poll = _positive_finite(self.poll_interval_seconds, "poll interval")
        if poll > timeout:
            raise ValueError("Authority poll interval must not exceed its timeout.")
        if (
            isinstance(self.stable_poll_count, bool)
            or not isinstance(self.stable_poll_count, int)
            or self.stable_poll_count < 3
        ):
            raise ValueError("Exact window authority requires at least three polls.")
        object.__setattr__(self, "timeout_seconds", timeout)
        object.__setattr__(self, "poll_interval_seconds", poll)


@dataclass(frozen=True)
class PrivateHostSizingEligibility:
    """Credential-free result from the private activation gate."""

    status: PrivateHostSizingEligibilityStatus
    reason: str
    launch_authority: BrowserLaunchAuthority | None = None
    process_snapshot: BrowserProcessTreeSnapshot | None = None
    window_authority: WindowSizingAuthority | None = None

    @property
    def eligible(self) -> bool:
        """Return whether all private production prerequisites were proven."""

        return (
            self.status == PrivateHostSizingEligibilityStatus.ELIGIBLE
            and self.window_authority is not None
        )


class WindowCaptureProvider(Protocol):
    """Narrow top-level window observation seam."""

    def capture(self) -> Sequence[WindowInfo]:
        """Return current visible top-level windows."""


class BrowserAuthoritySession(Protocol):
    """Private RuntimeSession authority-retention shape."""

    def _browser_authority_snapshot(self) -> BrowserLaunchAuthority | None:
        """Return current immutable launch identity, or None after cleanup."""


class ProcessBoundWindowsWindowAuthorityVerifier:
    """Revalidate process ancestry and exact HWND identity around mutation."""

    def __init__(
        self,
        launch_authority: BrowserLaunchAuthority,
        *,
        process_tracker: BrowserProcessTreeTracker | None = None,
        window_provider: WindowCaptureProvider | None = None,
    ) -> None:
        self.launch_authority = launch_authority
        self.process_tracker = process_tracker or BrowserProcessTreeTracker()
        self.window_verifier = WindowsWindowAuthorityVerifier(window_provider)

    def verify(self, authority: WindowSizingAuthority) -> WindowAuthorityVerification:
        """Require the same launch, live ancestry, and exact Chromium HWND."""

        if authority.authority_id != self.launch_authority.launch_id:
            return WindowAuthorityVerification(
                False,
                "Window authority is bound to a different browser launch.",
            )
        process_snapshot = self.process_tracker.capture(self.launch_authority)
        if not process_snapshot.active:
            return WindowAuthorityVerification(False, process_snapshot.reason)
        if authority.process_id not in process_snapshot.browser_process_ids:
            return WindowAuthorityVerification(
                False,
                "Authorized HWND process is no longer in the exact browser tree.",
            )
        return self.window_verifier.verify(authority)


class PrivateHostSizingActivationGate:
    """Build exact mutation authority only after every private gate passes."""

    def __init__(
        self,
        *,
        process_tracker: BrowserProcessTreeTracker | None = None,
        window_provider: WindowCaptureProvider | None = None,
        geometry_backend: GeometryBackend | None = None,
        config: HostSizingAuthorityCollectionConfig | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], object] = time.sleep,
        is_windows: bool | None = None,
    ) -> None:
        self.process_tracker = process_tracker or BrowserProcessTreeTracker()
        self.window_provider = window_provider or WindowsWindowProvider()
        self.geometry_backend = geometry_backend or WindowsGeometryBackend()
        self.config = config or HostSizingAuthorityCollectionConfig()
        self.clock = clock
        self.sleeper = sleeper
        self.is_windows = os.name == "nt" if is_windows is None else is_windows

    def capture_baseline_handles(self) -> tuple[str, ...]:
        """Capture pre-launch HWNDs without retaining titles or process details."""

        if not self.is_windows:
            raise RuntimeError("Host-sizing HWND baselines require Windows.")
        return tuple(str(window.handle) for window in self.window_provider.capture())

    def collect_for_session(
        self,
        session: BrowserAuthoritySession,
        *,
        private_enabled: bool = False,
        mode: LaunchMode = LaunchMode.WEBAPP,
        baseline_handles: Sequence[str] = (),
    ) -> PrivateHostSizingEligibility:
        """Collect authority while requiring the session to retain the same launch."""

        authority = session._browser_authority_snapshot()
        return self.collect(
            authority,
            private_enabled=private_enabled,
            mode=mode,
            baseline_handles=baseline_handles,
            shutdown_requested=lambda: (
                session._browser_authority_snapshot() != authority
            ),
        )

    def collect(
        self,
        authority: BrowserLaunchAuthority | None,
        *,
        private_enabled: bool = False,
        mode: LaunchMode = LaunchMode.WEBAPP,
        baseline_handles: Sequence[str] = (),
        shutdown_requested: Callable[[], bool] = lambda: False,
    ) -> PrivateHostSizingEligibility:
        """Return exact authority or one internal fail-closed reason."""

        prerequisite = self._prerequisite_result(
            authority,
            private_enabled=private_enabled,
            mode=mode,
        )
        if prerequisite is not None:
            return prerequisite
        assert authority is not None

        baseline = frozenset(str(handle) for handle in baseline_handles)
        deadline = self.clock() + self.config.timeout_seconds
        candidate: WindowInfo | None = None
        stable_polls = 0
        last_process_snapshot: BrowserProcessTreeSnapshot | None = None
        observed_candidate = False
        while self.clock() <= deadline:
            if shutdown_requested():
                return PrivateHostSizingEligibility(
                    PrivateHostSizingEligibilityStatus.SHUT_DOWN,
                    "Runtime shutdown invalidated browser launch authority.",
                    authority,
                    last_process_snapshot,
                )
            process_snapshot = self.process_tracker.capture(authority)
            last_process_snapshot = process_snapshot
            if not process_snapshot.active:
                return PrivateHostSizingEligibility(
                    PrivateHostSizingEligibilityStatus.AUTHORITY_UNAVAILABLE,
                    process_snapshot.reason,
                    authority,
                    process_snapshot,
                )
            try:
                windows = tuple(self.window_provider.capture())
            except Exception:
                return PrivateHostSizingEligibility(
                    PrivateHostSizingEligibilityStatus.AUTHORITY_UNAVAILABLE,
                    "Top-level window capture failed.",
                    authority,
                    process_snapshot,
                )
            candidates = tuple(
                window
                for window in windows
                if _exact_window_candidate(
                    window,
                    authority,
                    process_snapshot,
                    baseline,
                )
            )
            if len(candidates) > 1:
                return PrivateHostSizingEligibility(
                    PrivateHostSizingEligibilityStatus.AMBIGUOUS,
                    "Multiple launch-associated Chromium app windows were observed.",
                    authority,
                    process_snapshot,
                )
            selected = candidates[0] if candidates else None
            if selected is None:
                candidate = None
                stable_polls = 0
            elif (
                candidate is not None
                and selected.handle == candidate.handle
                and selected.pid == candidate.pid
            ):
                stable_polls += 1
                observed_candidate = True
            else:
                candidate = selected
                stable_polls = 1
                observed_candidate = True
            if candidate is not None and stable_polls >= self.config.stable_poll_count:
                return self._promote(
                    authority,
                    process_snapshot,
                    candidate,
                    stable_polls,
                )
            self.sleeper(self.config.poll_interval_seconds)

        status = (
            PrivateHostSizingEligibilityStatus.UNSTABLE
            if observed_candidate
            else PrivateHostSizingEligibilityStatus.NO_WINDOW
        )
        reason = (
            "Launch-associated app window did not remain stable."
            if observed_candidate
            else "No launch-associated app window was observed."
        )
        return PrivateHostSizingEligibility(
            status,
            reason,
            authority,
            last_process_snapshot,
        )

    def _prerequisite_result(
        self,
        authority: BrowserLaunchAuthority | None,
        *,
        private_enabled: bool,
        mode: LaunchMode,
    ) -> PrivateHostSizingEligibility | None:
        if not private_enabled:
            return PrivateHostSizingEligibility(
                PrivateHostSizingEligibilityStatus.DISABLED,
                "Private host-sizing activation was not explicitly enabled.",
            )
        if not self.is_windows:
            return PrivateHostSizingEligibility(
                PrivateHostSizingEligibilityStatus.UNSUPPORTED,
                "Private host sizing requires Windows.",
            )
        if mode != LaunchMode.WEBAPP:
            return PrivateHostSizingEligibility(
                PrivateHostSizingEligibilityStatus.UNSUPPORTED,
                "Private host sizing requires Chromium app mode.",
            )
        if authority is None:
            return PrivateHostSizingEligibility(
                PrivateHostSizingEligibilityStatus.AUTHORITY_UNAVAILABLE,
                "No exact browser launch process authority was retained.",
            )
        if authority.browser_kind not in {BrowserKind.EDGE, BrowserKind.CHROME}:
            return PrivateHostSizingEligibility(
                PrivateHostSizingEligibilityStatus.UNSUPPORTED,
                "Private host sizing requires Edge or Chrome.",
                authority,
            )
        if not is_litlaunch_owned(authority.managed_profile_dir):
            return PrivateHostSizingEligibility(
                PrivateHostSizingEligibilityStatus.AUTHORITY_UNAVAILABLE,
                "Browser profile is not owned by this LitLaunch runtime.",
                authority,
            )
        return None

    def _promote(
        self,
        authority: BrowserLaunchAuthority,
        process_snapshot: BrowserProcessTreeSnapshot,
        candidate: WindowInfo,
        stable_polls: int,
    ) -> PrivateHostSizingEligibility:
        try:
            handle = int(candidate.handle)
            baseline = self.geometry_backend.capture(handle)
        except Exception:
            return PrivateHostSizingEligibility(
                PrivateHostSizingEligibilityStatus.UNSAFE_WINDOW,
                "Could not capture immutable baseline geometry.",
                authority,
                process_snapshot,
            )
        if baseline.state != WindowGeometryState.NORMAL:
            return PrivateHostSizingEligibility(
                PrivateHostSizingEligibilityStatus.UNSAFE_WINDOW,
                f"App window state is {baseline.state.value}, not normal.",
                authority,
                process_snapshot,
            )
        probe = WindowAuthorityProbe(
            status=WindowAuthorityStatus.EXACT,
            window=candidate,
            candidates=(candidate,),
            reason="Exact launch-process app window remained stable.",
            stable_polls=stable_polls,
        )
        try:
            window_authority = create_window_sizing_authority(
                authority_id=authority.launch_id,
                probe=probe,
                browser_kind=authority.browser_kind,
                launch_process_ids=process_snapshot.browser_process_ids,
                baseline=baseline,
                managed_profile=True,
                app_mode=True,
            )
        except HostSizingWindowError as exc:
            return PrivateHostSizingEligibility(
                PrivateHostSizingEligibilityStatus.UNSAFE_WINDOW,
                str(exc),
                authority,
                process_snapshot,
            )
        return PrivateHostSizingEligibility(
            PrivateHostSizingEligibilityStatus.ELIGIBLE,
            "Exact private host-sizing authority established.",
            authority,
            process_snapshot,
            window_authority,
        )


def _exact_window_candidate(
    window: WindowInfo,
    authority: BrowserLaunchAuthority,
    process_snapshot: BrowserProcessTreeSnapshot,
    baseline_handles: frozenset[str],
) -> bool:
    if window.handle in baseline_handles or window.pid is None:
        return False
    if window.pid not in process_snapshot.browser_process_ids:
        return False
    if not window.class_name.startswith("Chrome_WidgetWin"):
        return False
    process_name = str(window.process_name or "").casefold()
    if authority.browser_kind == BrowserKind.EDGE:
        return process_name in {"msedge", "msedge.exe"}
    return process_name in {"chrome", "chrome.exe"}


def _positive_finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Authority {label} must be a finite number.")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"Authority {label} must be positive and finite.")
    return result
