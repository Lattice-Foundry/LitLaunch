from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

import litlaunch
import litlaunch._host_sizing_window as window_module
from litlaunch._host_sizing_geometry import (
    SWP_NOACTIVATE,
    SWP_NOMOVE,
    SWP_NOOWNERZORDER,
    SWP_NOZORDER,
    GeometryProbeError,
    NativeRect,
    WindowAuthorityProbe,
    WindowAuthorityStatus,
    WindowGeometry,
    WindowGeometryState,
    WindowsGeometryBackend,
)
from litlaunch._host_sizing_policy import (
    HostSizingAction,
    HostSizingAuthorityStatus,
    HostSizingPolicy,
    HostSizingPolicyConfig,
    HostSizingPolicyMode,
    HostSizingPolicyState,
)
from litlaunch._host_sizing_transport import HostSizingReport, SurfaceDimensions
from litlaunch._host_sizing_window import (
    HostSizingMutationStatus,
    HostSizingWindowError,
    TrustedWindowsWindowSizer,
    WindowAuthorityVerification,
    WindowSizingAuthority,
    WindowSizingLifetime,
    WindowsWindowAuthorityVerifier,
    create_window_sizing_authority,
)
from litlaunch.browsers import BrowserKind
from litlaunch.windowing import WindowInfo


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class FakeGeometryBackend:
    def __init__(
        self,
        *snapshots: WindowGeometry,
        capture_error_at: int | None = None,
        set_error: bool = False,
    ) -> None:
        self.snapshots = list(snapshots)
        self.capture_error_at = capture_error_at
        self.set_error = set_error
        self.capture_calls = 0
        self.set_calls: list[tuple[int, int, int]] = []

    def capture(self, handle: int) -> WindowGeometry:
        self.capture_calls += 1
        if self.capture_error_at == self.capture_calls:
            raise GeometryProbeError("fake capture failure")
        if not self.snapshots:
            raise AssertionError("No fake geometry snapshot remains.")
        return self.snapshots.pop(0)

    def set_outer_size(self, handle: int, *, width: int, height: int) -> None:
        self.set_calls.append((handle, width, height))
        if self.set_error:
            raise GeometryProbeError("fake mutation failure")


class FakeAuthorityVerifier:
    def __init__(self, *results: WindowAuthorityVerification) -> None:
        self.results = list(results) or [
            WindowAuthorityVerification(True, "exact", window())
        ]
        self.calls = 0

    def verify(self, authority: WindowSizingAuthority) -> WindowAuthorityVerification:
        self.calls += 1
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]


class FakeWindowProvider:
    is_windows = True

    def __init__(self, *windows: WindowInfo, error: bool = False) -> None:
        self.windows = windows
        self.error = error

    def capture(self) -> tuple[WindowInfo, ...]:
        if self.error:
            raise OSError("fake provider failure")
        return self.windows


def window(
    handle: str = "100",
    *,
    pid: int = 400,
    process_name: str = "msedge",
    class_name: str = "Chrome_WidgetWin_1",
) -> WindowInfo:
    return WindowInfo(
        handle,
        title="Product",
        class_name=class_name,
        pid=pid,
        process_name=process_name,
    )


def geometry(
    *,
    outer: NativeRect | None = None,
    client_width: int = 984,
    client_height: int = 761,
    dpi: int = 96,
    monitor_handle: int = 1,
    monitor: NativeRect | None = None,
    work_area: NativeRect | None = None,
    show_command: int = 1,
    state: WindowGeometryState = WindowGeometryState.NORMAL,
) -> WindowGeometry:
    return WindowGeometry(
        handle=100,
        outer=outer or NativeRect(100, 100, 1100, 900),
        client_width=client_width,
        client_height=client_height,
        dpi=dpi,
        monitor_handle=monitor_handle,
        monitor=monitor or NativeRect(0, 0, 1920, 1080),
        work_area=work_area or NativeRect(0, 0, 1920, 1040),
        show_command=show_command,
        state=state,
    )


