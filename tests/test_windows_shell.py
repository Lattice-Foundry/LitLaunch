from pathlib import Path

import pytest

from litlaunch._windows_shell import (
    WindowsShellLaunchError,
    WindowsShellProcess,
    open_windows_shortcut_with_process,
)


def test_shell_process_identity_is_immutable_and_validated():
    process = WindowsShellProcess(4321, 123456789)

    assert process.process_id == 4321
    assert process.creation_time_100ns == 123456789


@pytest.mark.parametrize(
    ("process_id", "creation_time"),
    [(0, 1), (-1, 1), (True, 1), (1, 0), (1, -1), (1, True)],
)
def test_shell_process_identity_rejects_invalid_values(
    process_id: object,
    creation_time: object,
):
    with pytest.raises(WindowsShellLaunchError):
        WindowsShellProcess(process_id, creation_time)  # type: ignore[arg-type]


def test_shell_shortcut_activation_rejects_missing_or_malformed_path(
    tmp_path: Path,
):
    with pytest.raises(WindowsShellLaunchError):
        open_windows_shortcut_with_process(tmp_path / "missing.lnk")

    malformed = tmp_path / "not-a-shortcut.txt"
    malformed.write_text("not a shortcut", encoding="utf-8")
    with pytest.raises(WindowsShellLaunchError):
        open_windows_shortcut_with_process(malformed)
