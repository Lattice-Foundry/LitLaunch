from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from litlaunch._browser_authority import (
    BrowserLaunchAuthority,
    BrowserLaunchStrategy,
    BrowserProcessTreeStatus,
    BrowserProcessTreeTracker,
    WindowsProcessCapture,
    WindowsProcessRecord,
    create_browser_launch_authority,
)
from litlaunch.artifacts import mark_litlaunch_owned
from litlaunch.browsers import BrowserKind


class FakeProcessProvider:
    def __init__(self, *captures: WindowsProcessCapture, error: bool = False) -> None:
        self.captures = list(captures)
        self.error = error

    def capture(self) -> WindowsProcessCapture:
        if self.error:
            raise OSError("process capture unavailable")
        if len(self.captures) > 1:
            return self.captures.pop(0)
        return self.captures[0]


def owned_profile(tmp_path: Path) -> Path:
    profile = tmp_path / "managed profile with spaces"
    profile.mkdir(parents=True)
    mark_litlaunch_owned(profile)
    return profile


def authority(
    tmp_path: Path,
    *,
    browser_kind: BrowserKind = BrowserKind.EDGE,
    strategy: BrowserLaunchStrategy = BrowserLaunchStrategy.DIRECT,
) -> BrowserLaunchAuthority:
    profile = owned_profile(tmp_path)
    executable = (
        Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe")
        if browser_kind == BrowserKind.EDGE
        else Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
    )
    return BrowserLaunchAuthority(
        launch_id="launch-authority-123456",
        root_process_id=100,
        root_creation_time_100ns=10_000,
        browser_kind=browser_kind,
        executable_path=executable,
        managed_profile_dir=profile,
        launch_strategy=strategy,
        launched_at_monotonic=2.5,
    )


def process(
    process_id: int,
    parent_process_id: int,
    creation_time: int | None,
    executable: Path | None,
) -> WindowsProcessRecord:
    return WindowsProcessRecord(
        process_id,
        parent_process_id,
        creation_time,
        executable,
    )


@pytest.mark.parametrize("browser_kind", [BrowserKind.EDGE, BrowserKind.CHROME])
@pytest.mark.parametrize(
    "strategy",
    [BrowserLaunchStrategy.DIRECT, BrowserLaunchStrategy.WINDOWS_SHORTCUT],
)
def test_launch_authority_binds_browser_profile_launch_and_quoted_space_paths(
    tmp_path: Path,
    browser_kind: BrowserKind,
    strategy: BrowserLaunchStrategy,
):
    profile = owned_profile(tmp_path)
    executable = tmp_path / "Browser Program Files" / "browser.exe"
    result = create_browser_launch_authority(
        root_process_id=44,
        root_creation_time_100ns=1234,
        browser_kind=browser_kind,
        executable_path=executable,
        command=(
            str(executable),
            "--app=http://127.0.0.1:8501",
            f'--user-data-dir="{profile}"',
            "--new-window",
        ),
        launch_strategy=strategy,
        launched_at_monotonic=4.5,
        launch_id="bound-launch-123456",
    )

    assert result is not None
    assert result.root_process_id == 44
    assert result.root_creation_time_100ns == 1234
    assert result.browser_kind == browser_kind
    assert result.executable_path == executable
    assert result.managed_profile_dir == profile
    assert result.launch_strategy == strategy
    assert result.launch_id == "bound-launch-123456"
    assert result.launched_at_monotonic == 4.5


def test_launch_authority_is_immutable(tmp_path: Path):
    result = authority(tmp_path)

    with pytest.raises(FrozenInstanceError):
        result.root_process_id = 99  # type: ignore[misc]


def test_launch_authority_requires_owned_managed_profile(tmp_path: Path):
    unowned = tmp_path / "unowned"
    unowned.mkdir()

    result = create_browser_launch_authority(
        root_process_id=44,
        root_creation_time_100ns=1234,
        browser_kind=BrowserKind.EDGE,
        executable_path="C:/Edge/msedge.exe",
        command=("C:/Edge/msedge.exe", f"--user-data-dir={unowned}"),
        launch_strategy=BrowserLaunchStrategy.DIRECT,
        launched_at_monotonic=1.0,
    )

    assert result is None


def test_launch_authority_requires_exact_root_image_when_queried(tmp_path: Path):
    profile = owned_profile(tmp_path)

    result = create_browser_launch_authority(
        root_process_id=44,
        browser_kind=BrowserKind.CHROME,
        executable_path="C:/Chrome/chrome.exe",
        command=("C:/Chrome/chrome.exe", f"--user-data-dir={profile}"),
        launch_strategy=BrowserLaunchStrategy.DIRECT,
        launched_at_monotonic=1.0,
        root_record_provider=lambda _pid: process(
            44,
            0,
            1234,
            Path("C:/Other/chrome.exe"),
        ),
    )

    assert result is None


