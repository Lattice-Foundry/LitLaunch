from __future__ import annotations

from pathlib import Path

import pytest

import litlaunch
from litlaunch._browser_authority import (
    BrowserLaunchAuthority,
    BrowserLaunchStrategy,
    BrowserProcessTreeSnapshot,
    BrowserProcessTreeStatus,
)
from litlaunch._host_sizing_authority import (
    HostSizingAuthorityCollectionConfig,
    PrivateHostSizingActivationGate,
    PrivateHostSizingEligibilityStatus,
    ProcessBoundWindowsWindowAuthorityVerifier,
)
from litlaunch._host_sizing_geometry import (
    NativeRect,
    WindowGeometry,
    WindowGeometryState,
)
from litlaunch._host_sizing_window import create_window_sizing_authority
from litlaunch.artifacts import mark_litlaunch_owned
from litlaunch.browsers import BrowserKind
from litlaunch.config import LaunchMode
from litlaunch.windowing import WindowInfo


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


class FakeProcessTracker:
    def __init__(self, *snapshots: BrowserProcessTreeSnapshot) -> None:
        self.snapshots = list(snapshots)
        self.calls = 0

    def capture(
        self,
        authority: BrowserLaunchAuthority,
    ) -> BrowserProcessTreeSnapshot:
        self.calls += 1
        if len(self.snapshots) > 1:
            return self.snapshots.pop(0)
        return self.snapshots[0]


class FakeWindowProvider:
    is_windows = True

    def __init__(self, *captures: tuple[WindowInfo, ...], error: bool = False) -> None:
        self.captures = list(captures)
        self.error = error
        self.calls = 0

    def capture(self) -> tuple[WindowInfo, ...]:
        self.calls += 1
        if self.error:
            raise OSError("window capture failed")
        if len(self.captures) > 1:
            return self.captures.pop(0)
        return self.captures[0]


class FakeGeometryBackend:
    def __init__(self, snapshot: WindowGeometry, *, error: bool = False) -> None:
        self.snapshot = snapshot
        self.error = error
        self.capture_calls: list[int] = []

    def capture(self, handle: int) -> WindowGeometry:
        self.capture_calls.append(handle)
        if self.error:
            raise OSError("geometry unavailable")
        return self.snapshot

    def set_outer_size(self, handle: int, *, width: int, height: int) -> None:
        raise AssertionError("activation gate must not mutate a window")


class FakeSession:
    def __init__(self, *authorities: BrowserLaunchAuthority | None) -> None:
        self.authorities = list(authorities)

    def _browser_authority_snapshot(self) -> BrowserLaunchAuthority | None:
        if len(self.authorities) > 1:
            return self.authorities.pop(0)
        return self.authorities[0]


def launch_authority(
    tmp_path: Path,
    *,
    browser_kind: BrowserKind = BrowserKind.EDGE,
    strategy: BrowserLaunchStrategy = BrowserLaunchStrategy.DIRECT,
    launch_id: str = "launch-authority-123456",
) -> BrowserLaunchAuthority:
    profile = tmp_path / f"profile-{strategy.value}-{browser_kind.value}"
    profile.mkdir(parents=True)
    mark_litlaunch_owned(profile)
    executable = (
        Path("C:/Edge/msedge.exe")
        if browser_kind == BrowserKind.EDGE
        else Path("C:/Chrome/chrome.exe")
    )
    return BrowserLaunchAuthority(
        launch_id=launch_id,
        root_process_id=400,
        root_creation_time_100ns=10_000,
        browser_kind=browser_kind,
        executable_path=executable,
        managed_profile_dir=profile,
        launch_strategy=strategy,
        launched_at_monotonic=1.0,
    )


def process_snapshot(
    *process_ids: int,
    status: BrowserProcessTreeStatus = BrowserProcessTreeStatus.ACTIVE,
) -> BrowserProcessTreeSnapshot:
    return BrowserProcessTreeSnapshot(
        status,
        "exact process tree"
        if status
        in {
            BrowserProcessTreeStatus.ACTIVE,
            BrowserProcessTreeStatus.ROOT_EXITED,
        }
        else "process authority unavailable",
        browser_process_ids=frozenset(process_ids),
    )


def window(
    handle: str = "100",
    *,
    pid: int = 400,
    process_name: str = "msedge.exe",
    title: str = "",
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
    handle: int = 100,
    state: WindowGeometryState = WindowGeometryState.NORMAL,
) -> WindowGeometry:
    return WindowGeometry(
        handle=handle,
        outer=NativeRect(100, 100, 1100, 900),
        client_width=984,
        client_height=761,
        dpi=96,
        monitor_handle=1,
        monitor=NativeRect(0, 0, 1920, 1080),
        work_area=NativeRect(0, 0, 1920, 1040),
        show_command=1,
        state=state,
    )


