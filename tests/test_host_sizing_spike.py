from __future__ import annotations

from dataclasses import replace

import pytest

from litlaunch._host_sizing_geometry import (
    GeometryProbeError,
    HostSizingGeometryProbe,
    NativeRect,
    WindowAuthorityStatus,
    WindowGeometry,
    WindowGeometryState,
    WindowsGeometryBackend,
    classify_window_authority,
    geometry_changed,
    looks_snapped,
    plan_height_resize,
    wait_for_exact_window_authority,
)
from litlaunch._host_sizing_spike import (
    SpikeRunResult,
    ViewportObservation,
    _parse_viewport,
    build_parser,
    result_as_dict,
)
from litlaunch.browsers import BrowserKind
from litlaunch.windowing import WindowInfo


def window(
    handle: str,
    *,
    title: str = "LL-HS0-token|vh=700|vw=900|dpr=1",
    pid: int = 400,
    process_name: str = "msedge",
) -> WindowInfo:
    return WindowInfo(
        handle,
        title=title,
        class_name="Chrome_WidgetWin_1",
        pid=pid,
        process_name=process_name,
    )


def geometry(
    *,
    outer: NativeRect | None = None,
    dpi: int = 96,
    state: WindowGeometryState = WindowGeometryState.NORMAL,
    work_area: NativeRect | None = None,
) -> WindowGeometry:
    resolved_outer = outer or NativeRect(100, 100, 1100, 900)
    resolved_work_area = work_area or NativeRect(0, 0, 1920, 1040)
    return WindowGeometry(
        handle=100,
        outer=resolved_outer,
        client_width=984,
        client_height=761,
        dpi=dpi,
        monitor_handle=1,
        monitor=NativeRect(0, 0, 1920, 1080),
        work_area=resolved_work_area,
        show_command=1,
        state=state,
    )


def authority_for(*windows: WindowInfo, launch_pids=(400,), is_windows=True):
    return classify_window_authority(
        windows,
        baseline_handles=("50",),
        browser_kind=BrowserKind.EDGE,
        title_token="LL-HS0-token",
        launch_pids=launch_pids,
        is_windows=is_windows,
    )


def test_authority_requires_one_new_title_browser_and_process_match():
    exact = window("100")

    result = authority_for(
        window("50"),
        exact,
        window("200", title="Other app"),
        window("300", process_name="chrome"),
        window("400", pid=999),
    )

    assert result.status == WindowAuthorityStatus.EXACT
    assert result.window == exact
    assert result.candidates == (exact,)


def test_authority_reports_none_without_launched_process_match():
    result = authority_for(window("100", pid=999))

    assert result.status == WindowAuthorityStatus.NONE
    assert result.window is None
    assert "launch_process=0" in result.reason


def test_authority_fails_closed_when_multiple_windows_match():
    result = authority_for(window("100"), window("200"))

    assert result.status == WindowAuthorityStatus.AMBIGUOUS
    assert result.window is None
    assert [candidate.handle for candidate in result.candidates] == ["100", "200"]


def test_authority_is_unsupported_without_windows_or_process_identity():
    assert authority_for(window("100"), is_windows=False).status == (
        WindowAuthorityStatus.UNSUPPORTED
    )
    assert authority_for(window("100"), launch_pids=()).status == (
        WindowAuthorityStatus.UNSUPPORTED
    )


def test_authority_wait_requires_same_unique_handle_across_stable_polls():
    captures = iter(
        [
            (),
            (window("100"),),
            (window("100"),),
            (window("100"),),
        ]
    )

    class Provider:
        is_windows = True

        def capture(self, target):
            return next(captures)

    values = iter((0.0, 0.0, 0.1, 0.2, 0.3, 0.4))
    result = wait_for_exact_window_authority(
        Provider(),
        baseline_handles=(),
        browser_kind=BrowserKind.EDGE,
        title_token="LL-HS0-token",
        launch_pid_provider=lambda: (400,),
        timeout_seconds=1.0,
        stable_poll_count=3,
        clock=lambda: next(values),
        sleeper=lambda seconds: None,
    )

    assert result.status == WindowAuthorityStatus.EXACT
    assert result.stable_polls == 3


def test_authority_wait_stops_immediately_on_ambiguity():
    class Provider:
        is_windows = True

        def capture(self, target):
            return (window("100"), window("200"))

    result = wait_for_exact_window_authority(
        Provider(),
        baseline_handles=(),
        browser_kind=BrowserKind.EDGE,
        title_token="LL-HS0-token",
        launch_pid_provider=lambda: (400,),
        timeout_seconds=1.0,
        clock=lambda: 0.0,
        sleeper=lambda seconds: None,
    )

    assert result.status == WindowAuthorityStatus.AMBIGUOUS


def test_height_plan_converts_css_delta_using_window_dpi():
    current = geometry(dpi=144, work_area=NativeRect(0, 0, 1920, 1200))

    plan = plan_height_resize(
        current,
        current_viewport_height_css=700,
        desired_viewport_height_css=800,
        device_pixel_ratio=1.5,
    )

    assert plan.safe is True
    assert plan.css_delta == 100
    assert plan.native_delta == 150
    assert plan.requested_outer_height == 950
    assert plan.target_outer_height == 950
    assert plan.expected_viewport_height_css == 800


def test_height_plan_rejects_dpi_and_device_pixel_ratio_mismatch():
    plan = plan_height_resize(
        geometry(dpi=144),
        current_viewport_height_css=700,
        desired_viewport_height_css=800,
        device_pixel_ratio=1.0,
    )

    assert plan.safe is False
    assert "inconsistent" in plan.reason


