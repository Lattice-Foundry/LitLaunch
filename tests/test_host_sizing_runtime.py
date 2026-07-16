from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path

import pytest

import litlaunch
import litlaunch._host_sizing_runtime as runtime_module
from litlaunch._host_sizing_geometry import (
    GeometryProbeError,
    NativeRect,
    WindowGeometry,
    WindowGeometryState,
)
from litlaunch._host_sizing_policy import (
    HostSizingAction,
    HostSizingPolicy,
    HostSizingPolicyConfig,
    HostSizingPolicyState,
)
from litlaunch._host_sizing_runtime import HostSizingRuntimeCoordinator
from litlaunch._host_sizing_transport import (
    HOST_SIZING_TOKEN_HEADER,
    HostSizingReport,
    SurfaceDimensions,
    start_host_sizing_channel,
)
from litlaunch._host_sizing_window import (
    HostSizingMutationResult,
    HostSizingMutationStatus,
    TrustedWindowsWindowSizer,
    WindowAuthorityVerification,
    WindowSizingAuthority,
)
from litlaunch.browsers import BrowserKind
from litlaunch.windowing import WindowInfo

ALLOWED_ORIGIN = "http://127.0.0.1:8501"


def geometry(
    *,
    outer: NativeRect | None = None,
    client_width: int = 984,
    client_height: int = 761,
    dpi: int = 96,
    state: WindowGeometryState = WindowGeometryState.NORMAL,
) -> WindowGeometry:
    return WindowGeometry(
        handle=100,
        outer=outer or NativeRect(100, 100, 1100, 900),
        client_width=client_width,
        client_height=client_height,
        dpi=dpi,
        monitor_handle=1,
        monitor=NativeRect(0, 0, 2560, 1440),
        work_area=NativeRect(0, 0, 2560, 1400),
        show_command=1,
        state=state,
    )


def authority(*, baseline: WindowGeometry | None = None) -> WindowSizingAuthority:
    current = baseline or geometry()
    return WindowSizingAuthority(
        authority_id="window-authority-1",
        handle=current.handle,
        browser_kind=BrowserKind.EDGE,
        process_id=400,
        launch_process_ids=frozenset({400, 401}),
        stable_polls=3,
        baseline=current,
        managed_profile=True,
        app_mode=True,
    )


class MutableGeometryBackend:
    def __init__(
        self,
        baseline: WindowGeometry,
        *,
        set_error: bool = False,
    ) -> None:
        self.current = baseline
        self.set_error = set_error
        self.set_calls: list[tuple[int, int, int]] = []

    def capture(self, handle: int) -> WindowGeometry:
        assert handle == self.current.handle
        return self.current

    def set_outer_size(self, handle: int, *, width: int, height: int) -> None:
        self.set_calls.append((handle, width, height))
        if self.set_error:
            raise GeometryProbeError("fake native failure")
        outer_delta = height - self.current.outer.height
        self.current = replace(
            self.current,
            outer=replace(
                self.current.outer,
                right=self.current.outer.left + width,
                bottom=self.current.outer.top + height,
            ),
            client_height=self.current.client_height + outer_delta,
        )


class FakeAuthorityVerifier:
    def __init__(self, *, exact: bool = True) -> None:
        self.exact = exact
        self.calls = 0

    def verify(self, _authority: WindowSizingAuthority):
        self.calls += 1
        return WindowAuthorityVerification(
            self.exact,
            "exact" if self.exact else "authority lost",
            WindowInfo(
                "100",
                title="Product",
                class_name="Chrome_WidgetWin_1",
                pid=400,
                process_name="msedge",
            ),
        )


class FakeMutationCapability:
    def __init__(self) -> None:
        self.decisions = []

    def apply(self, *, decision, authority):
        self.decisions.append(decision)
        return HostSizingMutationResult(
            status=HostSizingMutationStatus.APPLIED,
            reason="fake mutation applied",
            decision=decision,
            authority_id=authority.authority_id,
            baseline=authority.baseline,
            pre_apply=authority.baseline,
            after=authority.baseline,
            plan=None,
            mutation_attempted=True,
        )


class FakeTrustedTransport:
    def __init__(self, consumer) -> None:
        self.consumer = consumer

    def submit(self, value: HostSizingReport, *, accepted: bool):
        if not accepted:
            return None
        return self.consumer(value)


class AcknowledgementFailurePolicy(HostSizingPolicy):
    def acknowledge_apply(self, *, applied, reason=None):
        raise RuntimeError("fake acknowledgement failure")


