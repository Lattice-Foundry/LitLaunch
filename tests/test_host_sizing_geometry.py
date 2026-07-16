from __future__ import annotations

from dataclasses import replace

import pytest

from litlaunch._host_sizing_geometry import (
    GeometryProbeError,
    NativeRect,
    WindowGeometry,
    WindowGeometryState,
    WindowsGeometryBackend,
    geometry_changed,
    looks_snapped,
    plan_height_resize,
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


@pytest.mark.parametrize(
    "changed",
    [
        replace(geometry(), monitor=NativeRect(0, 0, 2560, 1440)),
        replace(geometry(), show_command=2),
        replace(geometry(), outer=NativeRect(120, 100, 1120, 900)),
    ],
)
def test_geometry_change_covers_window_monitor_and_placement(changed):
    assert geometry_changed(geometry(), changed)


def test_non_windows_backend_refuses_native_capture():
    with pytest.raises(GeometryProbeError, match="unavailable"):
        WindowsGeometryBackend(is_windows=False).capture(100)