def test_height_plan_clamps_to_minimum_and_monitor_work_area():
    minimum = plan_height_resize(
        geometry(),
        current_viewport_height_css=700,
        desired_viewport_height_css=100,
        device_pixel_ratio=1.0,
    )
    maximum = plan_height_resize(
        geometry(
            outer=NativeRect(-1800, 200, -800, 900),
            work_area=NativeRect(-1920, 0, 0, 1000),
        ),
        current_viewport_height_css=700,
        desired_viewport_height_css=1200,
        device_pixel_ratio=1.0,
    )

    assert minimum.safe is True
    assert minimum.effective_viewport_height_css == 320
    assert minimum.clamp_reasons == ("minimum_viewport_height",)
    assert maximum.safe is True
    assert maximum.target_outer_height == 800
    assert maximum.clamp_reasons == ("monitor_work_area",)
    assert maximum.expected_viewport_height_css == 800


@pytest.mark.parametrize(
    "state",
    [
        WindowGeometryState.MINIMIZED,
        WindowGeometryState.MAXIMIZED,
        WindowGeometryState.FULLSCREEN,
        WindowGeometryState.SNAPPED,
    ],
)
def test_height_plan_rejects_unsuitable_window_states(state):
    plan = plan_height_resize(
        geometry(state=state),
        current_viewport_height_css=700,
        desired_viewport_height_css=800,
        device_pixel_ratio=1.0,
    )

    assert plan.safe is False
    assert state.value in plan.reason


def test_common_snap_layouts_are_detected_conservatively():
    work = NativeRect(0, 0, 1920, 1040)

    assert looks_snapped(NativeRect(0, 0, 960, 1040), work, dpi=96)
    assert looks_snapped(NativeRect(0, 0, 1920, 520), work, dpi=96)
    assert not looks_snapped(NativeRect(100, 100, 1100, 900), work, dpi=96)


class FakeGeometryBackend:
    def __init__(self, snapshots):
        self.snapshots = iter(snapshots)
        self.calls = []

    def capture(self, handle):
        return next(self.snapshots)

    def set_outer_size(self, handle, *, width, height):
        self.calls.append((handle, width, height))


def test_apply_preserves_width_and_position_and_measures_result():
    before = geometry()
    plan = plan_height_resize(
        before,
        current_viewport_height_css=700,
        desired_viewport_height_css=800,
        device_pixel_ratio=1.0,
    )
    after = replace(
        before,
        outer=NativeRect(
            before.outer.left,
            before.outer.top,
            before.outer.right,
            before.outer.bottom + 100,
        ),
        client_height=before.client_height + 100,
    )
    backend = FakeGeometryBackend((before, after))

    result = HostSizingGeometryProbe(backend).apply(
        handle=100,
        baseline=before,
        plan=plan,
    )

    assert result.applied is True
    assert backend.calls == [(100, before.outer.width, before.outer.height + 100)]
    assert result.after == after


def test_apply_refuses_external_geometry_change_before_mutation():
    baseline = geometry()
    changed = replace(
        baseline,
        outer=NativeRect(120, 100, 1120, 900),
    )
    backend = FakeGeometryBackend((changed,))
    plan = plan_height_resize(
        baseline,
        current_viewport_height_css=700,
        desired_viewport_height_css=800,
        device_pixel_ratio=1.0,
    )

    result = HostSizingGeometryProbe(backend).apply(
        handle=100,
        baseline=baseline,
        plan=plan,
    )

    assert result.applied is False
    assert backend.calls == []
    assert "changed" in result.reason
    assert geometry_changed(baseline, changed)


@pytest.mark.parametrize(
    "changed",
    [
        replace(geometry(), monitor=NativeRect(0, 0, 2560, 1440)),
        replace(geometry(), show_command=2),
    ],
)
def test_geometry_change_includes_monitor_bounds_and_show_command(changed):
    assert geometry_changed(geometry(), changed)


def test_non_windows_backend_refuses_native_capture():
    with pytest.raises(GeometryProbeError, match="unavailable"):
        WindowsGeometryBackend(is_windows=False).capture(100)


def test_measurement_title_parser_requires_exact_probe_token():
    title = "LL-HS0-abc123|vh=760|vw=1100|dpr=1.25 - Microsoft Edge"

    assert _parse_viewport(title, token="LL-HS0-abc123") == ViewportObservation(
        height=760,
        width=1100,
        device_pixel_ratio=1.25,
        title=title,
    )
    assert _parse_viewport(title, token="LL-HS0-other") is None


def test_internal_parser_defaults_to_dry_run_and_result_is_json_safe():
    args = build_parser().parse_args(
        ["--browser", "edge", "--desired-viewport-height", "900"]
    )
    authority = authority_for(window("100"))
    dry_run = SpikeRunResult(
        True,
        "edge",
        "msedge.exe",
        authority,
        ViewportObservation(700, 1000, 1.0, "title"),
        geometry(),
        plan_height_resize(
            geometry(),
            current_viewport_height_css=700,
            desired_viewport_height_css=800,
            device_pixel_ratio=1.0,
        ),
        None,
        None,
        None,
        True,
        "safe",
    )

    rendered = result_as_dict(dry_run)

    assert args.apply is False
    assert rendered["dry_run"] is True
    assert rendered["authority"]["status"] == "exact"
    assert rendered["geometry_before"]["state"] == "normal"