def sizer(
    baseline: WindowGeometry,
    *,
    exact: bool = True,
    set_error: bool = False,
):
    backend = MutableGeometryBackend(baseline, set_error=set_error)
    capability = TrustedWindowsWindowSizer(
        backend=backend,
        authority_verifier=FakeAuthorityVerifier(exact=exact),
    )
    return capability, backend


def report(
    *,
    sequence: int = 1,
    launch_id: str = "launch-authority-123456",
    current_height: float = 761,
    desired_height: float = 900,
    device_pixel_ratio: float = 1.0,
) -> HostSizingReport:
    return HostSizingReport(
        protocol=1,
        launch_id=launch_id,
        source_id="primary-surface",
        sequence=sequence,
        device_pixel_ratio=device_pixel_ratio,
        content=SurfaceDimensions(current_height, 984),
        host_viewport=SurfaceDimensions(current_height, 984),
        desired_host_viewport=SurfaceDimensions(desired_height),
    )


def test_coordinator_aborts_terminally_when_policy_acknowledgement_raises():
    mutation = FakeMutationCapability()
    coordinator = HostSizingRuntimeCoordinator(
        policy=AcknowledgementFailurePolicy(
            config=HostSizingPolicyConfig(quiet_period_seconds=0)
        ),
        mutation=mutation,
        authority=authority(),
    )

    decision = coordinator.consume_accepted_report(report())
    snapshot = coordinator.snapshot()

    assert decision.state == HostSizingPolicyState.ABORTED
    assert snapshot.policy_state == HostSizingPolicyState.ABORTED
    assert snapshot.mutation_calls == 1
    assert snapshot.acknowledgements == 1
    assert snapshot.failure_reason == (
        "Host-sizing policy acknowledgement failed unexpectedly."
    )


def payload(
    coordinator: HostSizingRuntimeCoordinator,
    *,
    sequence: int = 1,
    current_height: float = 761,
    desired_height: float = 900,
    device_pixel_ratio: float = 1.0,
) -> dict[str, object]:
    config = coordinator.channel_config
    assert config is not None
    return {
        "protocol": 1,
        "launch_id": config.launch_id,
        "source_id": "primary-surface",
        "sequence": sequence,
        "device_pixel_ratio": device_pixel_ratio,
        "content": {"height": current_height, "width": 984},
        "host_viewport": {"height": current_height, "width": 984},
        "desired_host_viewport": {"height": desired_height},
    }


def send(
    coordinator: HostSizingRuntimeCoordinator,
    body: dict[str, object],
    *,
    token: str | None = None,
) -> int:
    config = coordinator.channel_config
    assert config is not None
    request = urllib.request.Request(
        config.endpoint,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Origin": ALLOWED_ORIGIN,
            HOST_SIZING_TOKEN_HEADER: token or config.token,
            "Content-Type": "application/json",
        },
    )
    try:
        response = urllib.request.urlopen(request, timeout=2.0)
    except urllib.error.HTTPError as exc:
        exc.read()
        status = exc.code
        exc.close()
        return status
    response.read()
    status = response.status
    response.close()
    return status


def start_runtime(
    *,
    baseline: WindowGeometry | None = None,
    config: HostSizingPolicyConfig | None = None,
    exact: bool = True,
    set_error: bool = False,
):
    initial = baseline or geometry()
    capability, backend = sizer(initial, exact=exact, set_error=set_error)
    coordinator = HostSizingRuntimeCoordinator(
        policy=HostSizingPolicy(
            config=config or HostSizingPolicyConfig(quiet_period_seconds=0)
        ),
        authority=authority(baseline=initial),
        mutation=capability,
        poll_interval_seconds=0.005,
    )
    channel = start_host_sizing_channel(
        allowed_origin=ALLOWED_ORIGIN,
        accepted_report_callback=coordinator.consume_accepted_report,
    )
    coordinator.attach_channel(channel)
    coordinator.start()
    return coordinator, backend


def test_authenticated_report_runs_one_complete_private_pipeline():
    coordinator, backend = start_runtime()
    try:
        assert send(coordinator, payload(coordinator)) == 202
        assert coordinator.wait(1.0) is True
        snapshot = coordinator.snapshot()
    finally:
        coordinator.close()

    assert snapshot.policy_state == HostSizingPolicyState.COMPLETE
    assert snapshot.accepted_reports == 1
    assert snapshot.mutation_calls == 1
    assert snapshot.acknowledgements == 1
    assert snapshot.apply_decision is not None
    assert snapshot.apply_decision.sequence == 1
    assert snapshot.apply_decision.device_pixel_ratio == 1.0
    assert snapshot.mutation_result is not None
    assert snapshot.mutation_result.applied is True
    assert snapshot.channel_active is False
    assert backend.set_calls == [(100, 1000, 939)]


