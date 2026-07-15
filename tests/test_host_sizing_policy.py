from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import litlaunch
import litlaunch._host_sizing_policy as policy_module
from litlaunch._host_sizing_policy import (
    HOST_SIZING_HARD_MAX_VIEWPORT_HEIGHT,
    HOST_SIZING_HARD_MIN_VIEWPORT_HEIGHT,
    HOST_SIZING_MINIMUM_VIEWPORT_DELTA,
    HOST_SIZING_QUIET_PERIOD_SECONDS,
    HOST_SIZING_TIMEOUT_SECONDS,
    HostSizingAction,
    HostSizingAuthorityStatus,
    HostSizingDecision,
    HostSizingPolicy,
    HostSizingPolicyConfig,
    HostSizingPolicyError,
    HostSizingPolicyState,
)
from litlaunch._host_sizing_transport import (
    HostSizingReport,
    HostSizingReportStore,
    SurfaceDimensions,
)


class FakeClock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class FakeMutationCollaborator:
    def __init__(self, *, succeeds: bool = True) -> None:
        self.succeeds = succeeds
        self.decisions: list[HostSizingDecision] = []

    def apply(self, decision: HostSizingDecision) -> bool:
        assert decision.action == HostSizingAction.APPLY
        self.decisions.append(decision)
        return self.succeeds


def report(
    sequence: int = 1,
    *,
    launch_id: str = "launch-authority-123456",
    source_id: str = "primary-surface",
    content_height: float = 742,
    content_width: float | None = 1180,
    viewport_height: float = 812,
    viewport_width: float | None = 1280,
    desired_height: float = 790,
    desired_width: float | None = None,
    device_pixel_ratio: float = 1.0,
) -> HostSizingReport:
    return HostSizingReport(
        protocol=1,
        launch_id=launch_id,
        source_id=source_id,
        sequence=sequence,
        device_pixel_ratio=device_pixel_ratio,
        content=SurfaceDimensions(content_height, content_width),
        host_viewport=SurfaceDimensions(viewport_height, viewport_width),
        desired_host_viewport=SurfaceDimensions(desired_height, desired_width),
    )


def exact_authority(policy: HostSizingPolicy, authority_id: str = "window-1"):
    return policy.observe_authority(
        HostSizingAuthorityStatus.EXACT,
        authority_id=authority_id,
    )


def apply_ready_policy(
    *,
    desired_height: float = 790,
    config: HostSizingPolicyConfig | None = None,
) -> tuple[HostSizingPolicy, FakeClock, HostSizingDecision]:
    clock = FakeClock()
    policy = HostSizingPolicy(config=config, clock=clock)
    exact_authority(policy)
    policy.observe_report(report(desired_height=desired_height))
    clock.advance((config or HostSizingPolicyConfig()).quiet_period_seconds)
    return policy, clock, policy.evaluate()


def test_policy_defaults_are_internal_initial_fit_values():
    config = HostSizingPolicyConfig()

    assert config.quiet_period_seconds == HOST_SIZING_QUIET_PERIOD_SECONDS == 0.25
    assert config.timeout_seconds == HOST_SIZING_TIMEOUT_SECONDS == 5.0
    assert config.effective_min_viewport_height == 320
    assert config.effective_max_viewport_height == 4096


def test_policy_preserves_authenticated_device_pixel_ratio_in_decision():
    clock = FakeClock()
    policy = HostSizingPolicy(
        config=HostSizingPolicyConfig(quiet_period_seconds=0),
        clock=clock,
    )
    exact_authority(policy)

    decision = policy.observe_report(report(device_pixel_ratio=1.5))

    assert decision.action == HostSizingAction.APPLY
    assert decision.device_pixel_ratio == 1.5


@pytest.mark.parametrize(
    "kwargs",
    [
        {"quiet_period_seconds": -0.1},
        {"quiet_period_seconds": float("nan")},
        {"timeout_seconds": 0},
        {"timeout_seconds": float("inf")},
        {"min_viewport_height": True},
        {"max_viewport_height": 0},
        {"min_viewport_height": 900, "max_viewport_height": 800},
        {"min_viewport_height": 5000},
        {"max_viewport_height": 100},
    ],
)
def test_policy_rejects_invalid_internal_configuration(kwargs):
    with pytest.raises(HostSizingPolicyError):
        HostSizingPolicyConfig(**kwargs)