def probe(
    *,
    status: WindowAuthorityStatus = WindowAuthorityStatus.EXACT,
    observed: WindowInfo | None = None,
    stable_polls: int = 3,
) -> WindowAuthorityProbe:
    selected = observed if observed is not None else window()
    return WindowAuthorityProbe(
        status=status,
        window=selected if status == WindowAuthorityStatus.EXACT else None,
        candidates=(selected,) if status == WindowAuthorityStatus.EXACT else (),
        reason="fake authority",
        stable_polls=stable_polls,
    )


def authority(
    *,
    baseline: WindowGeometry | None = None,
    browser_kind: BrowserKind = BrowserKind.EDGE,
    authority_id: str = "window-authority-1",
) -> WindowSizingAuthority:
    process_name = "msedge" if browser_kind == BrowserKind.EDGE else "chrome"
    return create_window_sizing_authority(
        authority_id=authority_id,
        probe=probe(observed=window(process_name=process_name)),
        browser_kind=browser_kind,
        launch_process_ids=(400, 401),
        baseline=baseline or geometry(),
        managed_profile=True,
        app_mode=True,
    )


def pending_policy_decision(
    *,
    current_height: float = 761,
    desired_height: float = 900,
    device_pixel_ratio: float = 1.0,
    authority_id: str = "window-authority-1",
):
    clock = FakeClock()
    policy = HostSizingPolicy(
        config=HostSizingPolicyConfig(quiet_period_seconds=0),
        clock=clock,
    )
    policy.observe_authority(
        HostSizingAuthorityStatus.EXACT,
        authority_id=authority_id,
    )
    decision = policy.observe_report(
        HostSizingReport(
            protocol=1,
            launch_id="launch-authority-123456",
            source_id="primary-surface",
            sequence=1,
            device_pixel_ratio=device_pixel_ratio,
            content=SurfaceDimensions(742, 1180),
            host_viewport=SurfaceDimensions(current_height, 1280),
            desired_host_viewport=SurfaceDimensions(desired_height),
        )
    )
    assert decision.action == HostSizingAction.APPLY
    return policy, decision


def after_height(height: int, *, base: WindowGeometry | None = None) -> WindowGeometry:
    source = base or geometry()
    return replace(
        source,
        outer=replace(source.outer, bottom=source.outer.top + height),
        client_height=source.client_height + (height - source.outer.height),
    )


def test_exact_probe_promotes_to_immutable_window_authority():
    baseline = geometry()

    result = authority(baseline=baseline)

    assert result.handle == 100
    assert result.process_id == 400
    assert result.launch_process_ids == frozenset({400, 401})
    assert result.stable_polls == 3
    assert result.baseline is baseline
    assert result.managed_profile is True
    assert result.app_mode is True


@pytest.mark.parametrize(
    "bad_probe",
    [
        probe(status=WindowAuthorityStatus.NONE),
        probe(status=WindowAuthorityStatus.AMBIGUOUS),
        probe(status=WindowAuthorityStatus.UNSUPPORTED),
        probe(stable_polls=2),
    ],
)
def test_authority_factory_rejects_nonexact_or_unstable_probe(bad_probe):
    with pytest.raises(HostSizingWindowError):
        create_window_sizing_authority(
            authority_id="authority",
            probe=bad_probe,
            browser_kind=BrowserKind.EDGE,
            launch_process_ids=(400,),
            baseline=geometry(),
            managed_profile=True,
            app_mode=True,
        )