def test_process_tree_discovers_only_exact_launch_descendants(tmp_path: Path):
    launch = authority(tmp_path)
    executable = launch.executable_path
    provider = FakeProcessProvider(
        WindowsProcessCapture(
            (
                process(100, 1, 10_000, executable),
                process(101, 100, 10_010, executable),
                process(102, 101, 10_020, executable),
                process(200, 1, 9_000, executable),
                process(201, 200, 10_030, executable),
            )
        )
    )

    snapshot = BrowserProcessTreeTracker(provider).capture(launch)

    assert snapshot.status == BrowserProcessTreeStatus.ACTIVE
    assert snapshot.browser_process_ids == frozenset({100, 101, 102})
    assert {record.process_id for record in snapshot.records} == {100, 101, 102}


def test_process_tree_retains_valid_descendants_after_root_handoff(tmp_path: Path):
    launch = authority(tmp_path)
    provider = FakeProcessProvider(
        WindowsProcessCapture(
            (
                process(101, 100, 10_010, launch.executable_path),
                process(102, 101, 10_020, launch.executable_path),
            )
        )
    )

    snapshot = BrowserProcessTreeTracker(provider).capture(launch)

    assert snapshot.status == BrowserProcessTreeStatus.ROOT_EXITED
    assert snapshot.browser_process_ids == frozenset({101, 102})


def test_process_tree_rejects_root_pid_reuse(tmp_path: Path):
    launch = authority(tmp_path)
    provider = FakeProcessProvider(
        WindowsProcessCapture((process(100, 1, 99_999, launch.executable_path),))
    )

    snapshot = BrowserProcessTreeTracker(provider).capture(launch)

    assert snapshot.status == BrowserProcessTreeStatus.PID_REUSED
    assert snapshot.active is False


def test_process_tree_fails_closed_when_root_identity_cannot_be_read(
    tmp_path: Path,
):
    launch = authority(tmp_path)
    provider = FakeProcessProvider(
        WindowsProcessCapture((process(100, 1, None, None),))
    )

    snapshot = BrowserProcessTreeTracker(provider).capture(launch)

    assert snapshot.status == BrowserProcessTreeStatus.UNAVAILABLE
    assert snapshot.active is False


def test_process_tree_drops_stale_descendant_on_refresh(tmp_path: Path):
    launch = authority(tmp_path)
    root = process(100, 1, 10_000, launch.executable_path)
    child = process(101, 100, 10_010, launch.executable_path)
    provider = FakeProcessProvider(
        WindowsProcessCapture((root, child)),
        WindowsProcessCapture((root,)),
    )
    tracker = BrowserProcessTreeTracker(provider)

    first = tracker.capture(launch)
    second = tracker.capture(launch)

    assert first.browser_process_ids == frozenset({100, 101})
    assert second.browser_process_ids == frozenset({100})


def test_process_tree_rejects_prelaunch_and_wrong_image_descendants(tmp_path: Path):
    launch = authority(tmp_path)
    provider = FakeProcessProvider(
        WindowsProcessCapture(
            (
                process(100, 1, 10_000, launch.executable_path),
                process(101, 100, 9_999, launch.executable_path),
                process(102, 100, 10_010, Path("C:/Windows/helper.exe")),
            )
        )
    )

    snapshot = BrowserProcessTreeTracker(provider).capture(launch)

    assert snapshot.browser_process_ids == frozenset({100})
    assert 101 not in {record.process_id for record in snapshot.records}


def test_process_tree_fails_closed_on_capture_and_traversal_bounds(tmp_path: Path):
    launch = authority(tmp_path)
    unavailable = BrowserProcessTreeTracker(FakeProcessProvider(error=True)).capture(
        launch
    )
    table_bounded = BrowserProcessTreeTracker(
        FakeProcessProvider(WindowsProcessCapture((), truncated=True))
    ).capture(launch)
    traversal_bounded = BrowserProcessTreeTracker(
        FakeProcessProvider(
            WindowsProcessCapture(
                (
                    process(100, 1, 10_000, launch.executable_path),
                    process(101, 100, 10_001, launch.executable_path),
                )
            )
        ),
        max_descendants=1,
    ).capture(launch)

    assert unavailable.status == BrowserProcessTreeStatus.UNAVAILABLE
    assert table_bounded.status == BrowserProcessTreeStatus.BOUNDED
    assert traversal_bounded.status == BrowserProcessTreeStatus.BOUNDED


def test_process_tree_launch_identity_cannot_be_replaced(tmp_path: Path):
    launch = authority(tmp_path)
    changed = replace(launch, launch_id="other-launch-123456")

    assert changed.launch_id != launch.launch_id
    assert changed.root_creation_time_100ns == launch.root_creation_time_100ns