def test_policy_waits_independently_for_report_and_authority():
    policy = HostSizingPolicy(clock=FakeClock())

    assert policy.evaluate().action == HostSizingAction.WAIT
    report_decision = policy.observe_report(report())

    assert report_decision.action == HostSizingAction.WAIT
    assert "stabilization" in report_decision.reason
    assert policy.evaluate().action == HostSizingAction.WAIT


def test_policy_applies_after_one_report_and_quiet_period_without_duplicates():
    policy, clock, decision = apply_ready_policy()

    assert clock.value == 0.25
    assert decision.action == HostSizingAction.APPLY
    assert decision.state == HostSizingPolicyState.APPLY_PENDING
    assert decision.desired_viewport_height == 790
    assert decision.requested_viewport_height == 790
    assert decision.current_viewport_height == 812
    assert decision.authority_id == "window-1"
    assert decision.source_id == "primary-surface"
    assert decision.sequence == 1
    assert policy.snapshot().apply_decisions == 1


def test_policy_consumes_the_typed_report_retained_by_ll_hs1():
    clock = FakeClock()
    store = HostSizingReportStore()
    accepted_report = report()
    assert store.accept(accepted_report).accepted is True
    retained = store.snapshot().latest_report
    assert retained is not None
    policy = HostSizingPolicy(clock=clock)
    exact_authority(policy)

    policy.observe_report(retained)
    clock.advance(0.25)

    assert policy.evaluate().action == HostSizingAction.APPLY


def test_authority_can_arrive_after_report_stabilizes():
    clock = FakeClock()
    policy = HostSizingPolicy(clock=clock)
    policy.observe_report(report())
    clock.advance(0.25)

    assert policy.evaluate().action == HostSizingAction.WAIT
    decision = exact_authority(policy)

    assert decision.action == HostSizingAction.APPLY


def test_material_content_height_change_restarts_quiet_period():
    clock = FakeClock()
    policy = HostSizingPolicy(clock=clock)
    exact_authority(policy)
    policy.observe_report(report())
    clock.advance(0.2)
    policy.observe_report(report(2, content_height=760))
    clock.advance(0.2)

    assert policy.evaluate().action == HostSizingAction.WAIT
    clock.advance(0.051)
    assert policy.evaluate().action == HostSizingAction.APPLY


def test_material_content_width_change_restarts_quiet_period():
    clock = FakeClock()
    policy = HostSizingPolicy(clock=clock)
    exact_authority(policy)
    policy.observe_report(report())
    clock.advance(0.2)
    policy.observe_report(report(2, content_width=1200))
    first_deadline = policy.snapshot().quiet_deadline

    assert first_deadline == pytest.approx(0.45)


def test_desired_height_change_restarts_quiet_period():
    clock = FakeClock()
    policy = HostSizingPolicy(clock=clock)
    exact_authority(policy)
    policy.observe_report(report())
    clock.advance(0.2)
    policy.observe_report(report(2, desired_height=840))

    assert policy.snapshot().quiet_deadline == pytest.approx(0.45)


def test_viewport_only_feedback_does_not_restart_stabilization():
    clock = FakeClock()
    policy = HostSizingPolicy(clock=clock)
    exact_authority(policy)
    policy.observe_report(report())
    original_deadline = policy.snapshot().quiet_deadline
    clock.advance(0.2)

    decision = policy.observe_report(report(2, viewport_height=900))

    assert decision.action == HostSizingAction.IGNORE
    assert policy.snapshot().quiet_deadline == original_deadline
    clock.advance(0.05)
    applied = policy.evaluate()
    assert applied.action == HostSizingAction.APPLY
    assert applied.current_viewport_height == 900
    assert applied.sequence == 2