@pytest.mark.parametrize(
    "observed",
    [
        window(process_name="chrome"),
        window(class_name="OtherWindowClass"),
        window(pid=999),
    ],
)
def test_authority_factory_rejects_wrong_browser_class_or_process(observed):
    with pytest.raises(HostSizingWindowError):
        create_window_sizing_authority(
            authority_id="authority",
            probe=probe(observed=observed),
            browser_kind=BrowserKind.EDGE,
            launch_process_ids=(400,),
            baseline=geometry(),
            managed_profile=True,
            app_mode=True,
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"authority_id": ""},
        {"handle": 0},
        {"browser_kind": BrowserKind.DEFAULT},
        {"process_id": 999},
        {"launch_process_ids": frozenset({400, -1})},
        {"stable_polls": 2},
        {"managed_profile": False},
        {"app_mode": False},
    ],
)
def test_window_authority_rejects_incomplete_or_unsafe_proof(overrides):
    values = {
        "authority_id": "authority",
        "handle": 100,
        "browser_kind": BrowserKind.EDGE,
        "process_id": 400,
        "launch_process_ids": frozenset({400}),
        "stable_polls": 3,
        "baseline": geometry(),
        "managed_profile": True,
        "app_mode": True,
    }
    values.update(overrides)

    with pytest.raises(HostSizingWindowError):
        WindowSizingAuthority(**values)


def test_window_authority_requires_matching_baseline_handle():
    with pytest.raises(HostSizingWindowError):
        WindowSizingAuthority(
            authority_id="authority",
            handle=200,
            browser_kind=BrowserKind.EDGE,
            process_id=400,
            launch_process_ids=frozenset({400}),
            stable_polls=3,
            baseline=geometry(),
            managed_profile=True,
            app_mode=True,
        )


def test_windows_authority_verifier_requires_one_matching_candidate():
    exact = WindowsWindowAuthorityVerifier(FakeWindowProvider(window()))

    assert exact.verify(authority()).exact is True

    none = WindowsWindowAuthorityVerifier(FakeWindowProvider())
    multiple = WindowsWindowAuthorityVerifier(
        FakeWindowProvider(window(), window("200", pid=401))
    )
    assert none.verify(authority()).exact is False
    assert multiple.verify(authority()).exact is False


@pytest.mark.parametrize(
    "observed",
    [
        window("200"),
        window(pid=401),
        window(pid=999),
        window(process_name="chrome"),
        window(class_name="OtherWindowClass"),
    ],
)
def test_windows_authority_verifier_refuses_identity_drift(observed):
    verifier = WindowsWindowAuthorityVerifier(FakeWindowProvider(observed))

    assert verifier.verify(authority()).exact is False


def test_windows_authority_verifier_fails_closed_when_unavailable_or_broken():
    non_windows = FakeWindowProvider(window())
    non_windows.is_windows = False

    assert (
        WindowsWindowAuthorityVerifier(non_windows).verify(authority()).exact is False
    )
    assert (
        WindowsWindowAuthorityVerifier(FakeWindowProvider(error=True))
        .verify(authority())
        .exact
        is False
    )


def test_valid_growth_is_applied_and_verified_once():
    policy, decision = pending_policy_decision()
    baseline = geometry()
    after = after_height(939, base=baseline)
    backend = FakeGeometryBackend(baseline, after)
    verifier = FakeAuthorityVerifier(
        WindowAuthorityVerification(True, "pre", window()),
        WindowAuthorityVerification(True, "post", window()),
    )
    sizer = TrustedWindowsWindowSizer(
        backend=backend,
        authority_verifier=verifier,
    )

    result = sizer.apply(decision=decision, authority=authority(baseline=baseline))

    assert result.status == HostSizingMutationStatus.APPLIED
    assert result.applied is True
    assert result.acknowledgement_succeeded is True
    assert result.mutation_attempted is True
    assert result.safe_to_retry is False
    assert backend.set_calls == [(100, 1000, 939)]
    assert verifier.calls == 2
    acknowledgement = policy.acknowledge_apply(
        applied=result.acknowledgement_succeeded,
        reason=result.reason,
    )
    assert acknowledgement.state == HostSizingPolicyState.COMPLETE