def gate(
    process_tracker: FakeProcessTracker,
    window_provider: FakeWindowProvider,
    geometry_backend: FakeGeometryBackend,
) -> PrivateHostSizingActivationGate:
    clock = FakeClock()
    return PrivateHostSizingActivationGate(
        process_tracker=process_tracker,  # type: ignore[arg-type]
        window_provider=window_provider,
        geometry_backend=geometry_backend,
        config=HostSizingAuthorityCollectionConfig(
            timeout_seconds=0.2,
            poll_interval_seconds=0.05,
            stable_poll_count=3,
        ),
        clock=clock,
        sleeper=clock.sleep,
        is_windows=True,
    )


@pytest.mark.parametrize("browser_kind", [BrowserKind.EDGE, BrowserKind.CHROME])
@pytest.mark.parametrize(
    "strategy",
    [BrowserLaunchStrategy.DIRECT, BrowserLaunchStrategy.WINDOWS_SHORTCUT],
)
def test_private_gate_establishes_equivalent_exact_direct_and_shortcut_authority(
    tmp_path: Path,
    browser_kind: BrowserKind,
    strategy: BrowserLaunchStrategy,
):
    launch = launch_authority(
        tmp_path,
        browser_kind=browser_kind,
        strategy=strategy,
    )
    process_name = "msedge.exe" if browser_kind == BrowserKind.EDGE else "chrome.exe"
    candidate = window(process_name=process_name)
    tracker = FakeProcessTracker(process_snapshot(400, 401))
    provider = FakeWindowProvider((candidate,))
    backend = FakeGeometryBackend(geometry())

    result = gate(tracker, provider, backend).collect(
        launch,
        private_enabled=True,
    )

    assert result.status == PrivateHostSizingEligibilityStatus.ELIGIBLE
    assert result.eligible is True
    assert result.window_authority is not None
    assert result.window_authority.authority_id == launch.launch_id
    assert result.window_authority.handle == 100
    assert result.window_authority.process_id == 400
    assert result.window_authority.stable_polls == 3
    assert result.window_authority.baseline == geometry()
    assert tracker.calls == 3
    assert provider.calls == 3
    assert backend.capture_calls == [100]


def test_private_gate_is_inactive_by_default(tmp_path: Path):
    launch = launch_authority(tmp_path)
    tracker = FakeProcessTracker(process_snapshot(400))
    provider = FakeWindowProvider((window(),))

    result = gate(
        tracker,
        provider,
        FakeGeometryBackend(geometry()),
    ).collect(launch)

    assert result.status == PrivateHostSizingEligibilityStatus.DISABLED
    assert tracker.calls == 0
    assert provider.calls == 0


def test_private_gate_rejects_non_webapp_and_missing_authority(tmp_path: Path):
    launch = launch_authority(tmp_path)
    activation = gate(
        FakeProcessTracker(process_snapshot(400)),
        FakeWindowProvider((window(),)),
        FakeGeometryBackend(geometry()),
    )

    browser_mode = activation.collect(
        launch,
        private_enabled=True,
        mode=LaunchMode.BROWSER,
    )
    missing = activation.collect(None, private_enabled=True)

    assert browser_mode.status == PrivateHostSizingEligibilityStatus.UNSUPPORTED
    assert missing.status == PrivateHostSizingEligibilityStatus.AUTHORITY_UNAVAILABLE


def test_private_gate_excludes_preexisting_and_title_only_windows(tmp_path: Path):
    launch = launch_authority(tmp_path)
    preexisting = window("100", title="Expected Product")
    title_only = window("101", pid=999, title="Expected Product")
    activation = gate(
        FakeProcessTracker(process_snapshot(400)),
        FakeWindowProvider((preexisting, title_only)),
        FakeGeometryBackend(geometry()),
    )

    result = activation.collect(
        launch,
        private_enabled=True,
        baseline_handles=("100",),
    )

    assert result.status == PrivateHostSizingEligibilityStatus.NO_WINDOW
    assert result.window_authority is None


def test_private_gate_fails_closed_on_ambiguous_windows(tmp_path: Path):
    launch = launch_authority(tmp_path)
    activation = gate(
        FakeProcessTracker(process_snapshot(400, 401)),
        FakeWindowProvider((window("100"), window("101", pid=401))),
        FakeGeometryBackend(geometry()),
    )

    result = activation.collect(launch, private_enabled=True)

    assert result.status == PrivateHostSizingEligibilityStatus.AMBIGUOUS
    assert result.window_authority is None


def test_private_gate_rejects_unstable_candidate(tmp_path: Path):
    launch = launch_authority(tmp_path)
    activation = gate(
        FakeProcessTracker(process_snapshot(400, 401)),
        FakeWindowProvider(
            (window("100"),),
            (window("101", pid=401),),
            (window("100"),),
            (window("101", pid=401),),
            (window("100"),),
        ),
        FakeGeometryBackend(geometry()),
    )

    result = activation.collect(launch, private_enabled=True)

    assert result.status == PrivateHostSizingEligibilityStatus.UNSTABLE
    assert result.window_authority is None