def test_desired_width_only_feedback_is_ignored_by_height_only_policy():
    clock = FakeClock()
    policy = HostSizingPolicy(clock=clock)
    exact_authority(policy)
    policy.observe_report(report(desired_width=900))
    deadline = policy.snapshot().quiet_deadline
    clock.advance(0.1)

    decision = policy.observe_report(report(2, desired_width=1200))

    assert decision.action == HostSizingAction.IGNORE
    assert policy.snapshot().quiet_deadline == deadline


def test_stale_sequence_is_ignored_without_replacing_latest_report():
    policy = HostSizingPolicy(clock=FakeClock())
    policy.observe_report(report(2, desired_height=800))

    decision = policy.observe_report(report(1, desired_height=900))
    snapshot = policy.snapshot()

    assert decision.action == HostSizingAction.IGNORE
    assert snapshot.last_sequence == 2
    assert snapshot.latest_report == report(2, desired_height=800)


def test_source_authority_conflict_is_terminal():
    policy = HostSizingPolicy(clock=FakeClock())
    policy.observe_report(report())

    decision = policy.observe_report(report(2, source_id="secondary-surface"))

    assert decision.action == HostSizingAction.ABORT
    assert decision.state == HostSizingPolicyState.ABORTED
    assert "source authority conflict" in decision.reason


def test_launch_authority_conflict_is_terminal():
    policy = HostSizingPolicy(clock=FakeClock())
    policy.observe_report(report())

    decision = policy.observe_report(report(2, launch_id="different-launch-123456"))

    assert decision.action == HostSizingAction.ABORT
    assert decision.state == HostSizingPolicyState.ABORTED
    assert "launch authority" in decision.reason


@pytest.mark.parametrize(
    "status",
    [
        HostSizingAuthorityStatus.AMBIGUOUS,
        HostSizingAuthorityStatus.UNSUPPORTED,
        HostSizingAuthorityStatus.LOST,
    ],
)
def test_ineligible_authority_states_abort(status):
    policy = HostSizingPolicy(clock=FakeClock())

    decision = policy.observe_authority(status)

    assert decision.action == HostSizingAction.ABORT
    assert decision.state == HostSizingPolicyState.ABORTED


def test_pending_authority_waits_until_exact():
    policy = HostSizingPolicy(clock=FakeClock())

    decision = policy.observe_authority(HostSizingAuthorityStatus.PENDING)

    assert decision.action == HostSizingAction.WAIT
    assert policy.snapshot().authority_status == HostSizingAuthorityStatus.PENDING


def test_exact_authority_requires_a_bounded_opaque_identity():
    policy = HostSizingPolicy(clock=FakeClock())

    with pytest.raises(HostSizingPolicyError):
        exact_authority(policy, "")
    with pytest.raises(HostSizingPolicyError):
        exact_authority(policy, "x" * 257)


def test_exact_authority_identity_change_aborts():
    policy = HostSizingPolicy(clock=FakeClock())
    exact_authority(policy, "window-1")

    decision = exact_authority(policy, "window-2")

    assert decision.action == HostSizingAction.ABORT
    assert decision.state == HostSizingPolicyState.ABORTED


def test_exact_authority_returning_to_pending_aborts():
    policy = HostSizingPolicy(clock=FakeClock())
    exact_authority(policy)

    decision = policy.observe_authority(HostSizingAuthorityStatus.PENDING)

    assert decision.action == HostSizingAction.ABORT
    assert "lost" in decision.reason


def test_timeout_without_report_is_terminal():
    clock = FakeClock()
    policy = HostSizingPolicy(clock=clock)
    clock.advance(5.0)

    decision = policy.evaluate()

    assert decision.action == HostSizingAction.ABORT
    assert decision.state == HostSizingPolicyState.TIMED_OUT


def test_timeout_while_waiting_for_authority_is_terminal():
    clock = FakeClock()
    policy = HostSizingPolicy(clock=clock)
    policy.observe_report(report())
    clock.advance(5.0)

    assert policy.evaluate().state == HostSizingPolicyState.TIMED_OUT