def test_valid_shrink_preserves_width_and_position():
    _policy, decision = pending_policy_decision(
        current_height=1000,
        desired_height=800,
    )
    baseline = geometry(
        outer=NativeRect(100, 100, 1100, 1200),
        client_height=1061,
        work_area=NativeRect(0, 0, 1920, 1400),
    )
    after = after_height(900, base=baseline)
    backend = FakeGeometryBackend(baseline, after)
    sizer = TrustedWindowsWindowSizer(
        backend=backend,
        authority_verifier=FakeAuthorityVerifier(),
    )

    result = sizer.apply(decision=decision, authority=authority(baseline=baseline))

    assert result.applied is True
    assert backend.set_calls == [(100, 1000, 900)]
    assert result.after is not None
    assert result.after.outer.left == baseline.outer.left
    assert result.after.outer.top == baseline.outer.top


def test_144_dpi_conversion_is_repeatable():
    _policy, decision = pending_policy_decision(
        current_height=763,
        desired_height=900,
        device_pixel_ratio=1.5,
    )
    baseline = geometry(
        outer=NativeRect(3680, -300, 5480, 900),
        client_width=1768,
        client_height=1144,
        dpi=144,
        monitor_handle=2,
        monitor=NativeRect(3440, -301, 7280, 1859),
        work_area=NativeRect(3440, -301, 7280, 1787),
    )
    after = after_height(1406, base=baseline)
    backend = FakeGeometryBackend(baseline, after)
    sizer = TrustedWindowsWindowSizer(
        backend=backend,
        authority_verifier=FakeAuthorityVerifier(),
    )

    result = sizer.apply(
        decision=decision,
        authority=authority(baseline=baseline),
    )

    assert result.applied is True
    assert backend.set_calls == [(100, 1800, 1406)]


def test_monitor_work_area_clamps_without_moving_window():
    _policy, decision = pending_policy_decision(
        current_height=761,
        desired_height=1600,
    )
    baseline = geometry(work_area=NativeRect(0, 0, 1920, 1000))
    after = after_height(900, base=baseline)
    backend = FakeGeometryBackend(baseline, after)
    sizer = TrustedWindowsWindowSizer(
        backend=backend,
        authority_verifier=FakeAuthorityVerifier(),
    )

    result = sizer.apply(decision=decision, authority=authority(baseline=baseline))

    assert result.applied is True
    assert result.plan is not None
    assert result.plan.clamp_reasons == ("monitor_work_area",)
    assert backend.set_calls == [(100, 1000, 900)]


def test_native_no_change_is_safe_success_without_mutation():
    policy, decision = pending_policy_decision(
        current_height=700,
        desired_height=800,
    )
    baseline = geometry(work_area=NativeRect(0, 0, 1920, 900))
    backend = FakeGeometryBackend(baseline)
    sizer = TrustedWindowsWindowSizer(
        backend=backend,
        authority_verifier=FakeAuthorityVerifier(),
    )

    result = sizer.apply(decision=decision, authority=authority(baseline=baseline))

    assert result.status == HostSizingMutationStatus.NO_CHANGE
    assert result.applied is False
    assert result.acknowledgement_succeeded is True
    assert result.mutation_attempted is False
    assert backend.set_calls == []
    assert (
        policy.acknowledge_apply(
            applied=result.acknowledgement_succeeded,
            reason=result.reason,
        ).state
        == HostSizingPolicyState.COMPLETE
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda decision: replace(decision, action=HostSizingAction.WAIT),
        lambda decision: replace(decision, state=HostSizingPolicyState.COMPLETE),
        lambda decision: replace(decision, authority_id="other-authority"),
        lambda decision: replace(decision, desired_viewport_height=5000),
        lambda decision: replace(decision, current_viewport_height=float("nan")),
        lambda decision: replace(decision, source_id=None),
        lambda decision: replace(decision, sequence=0),
        lambda decision: replace(decision, requested_viewport_height=None),
    ],
)
def test_invalid_ll_hs2_decision_is_refused_before_native_access(mutate):
    _policy, valid = pending_policy_decision()
    backend = FakeGeometryBackend(geometry())
    verifier = FakeAuthorityVerifier()
    sizer = TrustedWindowsWindowSizer(
        backend=backend,
        authority_verifier=verifier,
    )

    result = sizer.apply(decision=mutate(valid), authority=authority())

    assert result.status == HostSizingMutationStatus.REFUSED
    assert result.mutation_attempted is False
    assert backend.capture_calls == 0
    assert backend.set_calls == []
    assert verifier.calls == 0


