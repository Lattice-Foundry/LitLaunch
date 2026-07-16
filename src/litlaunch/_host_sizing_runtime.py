"""Private one-shot host-sizing transport, policy, and mutation orchestration.

The coordinator joins authenticated reports, deterministic policy, and exact native
mutation without collapsing their separate trust boundaries.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import Protocol

from litlaunch._host_sizing_policy import (
    HostSizingAction,
    HostSizingAuthorityStatus,
    HostSizingDecision,
    HostSizingPolicy,
    HostSizingPolicyState,
)
from litlaunch._host_sizing_transport import (
    HostSizingChannel,
    HostSizingChannelConfig,
    HostSizingReport,
)
from litlaunch._host_sizing_window import (
    HostSizingMutationResult,
    WindowSizingAuthority,
)

HOST_SIZING_RUNTIME_POLL_SECONDS = 0.025


class HostSizingRuntimeError(RuntimeError):
    """Raised when the private coordinator cannot start safely."""


class HostSizingMutationCapability(Protocol):
    """Narrow one-shot native mutation collaborator contract."""

    def apply(
        self,
        *,
        decision: HostSizingDecision,
        authority: WindowSizingAuthority,
    ) -> HostSizingMutationResult:
        """Apply one policy-approved decision to one exact authority."""


@dataclass(frozen=True)
class HostSizingRuntimeSnapshot:
    """Credential-free immutable coordinator state."""

    active: bool
    policy_state: HostSizingPolicyState
    accepted_reports: int
    mutation_calls: int
    acknowledgements: int
    last_decision: HostSizingDecision
    apply_decision: HostSizingDecision | None
    mutation_result: HostSizingMutationResult | None
    failure_reason: str | None
    channel_active: bool


class HostSizingRuntimeCoordinator:
    """Coordinate one private initial-fit attempt without retries or loops."""

    def __init__(
        self,
        *,
        policy: HostSizingPolicy,
        mutation: HostSizingMutationCapability,
        authority: WindowSizingAuthority,
        poll_interval_seconds: float = HOST_SIZING_RUNTIME_POLL_SECONDS,
    ) -> None:
        poll_interval = _positive_finite_poll_interval(poll_interval_seconds)
        self.policy = policy
        self.mutation = mutation
        self.authority = authority
        self._poll_interval_seconds = poll_interval
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._terminal_event = threading.Event()
        self._channel: HostSizingChannel | None = None
        self._worker: threading.Thread | None = None
        self._closed = False
        self._accepted_reports = 0
        self._mutation_calls = 0
        self._acknowledgements = 0
        self._apply_decision: HostSizingDecision | None = None
        self._mutation_result: HostSizingMutationResult | None = None
        self._failure_reason: str | None = None
        self._last_decision = self.policy.observe_authority(
            HostSizingAuthorityStatus.EXACT,
            authority_id=authority.authority_id,
        )
        if self._last_decision.state.terminal:
            self._terminal_event.set()

    @property
    def channel_config(self) -> HostSizingChannelConfig | None:
        """Return private endpoint handoff configuration when attached."""

        with self._lock:
            return self._channel.config if self._channel is not None else None

    def attach_channel(self, channel: HostSizingChannel) -> None:
        """Attach the dedicated report channel before lifecycle polling starts."""

        if not isinstance(channel, HostSizingChannel):
            raise TypeError("Host-sizing runtime requires a HostSizingChannel.")
        with self._lock:
            if self._closed or self._channel is not None:
                raise HostSizingRuntimeError(
                    "Host-sizing runtime cannot attach this channel."
                )
            self._channel = channel

    def start(self) -> None:
        """Start bounded policy timeout and terminal-channel lifecycle polling."""

        with self._lock:
            if self._closed:
                raise HostSizingRuntimeError("Host-sizing runtime is closed.")
            if self._channel is None:
                raise HostSizingRuntimeError(
                    "Host-sizing runtime requires an attached channel."
                )
            if self._worker is not None:
                raise HostSizingRuntimeError("Host-sizing runtime is already started.")
            worker = threading.Thread(
                target=self._run,
                daemon=True,
                name="litlaunch-host-sizing-runtime",
            )
            self._worker = worker
            try:
                worker.start()
            except Exception:
                self._worker = None
                raise

    def consume_accepted_report(
        self,
        report: HostSizingReport,
    ) -> HostSizingDecision:
        """Consume one authenticated typed report and dispatch its decision."""

        if not isinstance(report, HostSizingReport):
            raise TypeError(
                "Host-sizing runtime requires an accepted HostSizingReport."
            )
        with self._lock:
            self._accepted_reports += 1
            decision = self.policy.observe_report(report)
            return self._dispatch_locked(decision)

    def tick(self) -> HostSizingDecision:
        """Advance stabilization or timeout once for tests and the private worker."""

        with self._lock:
            decision = self.policy.evaluate()
            return self._dispatch_locked(decision)

    def shutdown(self) -> HostSizingDecision:
        """Cancel policy work and close the dedicated channel idempotently."""

        with self._lock:
            if self._closed:
                return self._last_decision
            if not self.policy.snapshot().state.terminal:
                self._last_decision = self.policy.shutdown()
            self._closed = True
            self._stop_event.set()
            self._terminal_event.set()
            worker = self._worker
        self._close_channel()
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=2.0)
        return self._last_decision

    close = shutdown

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for terminal policy state and endpoint cleanup."""

        completed = self._terminal_event.wait(timeout)
        if not completed:
            return False
        with self._lock:
            worker = self._worker
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=2.0)
            if worker.is_alive():
                return False
        with self._lock:
            return self._channel is None or not self._channel.active

    def snapshot(self) -> HostSizingRuntimeSnapshot:
        """Return one credential-free view of orchestration state."""

        with self._lock:
            channel_active = (
                self._channel.active if self._channel is not None else False
            )
            return HostSizingRuntimeSnapshot(
                active=not self._closed and not self.policy.snapshot().state.terminal,
                policy_state=self.policy.snapshot().state,
                accepted_reports=self._accepted_reports,
                mutation_calls=self._mutation_calls,
                acknowledgements=self._acknowledgements,
                last_decision=self._last_decision,
                apply_decision=self._apply_decision,
                mutation_result=self._mutation_result,
                failure_reason=self._failure_reason,
                channel_active=channel_active,
            )

    def _dispatch_locked(self, decision: HostSizingDecision) -> HostSizingDecision:
        self._last_decision = decision
        if decision.action == HostSizingAction.APPLY:
            if self._mutation_calls != 0 or self._acknowledgements != 0:
                self._failure_reason = (
                    "Coordinator refused a second host-sizing mutation decision."
                )
                self._last_decision = self.policy.abort(self._failure_reason)
            else:
                self._apply_decision = decision
                self._mutation_calls = 1
                try:
                    result = self.mutation.apply(
                        decision=decision,
                        authority=self.authority,
                    )
                    if not isinstance(result, HostSizingMutationResult):
                        raise TypeError(
                            "Mutation collaborator returned an invalid result."
                        )
                    acknowledgement_succeeded = result.acknowledgement_succeeded
                    result_reason = result.reason
                except Exception:
                    self._failure_reason = (
                        "Host-sizing mutation collaborator failed unexpectedly."
                    )
                    self._acknowledgements = 1
                    self._acknowledge_locked(
                        applied=False,
                        reason=self._failure_reason,
                    )
                else:
                    self._mutation_result = result
                    self._acknowledgements = 1
                    self._acknowledge_locked(
                        applied=acknowledgement_succeeded,
                        reason=result_reason,
                    )

        if self.policy.snapshot().state.terminal:
            self._terminal_event.set()
        return self._last_decision

    def _acknowledge_locked(self, *, applied: bool, reason: str) -> None:
        try:
            self._last_decision = self.policy.acknowledge_apply(
                applied=applied,
                reason=reason,
            )
        except Exception:
            self._failure_reason = (
                "Host-sizing policy acknowledgement failed unexpectedly."
            )
            self._last_decision = self.policy.abort(self._failure_reason)

    def _run(self) -> None:
        try:
            while not self._stop_event.wait(self._poll_interval_seconds):
                self.tick()
                if self._terminal_event.is_set():
                    break
        finally:
            self._close_channel()
            with self._lock:
                self._closed = True
                self._stop_event.set()

    def _close_channel(self) -> None:
        with self._lock:
            channel = self._channel
        if channel is not None:
            channel.close()


def _positive_finite_poll_interval(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HostSizingRuntimeError("Host-sizing poll interval must be finite.")
    result = float(value)
    if not math.isfinite(result) or result <= 0 or result > 1.0:
        raise HostSizingRuntimeError(
            "Host-sizing poll interval must be greater than zero and at most one."
        )
    return result