def test_timeout_while_stabilizing_is_terminal():
    clock = FakeClock()
    config = HostSizingPolicyConfig(quiet_period_seconds=10, timeout_seconds=5)
    policy = HostSizingPolicy(config=config, clock=clock)
    exact_authority(policy)
    policy.observe_report(report())
    clock.advance(5)

    assert policy.evaluate().state == HostSizingPolicyState.TIMED_OUT


def test_apply_pending_expires_at_overall_deadline():
    policy, clock, decision = apply_ready_policy()
    assert decision.action == HostSizingAction.APPLY
    clock.advance(4.75)

    expired = policy.evaluate()

    assert expired.action == HostSizingAction.ABORT
    assert expired.state == HostSizingPolicyState.TIMED_OUT


def test_late_apply_acknowledgement_fails_closed_at_deadline():
    policy, clock, _decision = apply_ready_policy()
    clock.advance(4.75)

    result = policy.acknowledge_apply(applied=True)

    assert result.state == HostSizingPolicyState.TIMED_OUT


def test_shutdown_cancels_waiting_policy():
    policy = HostSizingPolicy(clock=FakeClock())

    decision = policy.shutdown()

    assert decision.action == HostSizingAction.ABORT
    assert decision.state == HostSizingPolicyState.SHUT_DOWN
    assert policy.evaluate().action == HostSizingAction.IGNORE


def test_shutdown_cancels_pending_apply_before_collaborator_acknowledgement():
    policy, _clock, decision = apply_ready_policy()
    assert decision.action == HostSizingAction.APPLY

    cancelled = policy.shutdown()

    assert cancelled.state == HostSizingPolicyState.SHUT_DOWN
    with pytest.raises(HostSizingPolicyError):
        policy.acknowledge_apply(applied=True)


def test_external_safety_gate_can_abort_with_reason():
    policy = HostSizingPolicy(clock=FakeClock())

    decision = policy.abort("Window geometry changed during stabilization.")

    assert decision.action == HostSizingAction.ABORT
    assert decision.reason == "Window geometry changed during stabilization."
    assert policy.snapshot().terminal_reason == decision.reason


def test_external_abort_requires_a_reason():
    policy = HostSizingPolicy(clock=FakeClock())

    with pytest.raises(HostSizingPolicyError):
        policy.abort("  ")


@pytest.mark.parametrize(
    ("desired", "expected", "reasons"),
    [
        (100, HOST_SIZING_HARD_MIN_VIEWPORT_HEIGHT, ("hard_minimum",)),
        (8000, HOST_SIZING_HARD_MAX_VIEWPORT_HEIGHT, ("hard_maximum",)),
    ],
)
def test_apply_decision_enforces_hard_viewport_bounds(desired, expected, reasons):
    _policy, _clock, decision = apply_ready_policy(desired_height=desired)

    assert decision.desired_viewport_height == expected
    assert decision.clamp_reasons == reasons


@pytest.mark.parametrize(
    ("desired", "expected", "reasons"),
    [
        (100, 480, ("hard_minimum", "configured_minimum")),
        (1600, 1200, ("configured_maximum",)),
    ],
)
def test_apply_decision_enforces_internal_configured_bounds(
    desired,
    expected,
    reasons,
):
    config = HostSizingPolicyConfig(
        min_viewport_height=480,
        max_viewport_height=1200,
    )
    _policy, _clock, decision = apply_ready_policy(
        desired_height=desired,
        config=config,
    )

    assert decision.desired_viewport_height == expected
    assert decision.clamp_reasons == reasons


def test_desired_height_uses_predictable_half_up_integer_normalization():
    _policy, _clock, decision = apply_ready_policy(desired_height=790.5)

    assert decision.requested_viewport_height == 791
    assert decision.desired_viewport_height == 791


@pytest.mark.parametrize("delta", [0, 0.5, HOST_SIZING_MINIMUM_VIEWPORT_DELTA])
def test_target_within_minimum_viewport_delta_completes_without_apply(delta):
    desired = 812 + delta
    policy, _clock, decision = apply_ready_policy(desired_height=desired)

    assert decision.action == HostSizingAction.COMPLETE
    assert decision.state == HostSizingPolicyState.COMPLETE
    assert policy.snapshot().apply_decisions == 0