def test_failed_identity_verification_refuses_before_geometry_capture():
    _policy, decision = pending_policy_decision()
    backend = FakeGeometryBackend(geometry())
    sizer = TrustedWindowsWindowSizer(
        backend=backend,
        authority_verifier=FakeAuthorityVerifier(
            WindowAuthorityVerification(False, "identity changed")
        ),
    )

    result = sizer.apply(decision=decision, authority=authority())

    assert result.status == HostSizingMutationStatus.REFUSED
    assert backend.capture_calls == 0
    assert backend.set_calls == []


@pytest.mark.parametrize(
    "changed",
    [
        replace(geometry(), outer=NativeRect(100, 100, 1100, 950)),
        replace(geometry(), client_height=800),
        replace(geometry(), dpi=144),
        replace(geometry(), monitor_handle=2),
        replace(geometry(), monitor=NativeRect(0, 0, 2560, 1440)),
        replace(geometry(), work_area=NativeRect(0, 0, 1920, 1000)),
        replace(geometry(), show_command=2),
        replace(geometry(), state=WindowGeometryState.MAXIMIZED),
    ],
)
def test_geometry_or_state_change_after_authority_capture_refuses_mutation(changed):
    _policy, decision = pending_policy_decision()
    baseline = geometry()
    backend = FakeGeometryBackend(changed)
    sizer = TrustedWindowsWindowSizer(
        backend=backend,
        authority_verifier=FakeAuthorityVerifier(),
    )

    result = sizer.apply(decision=decision, authority=authority(baseline=baseline))

    assert result.status == HostSizingMutationStatus.REFUSED
    assert backend.set_calls == []


@pytest.mark.parametrize(
    "state",
    [
        WindowGeometryState.MINIMIZED,
        WindowGeometryState.MAXIMIZED,
        WindowGeometryState.FULLSCREEN,
        WindowGeometryState.SNAPPED,
    ],
)
def test_unsuitable_baseline_window_state_refuses_mutation(state):
    _policy, decision = pending_policy_decision()
    baseline = geometry(state=state)
    backend = FakeGeometryBackend(baseline)
    sizer = TrustedWindowsWindowSizer(
        backend=backend,
        authority_verifier=FakeAuthorityVerifier(),
    )

    result = sizer.apply(decision=decision, authority=authority(baseline=baseline))

    assert result.status == HostSizingMutationStatus.REFUSED
    assert state.value in result.reason
    assert backend.set_calls == []


def test_dpi_and_device_pixel_ratio_mismatch_refuses_mutation():
    _policy, decision = pending_policy_decision()
    baseline = geometry(dpi=144)
    backend = FakeGeometryBackend(baseline)
    sizer = TrustedWindowsWindowSizer(
        backend=backend,
        authority_verifier=FakeAuthorityVerifier(),
    )

    result = sizer.apply(
        decision=decision,
        authority=authority(baseline=baseline),
    )

    assert result.status == HostSizingMutationStatus.REFUSED
    assert "inconsistent" in result.reason
    assert backend.set_calls == []


def test_pre_apply_capture_failure_is_acknowledgement_safe():
    _policy, decision = pending_policy_decision()
    backend = FakeGeometryBackend(geometry(), capture_error_at=1)
    sizer = TrustedWindowsWindowSizer(
        backend=backend,
        authority_verifier=FakeAuthorityVerifier(),
    )

    result = sizer.apply(decision=decision, authority=authority())

    assert result.status == HostSizingMutationStatus.FAILED
    assert result.mutation_attempted is False
    assert result.acknowledgement_succeeded is False