def test_fake_transport_and_fake_mutation_prove_coordinator_contract():
    baseline = geometry()
    mutation = FakeMutationCapability()
    coordinator = HostSizingRuntimeCoordinator(
        policy=HostSizingPolicy(config=HostSizingPolicyConfig(quiet_period_seconds=0)),
        mutation=mutation,
        authority=authority(baseline=baseline),
    )
    transport = FakeTrustedTransport(coordinator.consume_accepted_report)

    assert transport.submit(report(), accepted=False) is None
    completed = transport.submit(report(), accepted=True)
    snapshot = coordinator.snapshot()
    coordinator.close()

    assert completed is not None
    assert completed.action == HostSizingAction.COMPLETE
    assert len(mutation.decisions) == 1
    assert snapshot.accepted_reports == 1
    assert snapshot.mutation_calls == 1
    assert snapshot.acknowledgements == 1


def test_transport_rejection_never_reaches_policy_or_mutation():
    coordinator, backend = start_runtime(
        config=HostSizingPolicyConfig(
            quiet_period_seconds=0,
            timeout_seconds=1,
        )
    )
    try:
        assert send(coordinator, payload(coordinator), token="x" * 40) == 403
        snapshot = coordinator.snapshot()
    finally:
        coordinator.close()

    assert snapshot.accepted_reports == 0
    assert snapshot.policy_state == HostSizingPolicyState.WAITING
    assert snapshot.mutation_calls == 0
    assert backend.set_calls == []


def test_noop_policy_completion_never_calls_mutation():
    coordinator, backend = start_runtime()
    try:
        assert (
            send(
                coordinator,
                payload(coordinator, desired_height=761),
            )
            == 202
        )
        assert coordinator.wait(1.0) is True
        snapshot = coordinator.snapshot()
    finally:
        coordinator.close()

    assert snapshot.policy_state == HostSizingPolicyState.COMPLETE
    assert snapshot.mutation_calls == 0
    assert snapshot.acknowledgements == 0
    assert backend.set_calls == []


def test_policy_clamp_flows_to_one_bounded_mutation():
    coordinator, backend = start_runtime(
        config=HostSizingPolicyConfig(
            quiet_period_seconds=0,
            max_viewport_height=850,
        )
    )
    try:
        assert send(coordinator, payload(coordinator)) == 202
        assert coordinator.wait(1.0) is True
        snapshot = coordinator.snapshot()
    finally:
        coordinator.close()

    assert snapshot.policy_state == HostSizingPolicyState.COMPLETE
    assert snapshot.apply_decision is not None
    assert snapshot.apply_decision.desired_viewport_height == 850
    assert snapshot.apply_decision.clamp_reasons == ("configured_maximum",)
    assert backend.set_calls == [(100, 1000, 889)]


@pytest.mark.parametrize(
    ("exact", "set_error"),
    [(False, False), (True, True)],
)
def test_authority_and_native_failures_abort_without_retry(exact, set_error):
    coordinator, backend = start_runtime(exact=exact, set_error=set_error)
    try:
        assert send(coordinator, payload(coordinator)) == 202
        assert coordinator.wait(1.0) is True
        snapshot = coordinator.snapshot()
    finally:
        coordinator.close()

    assert snapshot.policy_state == HostSizingPolicyState.ABORTED
    assert snapshot.mutation_calls == 1
    assert snapshot.acknowledgements == 1
    assert snapshot.mutation_result is not None
    assert snapshot.mutation_result.acknowledgement_succeeded is False
    assert len(backend.set_calls) == int(set_error)


def test_geometry_drift_aborts_before_native_mutation():
    baseline = geometry()
    drifted = replace(
        baseline,
        outer=replace(baseline.outer, bottom=baseline.outer.bottom + 20),
        client_height=baseline.client_height + 20,
    )
    backend = MutableGeometryBackend(drifted)
    capability = TrustedWindowsWindowSizer(
        backend=backend,
        authority_verifier=FakeAuthorityVerifier(),
    )
    coordinator = HostSizingRuntimeCoordinator(
        policy=HostSizingPolicy(config=HostSizingPolicyConfig(quiet_period_seconds=0)),
        mutation=capability,
        authority=authority(baseline=baseline),
    )

    completed = coordinator.consume_accepted_report(report())
    snapshot = coordinator.snapshot()
    coordinator.close()

    assert completed.action == HostSizingAction.ABORT
    assert snapshot.policy_state == HostSizingPolicyState.ABORTED
    assert snapshot.mutation_result is not None
    assert snapshot.mutation_result.status == HostSizingMutationStatus.REFUSED
    assert backend.set_calls == []