@pytest.mark.parametrize(
    "state",
    [
        WindowGeometryState.MINIMIZED,
        WindowGeometryState.MAXIMIZED,
        WindowGeometryState.FULLSCREEN,
    ],
)
def test_private_gate_requires_normal_window_state(
    tmp_path: Path,
    state: WindowGeometryState,
):
    launch = launch_authority(tmp_path)
    activation = gate(
        FakeProcessTracker(process_snapshot(400)),
        FakeWindowProvider((window(),)),
        FakeGeometryBackend(geometry(state=state)),
    )

    result = activation.collect(launch, private_enabled=True)

    assert result.status == PrivateHostSizingEligibilityStatus.UNSAFE_WINDOW
    assert result.window_authority is None


def test_private_gate_shutdown_invalidates_session_authority(tmp_path: Path):
    launch = launch_authority(tmp_path)
    activation = gate(
        FakeProcessTracker(process_snapshot(400)),
        FakeWindowProvider((window(),)),
        FakeGeometryBackend(geometry()),
    )

    result = activation.collect_for_session(
        FakeSession(launch, None),
        private_enabled=True,
    )

    assert result.status == PrivateHostSizingEligibilityStatus.SHUT_DOWN
    assert result.window_authority is None


def test_private_gate_fails_when_process_authority_is_lost(tmp_path: Path):
    launch = launch_authority(tmp_path)
    activation = gate(
        FakeProcessTracker(
            process_snapshot(status=BrowserProcessTreeStatus.PID_REUSED)
        ),
        FakeWindowProvider((window(),)),
        FakeGeometryBackend(geometry()),
    )

    result = activation.collect(launch, private_enabled=True)

    assert result.status == PrivateHostSizingEligibilityStatus.AUTHORITY_UNAVAILABLE
    assert result.window_authority is None


def test_process_bound_verifier_rechecks_launch_tree_and_exact_hwnd(tmp_path: Path):
    launch = launch_authority(tmp_path)
    activation = gate(
        FakeProcessTracker(process_snapshot(400)),
        FakeWindowProvider((window(),)),
        FakeGeometryBackend(geometry()),
    )
    eligibility = activation.collect(launch, private_enabled=True)
    assert eligibility.window_authority is not None
    verifier = ProcessBoundWindowsWindowAuthorityVerifier(
        launch,
        process_tracker=FakeProcessTracker(process_snapshot(400)),  # type: ignore[arg-type]
        window_provider=FakeWindowProvider((window(),)),
    )

    verification = verifier.verify(eligibility.window_authority)

    assert verification.exact is True
    assert verification.window == window()


def test_process_bound_verifier_rejects_launch_mismatch_and_pid_reuse(
    tmp_path: Path,
):
    launch = launch_authority(tmp_path)
    activation = gate(
        FakeProcessTracker(process_snapshot(400)),
        FakeWindowProvider((window(),)),
        FakeGeometryBackend(geometry()),
    )
    eligibility = activation.collect(launch, private_enabled=True)
    assert eligibility.window_authority is not None
    mismatched = create_window_sizing_authority(
        authority_id="different-launch-123456",
        probe=_exact_probe(),
        browser_kind=BrowserKind.EDGE,
        launch_process_ids=(400,),
        baseline=geometry(),
        managed_profile=True,
        app_mode=True,
    )
    verifier = ProcessBoundWindowsWindowAuthorityVerifier(
        launch,
        process_tracker=FakeProcessTracker(
            process_snapshot(status=BrowserProcessTreeStatus.PID_REUSED)
        ),  # type: ignore[arg-type]
        window_provider=FakeWindowProvider((window(),)),
    )

    launch_mismatch = verifier.verify(mismatched)
    pid_reuse = verifier.verify(eligibility.window_authority)

    assert launch_mismatch.exact is False
    assert "different browser launch" in launch_mismatch.reason
    assert pid_reuse.exact is False
    assert "unavailable" in pid_reuse.reason


def test_private_authority_has_no_public_or_normal_activation_surface():
    launcher_source = Path("src/litlaunch/launcher.py").read_text(encoding="utf-8")

    assert not hasattr(litlaunch, "PrivateHostSizingActivationGate")
    assert not hasattr(litlaunch, "BrowserLaunchAuthority")
    assert "PrivateHostSizingActivationGate" not in launcher_source
    assert "private_enabled=True" not in launcher_source


def _exact_probe():
    from litlaunch._host_sizing_geometry import (
        WindowAuthorityProbe,
        WindowAuthorityStatus,
    )

    candidate = window()
    return WindowAuthorityProbe(
        WindowAuthorityStatus.EXACT,
        candidate,
        (candidate,),
        "exact",
        3,
    )