def test_native_call_failure_is_nonretryable_and_acknowledges_failure():
    policy, decision = pending_policy_decision()
    baseline = geometry()
    backend = FakeGeometryBackend(baseline, set_error=True)
    sizer = TrustedWindowsWindowSizer(
        backend=backend,
        authority_verifier=FakeAuthorityVerifier(),
    )

    result = sizer.apply(decision=decision, authority=authority(baseline=baseline))

    assert result.status == HostSizingMutationStatus.FAILED
    assert result.mutation_attempted is True
    assert result.safe_to_retry is False
    assert (
        policy.acknowledge_apply(
            applied=result.acknowledgement_succeeded,
            reason=result.reason,
        ).state
        == HostSizingPolicyState.ABORTED
    )


def test_post_apply_capture_failure_reports_attempted_unverified_mutation():
    _policy, decision = pending_policy_decision()
    baseline = geometry()
    backend = FakeGeometryBackend(baseline, geometry(), capture_error_at=2)
    sizer = TrustedWindowsWindowSizer(
        backend=backend,
        authority_verifier=FakeAuthorityVerifier(),
    )

    result = sizer.apply(decision=decision, authority=authority(baseline=baseline))

    assert result.status == HostSizingMutationStatus.FAILED
    assert result.mutation_attempted is True
    assert len(backend.set_calls) == 1


@pytest.mark.parametrize(
    "after",
    [
        after_height(900),
        replace(after_height(939), outer=NativeRect(110, 100, 1110, 1039)),
        replace(after_height(939), outer=NativeRect(100, 100, 1110, 1039)),
        after_height(920),
        replace(after_height(939), state=WindowGeometryState.SNAPPED),
        replace(after_height(939), dpi=144),
        replace(after_height(939), monitor_handle=2),
        replace(after_height(939), show_command=2),
        replace(after_height(939), client_width=900),
    ],
)
def test_post_apply_geometry_mismatch_reports_failed_mutation(after):
    _policy, decision = pending_policy_decision()
    baseline = geometry()
    backend = FakeGeometryBackend(baseline, after)
    sizer = TrustedWindowsWindowSizer(
        backend=backend,
        authority_verifier=FakeAuthorityVerifier(),
    )

    result = sizer.apply(decision=decision, authority=authority(baseline=baseline))

    assert result.status == HostSizingMutationStatus.FAILED
    assert result.mutation_attempted is True
    assert result.acknowledgement_succeeded is False


def test_post_apply_identity_drift_reports_failed_mutation():
    _policy, decision = pending_policy_decision()
    baseline = geometry()
    backend = FakeGeometryBackend(baseline, after_height(939))
    verifier = FakeAuthorityVerifier(
        WindowAuthorityVerification(True, "pre", window()),
        WindowAuthorityVerification(False, "post identity changed"),
    )
    sizer = TrustedWindowsWindowSizer(
        backend=backend,
        authority_verifier=verifier,
    )

    result = sizer.apply(decision=decision, authority=authority(baseline=baseline))

    assert result.status == HostSizingMutationStatus.FAILED
    assert result.reason == "post identity changed"
    assert result.mutation_attempted is True


def test_one_shot_capability_refuses_second_call_after_success():
    _policy, decision = pending_policy_decision()
    baseline = geometry()
    backend = FakeGeometryBackend(baseline, after_height(939))
    sizer = TrustedWindowsWindowSizer(
        backend=backend,
        authority_verifier=FakeAuthorityVerifier(),
    )
    exact = authority(baseline=baseline)

    first = sizer.apply(decision=decision, authority=exact)
    second = sizer.apply(decision=decision, authority=exact)

    assert first.applied is True
    assert second.status == HostSizingMutationStatus.REFUSED
    assert sizer.consumed is True
    assert len(backend.set_calls) == 1