def test_newest_report_wins_and_stale_report_cannot_trigger_a_second_apply():
    coordinator, backend = start_runtime(
        config=HostSizingPolicyConfig(quiet_period_seconds=0.05)
    )
    try:
        assert (
            send(
                coordinator,
                payload(coordinator, sequence=1, desired_height=850),
            )
            == 202
        )
        assert (
            send(
                coordinator,
                payload(coordinator, sequence=2, desired_height=900),
            )
            == 202
        )
        assert (
            send(
                coordinator,
                payload(coordinator, sequence=1, desired_height=700),
            )
            == 409
        )
        assert coordinator.wait(1.0) is True
        snapshot = coordinator.snapshot()
    finally:
        coordinator.close()

    assert snapshot.apply_decision is not None
    assert snapshot.apply_decision.sequence == 2
    assert snapshot.apply_decision.desired_viewport_height == 900
    assert snapshot.mutation_calls == 1
    assert snapshot.acknowledgements == 1
    assert backend.set_calls == [(100, 1000, 939)]


def test_timeout_closes_pipeline_without_mutation():
    coordinator, backend = start_runtime(
        config=HostSizingPolicyConfig(
            quiet_period_seconds=0,
            timeout_seconds=0.05,
        )
    )
    try:
        assert coordinator.wait(1.0) is True
        snapshot = coordinator.snapshot()
    finally:
        coordinator.close()

    assert snapshot.policy_state == HostSizingPolicyState.TIMED_OUT
    assert snapshot.mutation_calls == 0
    assert snapshot.channel_active is False
    assert backend.set_calls == []


def test_shutdown_before_stabilization_cancels_without_mutation():
    coordinator, backend = start_runtime(
        config=HostSizingPolicyConfig(quiet_period_seconds=1)
    )
    assert send(coordinator, payload(coordinator)) == 202

    decision = coordinator.shutdown()
    snapshot = coordinator.snapshot()

    assert decision.state == HostSizingPolicyState.SHUT_DOWN
    assert snapshot.policy_state == HostSizingPolicyState.SHUT_DOWN
    assert snapshot.mutation_calls == 0
    assert snapshot.channel_active is False
    assert backend.set_calls == []


def test_report_after_completion_is_ignored_without_retry():
    baseline = geometry()
    capability, backend = sizer(baseline)
    coordinator = HostSizingRuntimeCoordinator(
        policy=HostSizingPolicy(config=HostSizingPolicyConfig(quiet_period_seconds=0)),
        mutation=capability,
        authority=authority(baseline=baseline),
    )

    first = coordinator.consume_accepted_report(report())
    second = coordinator.consume_accepted_report(report(sequence=2))
    snapshot = coordinator.snapshot()
    coordinator.close()

    assert first.action == HostSizingAction.COMPLETE
    assert second.action == HostSizingAction.IGNORE
    assert snapshot.accepted_reports == 2
    assert snapshot.mutation_calls == 1
    assert snapshot.acknowledgements == 1
    assert backend.set_calls == [(100, 1000, 939)]


def test_authenticated_dpr_reaches_native_conversion_unchanged():
    baseline = replace(
        geometry(
            outer=NativeRect(100, 100, 1900, 1300),
            client_width=1768,
            client_height=1144,
            dpi=144,
        ),
        monitor=NativeRect(0, 0, 3840, 2160),
        work_area=NativeRect(0, 0, 3840, 2080),
    )
    coordinator, backend = start_runtime(baseline=baseline)
    try:
        assert (
            send(
                coordinator,
                payload(
                    coordinator,
                    current_height=763,
                    desired_height=900,
                    device_pixel_ratio=1.5,
                ),
            )
            == 202
        )
        assert coordinator.wait(1.0) is True
        snapshot = coordinator.snapshot()
    finally:
        coordinator.close()

    assert snapshot.apply_decision is not None
    assert snapshot.apply_decision.device_pixel_ratio == 1.5
    assert backend.set_calls == [(100, 1800, 1406)]


def test_runtime_coordinator_remains_private_and_has_no_activation_shortcut():
    runtime_source = Path(runtime_module.__file__).read_text(encoding="utf-8")

    assert not hasattr(litlaunch, "HostSizingRuntimeCoordinator")
    assert "class HostSizingRuntimeCoordinator" in runtime_source
    assert "start_host_sizing_channel" not in runtime_source
