"""Private deterministic policy for authenticated host-window fit decisions.

The policy consumes authenticated, validated reports and produces immutable
decisions. It does not parse transport input, discover windows, convert geometry,
or mutate native state.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from litlaunch._host_sizing_transport import HostSizingReport

HOST_SIZING_QUIET_PERIOD_SECONDS = 0.25
HOST_SIZING_TIMEOUT_SECONDS = 5.0
HOST_SIZING_HARD_MIN_VIEWPORT_HEIGHT = 320
HOST_SIZING_HARD_MAX_VIEWPORT_HEIGHT = 4096
HOST_SIZING_MINIMUM_VIEWPORT_DELTA = 1.0


class HostSizingPolicyError(RuntimeError):
    """Raised when the private policy is configured or driven incorrectly."""


class HostSizingPolicyMode(str, Enum):
    """Internal decision lifetime selected from the public launch policy."""

    INITIAL = "initial"
    CONTINUOUS = "continuous"


class HostSizingAction(str, Enum):
    """Actions emitted by the private policy state machine."""

    WAIT = "wait"
    APPLY = "apply"
    IGNORE = "ignore"
    ABORT = "abort"
    COMPLETE = "complete"


class HostSizingPolicyState(str, Enum):
    """Lifecycle states shared by initial and continuous fitting."""

    WAITING = "waiting"
    STABILIZING = "stabilizing"
    APPLY_PENDING = "apply_pending"
    COMPLETE = "complete"
    ABORTED = "aborted"
    TIMED_OUT = "timed_out"
    SHUT_DOWN = "shut_down"

    @property
    def terminal(self) -> bool:
        """Return whether the policy can never emit another apply decision."""

        return self in {
            HostSizingPolicyState.COMPLETE,
            HostSizingPolicyState.ABORTED,
            HostSizingPolicyState.TIMED_OUT,
            HostSizingPolicyState.SHUT_DOWN,
        }


class HostSizingAuthorityStatus(str, Enum):
    """Opaque window-authority observations accepted by the policy."""

    PENDING = "pending"
    EXACT = "exact"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED = "unsupported"
    LOST = "lost"


@dataclass(frozen=True)
class HostSizingPolicyConfig:
    """Internal stabilization timing and CSS viewport bounds."""

    quiet_period_seconds: float = HOST_SIZING_QUIET_PERIOD_SECONDS
    timeout_seconds: float = HOST_SIZING_TIMEOUT_SECONDS
    min_viewport_height: int | None = None
    max_viewport_height: int | None = None

    def __post_init__(self) -> None:
        quiet = _finite_number(
            self.quiet_period_seconds,
            "quiet_period_seconds",
        )
        timeout = _finite_number(self.timeout_seconds, "timeout_seconds")
        if quiet < 0:
            raise HostSizingPolicyError("Quiet period must not be negative.")
        if timeout <= 0:
            raise HostSizingPolicyError("Policy timeout must be positive.")
        object.__setattr__(self, "quiet_period_seconds", quiet)
        object.__setattr__(self, "timeout_seconds", timeout)

        minimum = _optional_positive_int(
            self.min_viewport_height,
            "min_viewport_height",
        )
        maximum = _optional_positive_int(
            self.max_viewport_height,
            "max_viewport_height",
        )
        if minimum is not None and maximum is not None and minimum > maximum:
            raise HostSizingPolicyError(
                "Configured minimum viewport height exceeds the maximum."
            )
        effective_minimum = max(
            HOST_SIZING_HARD_MIN_VIEWPORT_HEIGHT,
            minimum or HOST_SIZING_HARD_MIN_VIEWPORT_HEIGHT,
        )
        effective_maximum = min(
            HOST_SIZING_HARD_MAX_VIEWPORT_HEIGHT,
            maximum or HOST_SIZING_HARD_MAX_VIEWPORT_HEIGHT,
        )
        if effective_minimum > effective_maximum:
            raise HostSizingPolicyError(
                "Configured viewport bounds do not overlap the hard policy bounds."
            )
        object.__setattr__(self, "min_viewport_height", minimum)
        object.__setattr__(self, "max_viewport_height", maximum)

    @property
    def effective_min_viewport_height(self) -> int:
        """Return the configured minimum constrained by the hard policy floor."""

        return max(
            HOST_SIZING_HARD_MIN_VIEWPORT_HEIGHT,
            self.min_viewport_height or HOST_SIZING_HARD_MIN_VIEWPORT_HEIGHT,
        )

    @property
    def effective_max_viewport_height(self) -> int:
        """Return the configured maximum constrained by the hard policy ceiling."""

        return min(
            HOST_SIZING_HARD_MAX_VIEWPORT_HEIGHT,
            self.max_viewport_height or HOST_SIZING_HARD_MAX_VIEWPORT_HEIGHT,
        )


@dataclass(frozen=True)
class HostSizingDecision:
    """One deterministic, credential-free host-sizing policy decision."""

    action: HostSizingAction
    state: HostSizingPolicyState
    desired_viewport_height: int | None
    reason: str
    authority_id: str | None = None
    source_id: str | None = None
    sequence: int | None = None
    current_viewport_height: float | None = None
    device_pixel_ratio: float | None = None
    requested_viewport_height: int | None = None
    clamp_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class HostSizingPolicySnapshot:
    """Immutable policy state for deterministic tests and bounded diagnostics."""

    state: HostSizingPolicyState
    mode: HostSizingPolicyMode
    authority_status: HostSizingAuthorityStatus
    authority_id: str | None
    bound_launch_id: str | None
    bound_source_id: str | None
    last_sequence: int | None
    latest_report: HostSizingReport | None
    started_at: float
    timeout_deadline: float
    quiet_deadline: float | None
    apply_decisions: int
    last_applied_sequence: int | None
    last_applied_target_height: int | None
    terminal_reason: str | None


class HostSizingPolicy:
    """Thread-safe state machine for bounded initial or continuous fitting."""

    def __init__(
        self,
        *,
        config: HostSizingPolicyConfig | None = None,
        mode: HostSizingPolicyMode = HostSizingPolicyMode.INITIAL,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(mode, HostSizingPolicyMode):
            raise TypeError("Host-sizing policy mode is invalid.")
        self.config = config or HostSizingPolicyConfig()
        self.mode = mode
        self._clock = clock
        self._lock = threading.RLock()
        started_at = self._read_clock_value()
        self._started_at = started_at
        self._last_now = started_at
        self._timeout_deadline = started_at + self.config.timeout_seconds
        self._state = HostSizingPolicyState.WAITING
        self._authority_status = HostSizingAuthorityStatus.PENDING
        self._authority_id: str | None = None
        self._bound_launch_id: str | None = None
        self._bound_source_id: str | None = None
        self._last_sequence: int | None = None
        self._latest_report: HostSizingReport | None = None
        self._material_signature: tuple[float, float | None, float, float] | None = None
        self._quiet_deadline: float | None = None
        self._apply_decisions = 0
        self._last_applied_sequence: int | None = None
        self._last_applied_target_height: int | None = None
        self._terminal_reason: str | None = None

    @property
    def continuous(self) -> bool:
        """Return whether successful decisions preserve session authority."""

        return self.mode == HostSizingPolicyMode.CONTINUOUS

    def observe_report(self, report: HostSizingReport) -> HostSizingDecision:
        """Consume one already validated report without parsing transport input."""

        if not isinstance(report, HostSizingReport):
            raise TypeError("Host-sizing policy requires a validated HostSizingReport.")
        with self._lock:
            now = self._now()
            if self._state.terminal:
                return self._decision(
                    HostSizingAction.IGNORE,
                    "Report ignored because the policy is terminal.",
                )
            timeout = self._timeout_if_due(now)
            if timeout is not None:
                return timeout
            if self._state == HostSizingPolicyState.APPLY_PENDING:
                return self._decision(
                    HostSizingAction.IGNORE,
                    "Report ignored after the one apply decision was emitted.",
                )

            if self._bound_launch_id is None:
                self._bound_launch_id = report.launch_id
            elif report.launch_id != self._bound_launch_id:
                return self._terminate(
                    HostSizingPolicyState.ABORTED,
                    HostSizingAction.ABORT,
                    "Host-sizing launch authority changed during policy execution.",
                )

            if self._bound_source_id is None:
                self._bound_source_id = report.source_id
            elif report.source_id != self._bound_source_id:
                return self._terminate(
                    HostSizingPolicyState.ABORTED,
                    HostSizingAction.ABORT,
                    "Host-sizing source authority conflict.",
                )

            if (
                self._last_sequence is not None
                and report.sequence <= self._last_sequence
            ):
                return self._decision(
                    HostSizingAction.IGNORE,
                    "Stale host-sizing report ignored.",
                )

            signature = (
                report.content.height,
                report.content.width,
                report.desired_host_viewport.height,
                report.device_pixel_ratio,
            )
            material_change = signature != self._material_signature
            self._last_sequence = report.sequence
            self._latest_report = report

            if material_change:
                self._material_signature = signature
                self._quiet_deadline = now + self.config.quiet_period_seconds
                self._state = HostSizingPolicyState.STABILIZING
                evaluated = self._evaluate(now)
                if evaluated.action != HostSizingAction.WAIT:
                    return evaluated
                return self._decision(
                    HostSizingAction.WAIT,
                    "Material sizing input accepted; stabilization restarted.",
                )

            evaluated = self._evaluate(now)
            if evaluated.action != HostSizingAction.WAIT:
                return evaluated
            return self._decision(
                HostSizingAction.IGNORE,
                "Viewport-only sizing feedback retained without restarting "
                "stabilization.",
            )

    def observe_authority(
        self,
        status: HostSizingAuthorityStatus,
        *,
        authority_id: str | None = None,
        reason: str | None = None,
    ) -> HostSizingDecision:
        """Consume an opaque authority result without knowing native window details."""

        if not isinstance(status, HostSizingAuthorityStatus):
            raise TypeError("Host-sizing authority status is invalid.")
        with self._lock:
            now = self._now()
            if self._state.terminal:
                return self._decision(
                    HostSizingAction.IGNORE,
                    "Authority update ignored because the policy is terminal.",
                )
            timeout = self._timeout_if_due(now)
            if timeout is not None:
                return timeout

            if status == HostSizingAuthorityStatus.EXACT:
                resolved_id = str(authority_id or "").strip()
                if not resolved_id:
                    raise HostSizingPolicyError(
                        "Exact host-sizing authority requires an opaque identity."
                    )
                if len(resolved_id) > 256:
                    raise HostSizingPolicyError(
                        "Host-sizing authority identity is unexpectedly long."
                    )
                if self._authority_id is None:
                    self._authority_id = resolved_id
                elif resolved_id != self._authority_id:
                    return self._terminate(
                        HostSizingPolicyState.ABORTED,
                        HostSizingAction.ABORT,
                        "Exact host-sizing authority changed before completion.",
                    )
                self._authority_status = status
                return self._evaluate(now)

            if status == HostSizingAuthorityStatus.PENDING:
                if self._authority_id is not None:
                    return self._terminate(
                        HostSizingPolicyState.ABORTED,
                        HostSizingAction.ABORT,
                        "Exact host-sizing authority was lost before completion.",
                    )
                self._authority_status = status
                return self._decision(
                    HostSizingAction.WAIT,
                    reason or "Waiting for exact host-sizing authority.",
                )

            self._authority_status = status
            default_reason = {
                HostSizingAuthorityStatus.AMBIGUOUS: (
                    "Host-sizing authority is ambiguous."
                ),
                HostSizingAuthorityStatus.UNSUPPORTED: (
                    "Host-sizing authority is unsupported."
                ),
                HostSizingAuthorityStatus.LOST: (
                    "Host-sizing authority was lost before completion."
                ),
            }[status]
            return self._terminate(
                HostSizingPolicyState.ABORTED,
                HostSizingAction.ABORT,
                reason or default_reason,
            )

    def evaluate(self) -> HostSizingDecision:
        """Advance timers and emit the next deterministic policy decision."""

        with self._lock:
            return self._evaluate(self._now())

    def acknowledge_apply(
        self,
        *,
        applied: bool,
        reason: str | None = None,
    ) -> HostSizingDecision:
        """Resolve one pending apply after the mutation collaborator handles it."""

        if not isinstance(applied, bool):
            raise TypeError("Apply acknowledgement must be a boolean.")
        with self._lock:
            now = self._now()
            if self._state != HostSizingPolicyState.APPLY_PENDING:
                raise HostSizingPolicyError(
                    "No host-sizing apply decision is awaiting acknowledgement."
                )
            timeout = self._timeout_if_due(now)
            if timeout is not None:
                return timeout
            if applied:
                if self.continuous:
                    report = self._latest_report
                    assert report is not None
                    self._last_applied_sequence = report.sequence
                    self._last_applied_target_height = self._bounded_target(
                        report.desired_host_viewport.height
                    )[1]
                    self._state = HostSizingPolicyState.WAITING
                    self._quiet_deadline = None
                    return self._decision(
                        HostSizingAction.WAIT,
                        reason
                        or "Continuous host-sizing apply completed; waiting for "
                        "meaningful later input.",
                    )
                return self._terminate(
                    HostSizingPolicyState.COMPLETE,
                    HostSizingAction.COMPLETE,
                    reason or "Initial host-sizing apply decision completed.",
                )
            return self._terminate(
                HostSizingPolicyState.ABORTED,
                HostSizingAction.ABORT,
                reason or "Initial host-sizing apply decision was not applied.",
            )

    def abort(self, reason: str) -> HostSizingDecision:
        """Abort for user intent, window state, or another external safety gate."""

        resolved_reason = str(reason).strip()
        if not resolved_reason:
            raise HostSizingPolicyError("Host-sizing abort requires a reason.")
        with self._lock:
            self._now()
            if self._state.terminal:
                return self._decision(
                    HostSizingAction.IGNORE,
                    "Abort ignored because the policy is already terminal.",
                )
            return self._terminate(
                HostSizingPolicyState.ABORTED,
                HostSizingAction.ABORT,
                resolved_reason,
            )

    def shutdown(self) -> HostSizingDecision:
        """Cancel pending sizing without affecting the surrounding runtime."""

        with self._lock:
            self._now()
            if self._state.terminal:
                return self._decision(
                    HostSizingAction.IGNORE,
                    "Shutdown cancellation ignored because the policy is terminal.",
                )
            return self._terminate(
                HostSizingPolicyState.SHUT_DOWN,
                HostSizingAction.ABORT,
                "Host-sizing policy cancelled during runtime shutdown.",
            )

    def snapshot(self) -> HostSizingPolicySnapshot:
        """Return an immutable view of current policy state."""

        with self._lock:
            return HostSizingPolicySnapshot(
                state=self._state,
                mode=self.mode,
                authority_status=self._authority_status,
                authority_id=self._authority_id,
                bound_launch_id=self._bound_launch_id,
                bound_source_id=self._bound_source_id,
                last_sequence=self._last_sequence,
                latest_report=self._latest_report,
                started_at=self._started_at,
                timeout_deadline=self._timeout_deadline,
                quiet_deadline=self._quiet_deadline,
                apply_decisions=self._apply_decisions,
                last_applied_sequence=self._last_applied_sequence,
                last_applied_target_height=self._last_applied_target_height,
                terminal_reason=self._terminal_reason,
            )

    def _evaluate(self, now: float) -> HostSizingDecision:
        if self._state.terminal:
            return self._decision(
                HostSizingAction.IGNORE,
                "Policy evaluation ignored because the policy is terminal.",
            )
        timeout = self._timeout_if_due(now)
        if timeout is not None:
            return timeout
        if self._state == HostSizingPolicyState.APPLY_PENDING:
            return self._decision(
                HostSizingAction.WAIT,
                "Waiting for the one apply decision to be acknowledged.",
            )
        if self._latest_report is None:
            return self._decision(
                HostSizingAction.WAIT,
                "Waiting for an accepted host-sizing report.",
            )
        if self._authority_status != HostSizingAuthorityStatus.EXACT:
            return self._decision(
                HostSizingAction.WAIT,
                "Waiting for exact host-sizing authority.",
            )
        if self._quiet_deadline is None or now < self._quiet_deadline:
            return self._decision(
                HostSizingAction.WAIT,
                "Waiting for host-sizing input to stabilize.",
            )
        if self._apply_decisions != 0 and not self.continuous:
            return self._terminate(
                HostSizingPolicyState.ABORTED,
                HostSizingAction.ABORT,
                "Host-sizing policy refused a second apply decision.",
            )

        requested, desired, clamp_reasons = self._bounded_target(
            self._latest_report.desired_host_viewport.height
        )
        current = self._latest_report.host_viewport.height
        if abs(desired - current) <= HOST_SIZING_MINIMUM_VIEWPORT_DELTA:
            reason = (
                "Bounded target is already within the host-sizing minimum "
                "viewport delta."
            )
            if self.continuous:
                self._last_applied_sequence = self._latest_report.sequence
                self._last_applied_target_height = desired
                self._state = HostSizingPolicyState.WAITING
                self._quiet_deadline = None
                return self._decision(
                    HostSizingAction.IGNORE,
                    reason,
                    desired_viewport_height=desired,
                    requested_viewport_height=requested,
                    clamp_reasons=clamp_reasons,
                )
            self._state = HostSizingPolicyState.COMPLETE
            self._terminal_reason = reason
            return self._decision(
                HostSizingAction.COMPLETE,
                reason,
                desired_viewport_height=desired,
                requested_viewport_height=requested,
                clamp_reasons=clamp_reasons,
            )
        self._apply_decisions += 1
        self._state = HostSizingPolicyState.APPLY_PENDING
        return self._decision(
            HostSizingAction.APPLY,
            (
                "Stable continuous host-sizing decision is ready for a mutation "
                "collaborator."
                if self.continuous
                else "Stable initial host-sizing decision is ready for a mutation "
                "collaborator."
            ),
            desired_viewport_height=desired,
            requested_viewport_height=requested,
            clamp_reasons=clamp_reasons,
        )

    def _timeout_if_due(self, now: float) -> HostSizingDecision | None:
        if self.continuous:
            return None
        if now < self._timeout_deadline:
            return None
        return self._terminate(
            HostSizingPolicyState.TIMED_OUT,
            HostSizingAction.ABORT,
            "Host-sizing policy timed out before producing an apply decision.",
        )

    def _terminate(
        self,
        state: HostSizingPolicyState,
        action: HostSizingAction,
        reason: str,
    ) -> HostSizingDecision:
        self._state = state
        self._terminal_reason = reason
        return self._decision(action, reason)

    def _decision(
        self,
        action: HostSizingAction,
        reason: str,
        *,
        desired_viewport_height: int | None = None,
        requested_viewport_height: int | None = None,
        clamp_reasons: tuple[str, ...] = (),
    ) -> HostSizingDecision:
        report = self._latest_report
        return HostSizingDecision(
            action=action,
            state=self._state,
            desired_viewport_height=desired_viewport_height,
            reason=reason,
            authority_id=self._authority_id,
            source_id=report.source_id if report is not None else None,
            sequence=report.sequence if report is not None else None,
            current_viewport_height=(
                report.host_viewport.height if report is not None else None
            ),
            device_pixel_ratio=(
                report.device_pixel_ratio if report is not None else None
            ),
            requested_viewport_height=requested_viewport_height,
            clamp_reasons=clamp_reasons,
        )

    def _bounded_target(
        self,
        desired_height: float,
    ) -> tuple[int, int, tuple[str, ...]]:
        requested = math.floor(desired_height + 0.5)
        bounded = requested
        reasons: list[str] = []

        if bounded < HOST_SIZING_HARD_MIN_VIEWPORT_HEIGHT:
            bounded = HOST_SIZING_HARD_MIN_VIEWPORT_HEIGHT
            reasons.append("hard_minimum")
        if bounded > HOST_SIZING_HARD_MAX_VIEWPORT_HEIGHT:
            bounded = HOST_SIZING_HARD_MAX_VIEWPORT_HEIGHT
            reasons.append("hard_maximum")
        if bounded < self.config.effective_min_viewport_height:
            bounded = self.config.effective_min_viewport_height
            reasons.append("configured_minimum")
        if bounded > self.config.effective_max_viewport_height:
            bounded = self.config.effective_max_viewport_height
            reasons.append("configured_maximum")
        return requested, bounded, tuple(reasons)

    def _now(self) -> float:
        value = self._read_clock_value()
        if value < self._last_now:
            raise HostSizingPolicyError("Host-sizing monotonic clock moved backwards.")
        self._last_now = value
        return value

    def _read_clock_value(self) -> float:
        return _finite_number(self._clock(), "monotonic clock")


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HostSizingPolicyError(f"{name} must be a finite number.")
    result = float(value)
    if not math.isfinite(result):
        raise HostSizingPolicyError(f"{name} must be a finite number.")
    return result


def _optional_positive_int(value: int | None, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HostSizingPolicyError(f"{name} must be a positive integer.")
    return value