def test_session_capability_rebases_after_verified_growth_then_allows_shrink():
    baseline = geometry(work_area=NativeRect(0, 0, 1920, 1800))
    after_growth = after_height(939, base=baseline)
    after_shrink = after_height(739, base=after_growth)
    backend = FakeGeometryBackend(
        baseline,
        after_growth,
        after_growth,
        after_shrink,
    )
    sizer = TrustedWindowsWindowSizer(
        backend=backend,
        authority_verifier=FakeAuthorityVerifier(),
        lifetime=WindowSizingLifetime.SESSION,
    )
    policy = HostSizingPolicy(
        config=HostSizingPolicyConfig(quiet_period_seconds=0),
        mode=HostSizingPolicyMode.CONTINUOUS,
        clock=FakeClock(),
    )
    policy.observe_authority(
        HostSizingAuthorityStatus.EXACT,
        authority_id="window-authority-1",
    )
    exact = authority(baseline=baseline)

    growth = policy.observe_report(
        HostSizingReport(
            protocol=1,
            launch_id="launch-authority-123456",
            source_id="primary-surface",
            sequence=1,
            device_pixel_ratio=1.0,
            content=SurfaceDimensions(850, 1180),
            host_viewport=SurfaceDimensions(761, 1280),
            desired_host_viewport=SurfaceDimensions(900),
        )
    )
    growth_result = sizer.apply(decision=growth, authority=exact)
    policy.acknowledge_apply(applied=growth_result.acknowledgement_succeeded)
    shrink = policy.observe_report(
        HostSizingReport(
            protocol=1,
            launch_id="launch-authority-123456",
            source_id="primary-surface",
            sequence=2,
            device_pixel_ratio=1.0,
            content=SurfaceDimensions(650, 1180),
            host_viewport=SurfaceDimensions(900, 1280),
            desired_host_viewport=SurfaceDimensions(700),
        )
    )
    shrink_result = sizer.apply(decision=shrink, authority=exact)

    assert growth_result.applied is True
    assert shrink_result.applied is True
    assert shrink_result.baseline == after_growth
    assert backend.set_calls == [(100, 1000, 939), (100, 1000, 739)]
    assert sizer.apply_calls == 2
    assert sizer.authority_verifier.calls == 4


def test_session_capability_can_shrink_after_its_own_work_area_clamp():
    baseline = geometry(
        outer=NativeRect(0, 100, 640, 900),
        client_width=624,
        client_height=761,
        work_area=NativeRect(0, 0, 1920, 1000),
    )
    clamped = geometry(
        outer=NativeRect(0, 100, 640, 1000),
        client_width=624,
        client_height=861,
        work_area=baseline.work_area,
        state=WindowGeometryState.SNAPPED,
    )
    shrunk = geometry(
        outer=NativeRect(0, 100, 640, 800),
        client_width=624,
        client_height=661,
        work_area=baseline.work_area,
    )
    backend = FakeGeometryBackend(baseline, clamped, clamped, shrunk)
    sizer = TrustedWindowsWindowSizer(
        backend=backend,
        authority_verifier=FakeAuthorityVerifier(),
        lifetime=WindowSizingLifetime.SESSION,
    )
    policy = HostSizingPolicy(
        config=HostSizingPolicyConfig(quiet_period_seconds=0),
        mode=HostSizingPolicyMode.CONTINUOUS,
        clock=FakeClock(),
    )
    policy.observe_authority(
        HostSizingAuthorityStatus.EXACT,
        authority_id="window-authority-1",
    )
    exact = authority(baseline=baseline)

    clamp = policy.observe_report(
        HostSizingReport(
            protocol=1,
            launch_id="launch-authority-123456",
            source_id="primary-surface",
            sequence=1,
            device_pixel_ratio=1.0,
            content=SurfaceDimensions(1500, 624),
            host_viewport=SurfaceDimensions(761, 624),
            desired_host_viewport=SurfaceDimensions(1600),
        )
    )
    clamp_result = sizer.apply(decision=clamp, authority=exact)
    policy.acknowledge_apply(applied=clamp_result.acknowledgement_succeeded)
    shrink = policy.observe_report(
        HostSizingReport(
            protocol=1,
            launch_id="launch-authority-123456",
            source_id="primary-surface",
            sequence=2,
            device_pixel_ratio=1.0,
            content=SurfaceDimensions(620, 624),
            host_viewport=SurfaceDimensions(861, 624),
            desired_host_viewport=SurfaceDimensions(661),
        )
    )
    shrink_result = sizer.apply(decision=shrink, authority=exact)

    assert clamp_result.applied is True
    assert clamp_result.after is not None
    assert clamp_result.after.state == WindowGeometryState.NORMAL
    assert shrink_result.applied is True
    assert backend.set_calls == [(100, 640, 900), (100, 640, 700)]


