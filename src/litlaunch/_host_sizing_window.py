"""Private exact-authority Windows host-sizing mutation capability.

This module consumes policy-approved decisions for one exact immutable authority. It
does not discover launch authority, activate transport, or expose public controls.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from typing import Protocol

from litlaunch._host_sizing_geometry import (
    GeometryBackend,
    HeightResizePlan,
    WindowAuthorityProbe,
    WindowAuthorityStatus,
    WindowGeometry,
    WindowGeometryState,
    WindowsGeometryBackend,
    geometry_changed,
    plan_height_resize,
)
from litlaunch._host_sizing_policy import (
    HOST_SIZING_HARD_MAX_VIEWPORT_HEIGHT,
    HOST_SIZING_HARD_MIN_VIEWPORT_HEIGHT,
    HostSizingAction,
    HostSizingDecision,
    HostSizingPolicyState,
)
from litlaunch._host_sizing_transport import (
    HOST_SIZING_MAX_DEVICE_PIXEL_RATIO,
    HOST_SIZING_MIN_DEVICE_PIXEL_RATIO,
)
from litlaunch.browsers import BrowserKind
from litlaunch.windowing import WindowInfo
from litlaunch.windowing.title_match import window_matches_browser_kind
from litlaunch.windowing.windows import WindowsWindowProvider

MINIMUM_AUTHORITY_STABLE_POLLS = 3


class HostSizingWindowError(RuntimeError):
    """Raised when exact private mutation authority cannot be constructed."""


class HostSizingMutationStatus(str, Enum):
    """Outcomes from one guarded native mutation attempt."""

    APPLIED = "applied"
    NO_CHANGE = "no_change"
    REFUSED = "refused"
    FAILED = "failed"


class WindowSizingLifetime(str, Enum):
    """Internal authority lifetime for a native sizing capability."""

    ONE_SHOT = "one_shot"
    SESSION = "session"


@dataclass(frozen=True)
class WindowSizingAuthority:
    """Immutable proof inputs for one exact managed Chromium app window."""

    authority_id: str
    handle: int
    browser_kind: BrowserKind
    process_id: int
    launch_process_ids: frozenset[int]
    stable_polls: int
    baseline: WindowGeometry
    managed_profile: bool
    app_mode: bool

    def __post_init__(self) -> None:
        authority_id = str(self.authority_id).strip()
        if not authority_id or len(authority_id) > 256:
            raise HostSizingWindowError("Window-sizing authority ID is invalid.")
        object.__setattr__(self, "authority_id", authority_id)

        if isinstance(self.handle, bool) or not isinstance(self.handle, int):
            raise HostSizingWindowError("Window-sizing authority handle is invalid.")
        if self.handle <= 0 or self.baseline.handle != self.handle:
            raise HostSizingWindowError(
                "Window-sizing authority and baseline handles must match."
            )
        if self.browser_kind not in {BrowserKind.EDGE, BrowserKind.CHROME}:
            raise HostSizingWindowError(
                "Window sizing requires an explicit Edge or Chrome authority."
            )
        if isinstance(self.process_id, bool) or not isinstance(self.process_id, int):
            raise HostSizingWindowError("Window-sizing process identity is invalid.")
        process_ids: set[int] = set()
        for process_id in self.launch_process_ids:
            if (
                isinstance(process_id, bool)
                or not isinstance(process_id, int)
                or process_id <= 0
            ):
                raise HostSizingWindowError(
                    "Launch-process authority contains an invalid process ID."
                )
            process_ids.add(process_id)
        if self.process_id <= 0 or self.process_id not in process_ids:
            raise HostSizingWindowError(
                "Window process is outside the launch-process authority."
            )
        object.__setattr__(self, "launch_process_ids", frozenset(process_ids))
        if (
            isinstance(self.stable_polls, bool)
            or not isinstance(self.stable_polls, int)
            or self.stable_polls < MINIMUM_AUTHORITY_STABLE_POLLS
        ):
            raise HostSizingWindowError(
                "Window authority did not remain exact for enough stable polls."
            )
        if self.managed_profile is not True or self.app_mode is not True:
            raise HostSizingWindowError(
                "Window sizing requires managed-profile Chromium app mode."
            )
        invalid_geometry = _invalid_geometry_reason(self.baseline)
        if invalid_geometry is not None:
            raise HostSizingWindowError(
                f"Window-sizing baseline is invalid: {invalid_geometry}"
            )


@dataclass(frozen=True)
class WindowAuthorityVerification:
    """One pre- or post-mutation identity verification result."""

    exact: bool
    reason: str
    window: WindowInfo | None = None


@dataclass(frozen=True)
class HostSizingMutationResult:
    """Credential-free result suitable for policy acknowledgement."""

    status: HostSizingMutationStatus
    reason: str
    decision: HostSizingDecision
    authority_id: str
    baseline: WindowGeometry
    pre_apply: WindowGeometry | None
    after: WindowGeometry | None
    plan: HeightResizePlan | None
    mutation_attempted: bool

    @property
    def applied(self) -> bool:
        """Return whether a native size mutation was verified."""

        return self.status == HostSizingMutationStatus.APPLIED

    @property
    def acknowledgement_succeeded(self) -> bool:
        """Return the safe success value for policy acknowledgement."""

        return self.status in {
            HostSizingMutationStatus.APPLIED,
            HostSizingMutationStatus.NO_CHANGE,
        }

    @property
    def safe_to_retry(self) -> bool:
        """Native mutation attempts are never retried automatically."""

        return False


class WindowCaptureProvider(Protocol):
    """Narrow observation seam used to revalidate exact window identity."""

    def capture(self) -> Sequence[WindowInfo]:
        """Return current visible top-level window observations."""


class WindowAuthorityVerifier(Protocol):
    """Revalidate exact launch-associated identity immediately around mutation."""

    def verify(self, authority: WindowSizingAuthority) -> WindowAuthorityVerification:
        """Return exact only for the same sole launch-associated Chromium window."""


class WindowsWindowAuthorityVerifier:
    """Strictly revalidate one visible Edge or Chrome window by HWND and PID."""

    def __init__(self, provider: WindowCaptureProvider | None = None) -> None:
        self.provider = provider or WindowsWindowProvider()

    def verify(self, authority: WindowSizingAuthority) -> WindowAuthorityVerification:
        """Require one strict Chromium candidate inside the launch-process set."""

        if getattr(self.provider, "is_windows", True) is not True:
            return WindowAuthorityVerification(
                False,
                "Windows window identity verification is unavailable.",
            )
        try:
            windows = tuple(self.provider.capture())
        except Exception:
            return WindowAuthorityVerification(
                False,
                "Windows window identity capture failed.",
            )
        candidates = tuple(
            window
            for window in windows
            if _strict_authority_candidate(window, authority)
        )
        if len(candidates) != 1:
            return WindowAuthorityVerification(
                False,
                "Exact window authority no longer has one launch-associated "
                f"Chromium candidate; found {len(candidates)}.",
            )
        window = candidates[0]
        if window.handle != str(authority.handle) or window.pid != authority.process_id:
            return WindowAuthorityVerification(
                False,
                "Launch-associated Chromium identity no longer matches the "
                "authorized HWND and process.",
                window,
            )
        return WindowAuthorityVerification(
            True,
            "Exact launch-associated Chromium window identity verified.",
            window,
        )


class TrustedWindowsWindowSizer:
    """Apply approved decisions to one exact, continuously revalidated window."""

    def __init__(
        self,
        *,
        backend: GeometryBackend | None = None,
        authority_verifier: WindowAuthorityVerifier | None = None,
        lifetime: WindowSizingLifetime = WindowSizingLifetime.ONE_SHOT,
    ) -> None:
        if not isinstance(lifetime, WindowSizingLifetime):
            raise TypeError("Window-sizing capability lifetime is invalid.")
        self.backend = backend or WindowsGeometryBackend()
        self.authority_verifier = authority_verifier or WindowsWindowAuthorityVerifier()
        self.lifetime = lifetime
        self._lock = threading.Lock()
        self._apply_calls = 0
        self._bound_authority: WindowSizingAuthority | None = None
        self._expected_geometry: WindowGeometry | None = None

    @property
    def consumed(self) -> bool:
        """Return whether this capability has received an apply call."""

        with self._lock:
            return self._apply_calls > 0

    @property
    def apply_calls(self) -> int:
        """Return the number of serialized policy decisions received."""

        with self._lock:
            return self._apply_calls

    def apply(
        self,
        *,
        decision: HostSizingDecision,
        authority: WindowSizingAuthority,
    ) -> HostSizingMutationResult:
        """Apply one exact bounded height mutation or return a fail-closed result."""

        with self._lock:
            if self.lifetime == WindowSizingLifetime.ONE_SHOT and self._apply_calls > 0:
                return self._result(
                    HostSizingMutationStatus.REFUSED,
                    "Window-sizing capability was already consumed.",
                    decision,
                    authority,
                )
            if self._bound_authority is None:
                self._bound_authority = authority
                self._expected_geometry = authority.baseline
            elif authority != self._bound_authority:
                return self._result(
                    HostSizingMutationStatus.REFUSED,
                    "Window-sizing authority changed during the runtime session.",
                    decision,
                    authority,
                )
            self._apply_calls += 1
            try:
                result = self._apply_once(decision=decision, authority=authority)
            except Exception:
                return self._result(
                    HostSizingMutationStatus.FAILED,
                    "Window-sizing capability failed closed on an unexpected error.",
                    decision,
                    authority,
                    mutation_attempted=True,
                )
            if result.acknowledgement_succeeded and result.after is not None:
                self._expected_geometry = result.after
            return result

    def _apply_once(
        self,
        *,
        decision: HostSizingDecision,
        authority: WindowSizingAuthority,
    ) -> HostSizingMutationResult:
        expected_geometry = self._expected_geometry
        if expected_geometry is None:
            return self._result(
                HostSizingMutationStatus.REFUSED,
                "Window-sizing capability has no verified geometry baseline.",
                decision,
                authority,
            )
        decision_error = _decision_error(decision, authority)
        if decision_error is not None:
            return self._result(
                HostSizingMutationStatus.REFUSED,
                decision_error,
                decision,
                authority,
            )

        verification = self.authority_verifier.verify(authority)
        if not verification.exact:
            return self._result(
                HostSizingMutationStatus.REFUSED,
                verification.reason,
                decision,
                authority,
            )

        try:
            pre_apply = self.backend.capture(authority.handle)
        except Exception:
            return self._result(
                HostSizingMutationStatus.FAILED,
                "Could not capture pre-apply Windows geometry.",
                decision,
                authority,
            )
        pre_apply = _normalize_managed_pre_apply(expected_geometry, pre_apply)
        geometry_error = _invalid_geometry_reason(pre_apply)
        if geometry_error is not None:
            return self._result(
                HostSizingMutationStatus.REFUSED,
                f"Pre-apply Windows geometry is invalid: {geometry_error}",
                decision,
                authority,
                pre_apply=pre_apply,
            )
        if geometry_changed(expected_geometry, pre_apply):
            return self._result(
                HostSizingMutationStatus.REFUSED,
                "Window geometry or state changed outside verified host sizing.",
                decision,
                authority,
                pre_apply=pre_apply,
            )

        current_viewport_height = decision.current_viewport_height
        desired_viewport_height = decision.desired_viewport_height
        device_pixel_ratio = decision.device_pixel_ratio
        assert current_viewport_height is not None
        assert desired_viewport_height is not None
        assert device_pixel_ratio is not None
        plan = plan_height_resize(
            pre_apply,
            current_viewport_height_css=current_viewport_height,
            desired_viewport_height_css=desired_viewport_height,
            device_pixel_ratio=device_pixel_ratio,
        )
        if not plan.safe:
            return self._result(
                HostSizingMutationStatus.REFUSED,
                plan.reason,
                decision,
                authority,
                pre_apply=pre_apply,
                plan=plan,
            )
        if plan.target_outer_height == pre_apply.outer.height:
            return self._result(
                HostSizingMutationStatus.NO_CHANGE,
                "Bounded native target already matches the current outer height.",
                decision,
                authority,
                pre_apply=pre_apply,
                after=pre_apply,
                plan=plan,
            )

        try:
            self.backend.set_outer_size(
                authority.handle,
                width=plan.target_outer_width,
                height=plan.target_outer_height,
            )
        except Exception:
            return self._result(
                HostSizingMutationStatus.FAILED,
                "Native height mutation call failed.",
                decision,
                authority,
                pre_apply=pre_apply,
                plan=plan,
                mutation_attempted=True,
            )

        try:
            after = self.backend.capture(authority.handle)
        except Exception:
            return self._result(
                HostSizingMutationStatus.FAILED,
                "Could not verify Windows geometry after mutation.",
                decision,
                authority,
                pre_apply=pre_apply,
                plan=plan,
                mutation_attempted=True,
            )
        after = _normalize_managed_post_apply(pre_apply, after, plan)
        post_identity = self.authority_verifier.verify(authority)
        post_error = _post_apply_error(pre_apply, after, plan)
        if not post_identity.exact or post_error is not None:
            reason = (
                post_identity.reason if not post_identity.exact else str(post_error)
            )
            return self._result(
                HostSizingMutationStatus.FAILED,
                reason,
                decision,
                authority,
                pre_apply=pre_apply,
                after=after,
                plan=plan,
                mutation_attempted=True,
            )
        return self._result(
            HostSizingMutationStatus.APPLIED,
            "Applied and verified one bounded height-only Windows resize.",
            decision,
            authority,
            pre_apply=pre_apply,
            after=after,
            plan=plan,
            mutation_attempted=True,
        )

    def _result(
        self,
        status: HostSizingMutationStatus,
        reason: str,
        decision: HostSizingDecision,
        authority: WindowSizingAuthority,
        *,
        pre_apply: WindowGeometry | None = None,
        after: WindowGeometry | None = None,
        plan: HeightResizePlan | None = None,
        mutation_attempted: bool = False,
    ) -> HostSizingMutationResult:
        baseline = self._expected_geometry or authority.baseline
        return HostSizingMutationResult(
            status=status,
            reason=reason,
            decision=decision,
            authority_id=authority.authority_id,
            baseline=baseline,
            pre_apply=pre_apply,
            after=after,
            plan=plan,
            mutation_attempted=mutation_attempted,
        )


def create_window_sizing_authority(
    *,
    authority_id: str,
    probe: WindowAuthorityProbe,
    browser_kind: BrowserKind,
    launch_process_ids: Iterable[int],
    baseline: WindowGeometry,
    managed_profile: bool,
    app_mode: bool,
) -> WindowSizingAuthority:
    """Promote one exact stable probe into immutable mutation authority."""

    if probe.status != WindowAuthorityStatus.EXACT or probe.window is None:
        raise HostSizingWindowError("Window probe did not establish exact authority.")
    window = probe.window
    if probe.stable_polls < MINIMUM_AUTHORITY_STABLE_POLLS:
        raise HostSizingWindowError("Window probe authority was not stable enough.")
    if not _strict_chromium_window(window, browser_kind):
        raise HostSizingWindowError(
            "Window probe did not identify the requested Chromium browser."
        )
    if window.pid is None:
        raise HostSizingWindowError("Window probe has no process identity.")
    try:
        handle = int(window.handle)
    except (TypeError, ValueError) as exc:
        raise HostSizingWindowError("Window probe handle is invalid.") from exc
    return WindowSizingAuthority(
        authority_id=authority_id,
        handle=handle,
        browser_kind=browser_kind,
        process_id=window.pid,
        launch_process_ids=frozenset(launch_process_ids),
        stable_polls=probe.stable_polls,
        baseline=baseline,
        managed_profile=managed_profile,
        app_mode=app_mode,
    )


def _decision_error(
    decision: HostSizingDecision,
    authority: WindowSizingAuthority,
) -> str | None:
    if not isinstance(decision, HostSizingDecision):
        return "Window sizing requires a typed policy decision."
    if decision.action != HostSizingAction.APPLY:
        return "Window sizing requires a policy apply decision."
    if decision.state != HostSizingPolicyState.APPLY_PENDING:
        return "Policy decision is not awaiting mutation acknowledgement."
    if decision.authority_id != authority.authority_id:
        return "Policy decision authority does not match the authorized window."
    if (
        isinstance(decision.desired_viewport_height, bool)
        or not isinstance(decision.desired_viewport_height, int)
        or decision.desired_viewport_height < HOST_SIZING_HARD_MIN_VIEWPORT_HEIGHT
        or decision.desired_viewport_height > HOST_SIZING_HARD_MAX_VIEWPORT_HEIGHT
    ):
        return "Desired viewport height is outside hard policy bounds."
    current = decision.current_viewport_height
    if (
        isinstance(current, bool)
        or not isinstance(current, (int, float))
        or not math.isfinite(float(current))
        or current <= 0
    ):
        return "Current viewport height is invalid."
    ratio = decision.device_pixel_ratio
    if (
        isinstance(ratio, bool)
        or not isinstance(ratio, (int, float))
        or not math.isfinite(float(ratio))
        or ratio < HOST_SIZING_MIN_DEVICE_PIXEL_RATIO
        or ratio > HOST_SIZING_MAX_DEVICE_PIXEL_RATIO
    ):
        return "Device-pixel ratio is outside protocol bounds."
    if (
        not decision.source_id
        or isinstance(decision.sequence, bool)
        or not isinstance(decision.sequence, int)
        or decision.sequence < 1
    ):
        return "Policy decision is missing report authority metadata."
    if (
        isinstance(decision.requested_viewport_height, bool)
        or not isinstance(decision.requested_viewport_height, int)
        or decision.requested_viewport_height < 1
    ):
        return "Policy decision is missing normalized target metadata."
    return None


def _strict_authority_candidate(
    window: WindowInfo,
    authority: WindowSizingAuthority,
) -> bool:
    return (
        _strict_chromium_window(window, authority.browser_kind)
        and window.pid is not None
        and window.pid in authority.launch_process_ids
    )


def _strict_chromium_window(window: WindowInfo, browser_kind: BrowserKind) -> bool:
    return window.class_name.startswith(
        "Chrome_WidgetWin"
    ) and window_matches_browser_kind(window, browser_kind)


def _invalid_geometry_reason(geometry: WindowGeometry) -> str | None:
    if geometry.handle <= 0:
        return "window handle is invalid."
    if geometry.outer.width <= 0 or geometry.outer.height <= 0:
        return "outer-window dimensions are not positive."
    if geometry.client_width <= 0 or geometry.client_height <= 0:
        return "client dimensions are not positive."
    if geometry.dpi < 96:
        return "target-window DPI is invalid."
    if geometry.monitor_handle <= 0:
        return "monitor identity is invalid."
    if geometry.monitor.width <= 0 or geometry.monitor.height <= 0:
        return "monitor bounds are invalid."
    if geometry.work_area.width <= 0 or geometry.work_area.height <= 0:
        return "monitor work area is invalid."
    return None


def _post_apply_error(
    before: WindowGeometry,
    after: WindowGeometry,
    plan: HeightResizePlan,
) -> str | None:
    invalid_geometry = _invalid_geometry_reason(after)
    if invalid_geometry is not None:
        return f"Post-apply Windows geometry is invalid: {invalid_geometry}"
    if after.handle != before.handle:
        return "Post-apply HWND no longer matches the authorized window."
    if after.state != WindowGeometryState.NORMAL:
        return f"Post-apply window state is {after.state.value}, not normal."
    if (
        after.outer.left != before.outer.left
        or after.outer.top != before.outer.top
        or after.outer.width != before.outer.width
    ):
        return "Native resize changed window position or width."
    if abs(after.outer.height - plan.target_outer_height) > 1:
        return "Native resize did not reach the bounded target height."
    if (
        after.dpi != before.dpi
        or after.monitor_handle != before.monitor_handle
        or after.monitor != before.monitor
        or after.work_area != before.work_area
        or after.show_command != before.show_command
    ):
        return "Native resize changed monitor, DPI, work area, or show state."
    if abs(after.client_width - before.client_width) > 1:
        return "Native resize unexpectedly changed client width."
    if after.outer.bottom > after.work_area.bottom:
        return "Native resize exceeded the current monitor work area."
    return None


def _normalize_managed_pre_apply(
    expected: WindowGeometry,
    observed: WindowGeometry,
) -> WindowGeometry:
    """Ignore a snap heuristic caused solely by our verified prior resize."""

    if (
        expected.state == WindowGeometryState.NORMAL
        and observed.state == WindowGeometryState.SNAPPED
        and replace(observed, state=WindowGeometryState.NORMAL) == expected
    ):
        return expected
    return observed


def _normalize_managed_post_apply(
    before: WindowGeometry,
    after: WindowGeometry,
    plan: HeightResizePlan,
) -> WindowGeometry:
    """Keep an exact host-created work-area clamp in managed normal state."""

    if (
        before.state == WindowGeometryState.NORMAL
        and after.state == WindowGeometryState.SNAPPED
        and "monitor_work_area" in plan.clamp_reasons
        and after.outer.left == before.outer.left
        and after.outer.top == before.outer.top
        and after.outer.width == before.outer.width
        and abs(after.outer.height - plan.target_outer_height) <= 1
        and after.dpi == before.dpi
        and after.monitor_handle == before.monitor_handle
        and after.monitor == before.monitor
        and after.work_area == before.work_area
        and after.show_command == before.show_command
    ):
        return replace(after, state=WindowGeometryState.NORMAL)
    return after