def test_target_beyond_minimum_viewport_delta_emits_apply():
    _policy, _clock, decision = apply_ready_policy(desired_height=813.5)

    assert decision.action == HostSizingAction.APPLY


def test_fake_mutation_collaborator_completes_exactly_one_apply():
    policy, _clock, decision = apply_ready_policy()
    collaborator = FakeMutationCollaborator()

    applied = collaborator.apply(decision)
    completed = policy.acknowledge_apply(applied=applied)

    assert completed.action == HostSizingAction.COMPLETE
    assert completed.state == HostSizingPolicyState.COMPLETE
    assert len(collaborator.decisions) == 1
    assert policy.snapshot().apply_decisions == 1
    assert policy.evaluate().action == HostSizingAction.IGNORE
    assert policy.observe_report(report(2)).action == HostSizingAction.IGNORE


def test_fake_mutation_collaborator_failure_aborts_policy():
    policy, _clock, decision = apply_ready_policy()
    collaborator = FakeMutationCollaborator(succeeds=False)

    applied = collaborator.apply(decision)
    completed = policy.acknowledge_apply(
        applied=applied,
        reason="Fake mutation collaborator rejected the decision.",
    )

    assert completed.action == HostSizingAction.ABORT
    assert completed.state == HostSizingPolicyState.ABORTED
    assert len(collaborator.decisions) == 1


def test_apply_decision_waits_for_explicit_acknowledgement():
    policy, _clock, decision = apply_ready_policy()

    assert decision.action == HostSizingAction.APPLY
    waiting = policy.evaluate()

    assert waiting.action == HostSizingAction.WAIT
    assert waiting.state == HostSizingPolicyState.APPLY_PENDING
    assert policy.snapshot().apply_decisions == 1


def test_apply_acknowledgement_without_pending_decision_is_programmer_error():
    policy = HostSizingPolicy(clock=FakeClock())

    with pytest.raises(HostSizingPolicyError):
        policy.acknowledge_apply(applied=True)


def test_concurrent_reports_leave_highest_sequence_as_authority():
    clock = FakeClock()
    policy = HostSizingPolicy(clock=clock)
    reports = [
        report(sequence, desired_height=700 + sequence) for sequence in range(1, 51)
    ]

    with ThreadPoolExecutor(max_workers=8) as executor:
        tuple(executor.map(policy.observe_report, reports))

    snapshot = policy.snapshot()
    assert snapshot.last_sequence == 50
    assert snapshot.latest_report == report(50, desired_height=750)
    assert snapshot.bound_source_id == "primary-surface"


def test_monotonic_clock_regression_fails_closed_as_programmer_error():
    clock = FakeClock(10)
    policy = HostSizingPolicy(clock=clock)
    clock.value = 9

    with pytest.raises(HostSizingPolicyError):
        policy.evaluate()


def test_decisions_and_snapshots_are_immutable():
    policy, _clock, decision = apply_ready_policy()
    snapshot = policy.snapshot()

    with pytest.raises(FrozenInstanceError):
        decision.reason = "changed"
    with pytest.raises(FrozenInstanceError):
        snapshot.state = HostSizingPolicyState.ABORTED


def test_policy_accepts_only_typed_validated_reports():
    policy = HostSizingPolicy(clock=FakeClock())

    with pytest.raises(TypeError):
        policy.observe_report({"desired_host_viewport": {"height": 800}})  # type: ignore[arg-type]


def test_policy_remains_private_and_has_no_transport_or_native_behavior():
    source = Path(policy_module.__file__).read_text(encoding="utf-8")

    assert not hasattr(litlaunch, "HostSizingPolicy")
    assert "parse_host_sizing_report" not in source
    assert "start_host_sizing_channel" not in source
    assert "WindowsGeometryBackend" not in source
    assert "SetWindowPos" not in source
    assert "WindowSizer" not in source
    assert "BaseHTTPRequestHandler" not in source
    assert "ctypes" not in source
    assert "import json" not in source