def test_session_capability_refuses_unverified_user_geometry_change():
    _policy, decision = pending_policy_decision()
    baseline = geometry(work_area=NativeRect(0, 0, 1920, 1800))
    moved = replace(
        baseline,
        outer=NativeRect(110, 100, 1110, 900),
    )
    backend = FakeGeometryBackend(moved)
    sizer = TrustedWindowsWindowSizer(
        backend=backend,
        authority_verifier=FakeAuthorityVerifier(),
        lifetime=WindowSizingLifetime.SESSION,
    )

    result = sizer.apply(decision=decision, authority=authority(baseline=baseline))

    assert result.status == HostSizingMutationStatus.REFUSED
    assert "outside verified host sizing" in result.reason
    assert backend.set_calls == []


def test_concurrent_apply_calls_can_attempt_only_one_mutation():
    _policy, decision = pending_policy_decision()
    baseline = geometry()
    backend = FakeGeometryBackend(baseline, after_height(939))
    sizer = TrustedWindowsWindowSizer(
        backend=backend,
        authority_verifier=FakeAuthorityVerifier(),
    )
    exact = authority(baseline=baseline)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = tuple(
            executor.map(
                lambda _index: sizer.apply(decision=decision, authority=exact),
                range(8),
            )
        )

    assert sum(result.applied for result in results) == 1
    assert len(backend.set_calls) == 1
    assert (
        sum(result.status == HostSizingMutationStatus.REFUSED for result in results)
        == 7
    )


def test_mutation_results_are_immutable():
    _policy, decision = pending_policy_decision()
    baseline = geometry()
    result = TrustedWindowsWindowSizer(
        backend=FakeGeometryBackend(baseline, after_height(939)),
        authority_verifier=FakeAuthorityVerifier(),
    ).apply(decision=decision, authority=authority(baseline=baseline))

    with pytest.raises(FrozenInstanceError):
        result.reason = "changed"


class FakeUser32:
    class DpiContext:
        def __init__(self) -> None:
            self.calls: list[object] = []

        def __call__(self, value):
            self.calls.append(value)
            return 1

    def __init__(self) -> None:
        self.SetThreadDpiAwarenessContext = self.DpiContext()
        self.set_window_pos_calls: list[tuple[object, ...]] = []

    def SetWindowPos(self, *args):
        self.set_window_pos_calls.append(args)
        return 1


def test_windows_backend_uses_nonmoving_nonactivating_setwindowpos_flags():
    user32 = FakeUser32()
    backend = WindowsGeometryBackend(user32=user32, is_windows=True)

    backend.set_outer_size(100, width=1000, height=900)

    assert len(user32.set_window_pos_calls) == 1
    call = user32.set_window_pos_calls[0]
    assert call[2:6] == (0, 0, 1000, 900)
    assert call[6] == SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOOWNERZORDER
    assert len(user32.SetThreadDpiAwarenessContext.calls) == 2


def test_windows_backend_rejects_invalid_native_dimensions():
    backend = WindowsGeometryBackend(user32=FakeUser32(), is_windows=True)

    with pytest.raises(GeometryProbeError):
        backend.set_outer_size(100, width=0, height=900)


def test_window_sizing_capability_remains_private_and_narrow():
    source = Path(window_module.__file__).read_text(encoding="utf-8")

    assert not hasattr(litlaunch, "TrustedWindowsWindowSizer")
    assert "start_host_sizing_channel" not in source
    assert "HostSizingChannel" not in source
    assert "parse_host_sizing_report" not in source
    assert "subprocess" not in source
    assert "TerminateProcess" not in source
    assert "MoveWindow" not in source
    assert "SetWindowText" not in source
    assert "CloseWindow" not in source
