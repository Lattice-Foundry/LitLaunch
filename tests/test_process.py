import subprocess

import pytest

from litlaunch.exceptions import ProcessError
from litlaunch.process import ManagedProcess, ProcessManager


class FakePopen:
    pid = 4321

    def __init__(
        self,
        *,
        returncode=None,
        timeout_on_wait=False,
        timeout_after_kill=False,
    ):
        self.returncode = returncode
        self.timeout_on_wait = timeout_on_wait
        self.timeout_after_kill = timeout_after_kill
        self.calls = []

    def poll(self):
        return self.returncode

    def terminate(self):
        self.calls.append("terminate")
        if not self.timeout_on_wait:
            self.returncode = 0

    def kill(self):
        self.calls.append("kill")
        self.returncode = -9

    def wait(self, timeout=None):
        self.calls.append(("wait", timeout))
        if self.timeout_on_wait and "kill" not in self.calls:
            raise subprocess.TimeoutExpired("fake", timeout)
        if self.timeout_after_kill and "kill" in self.calls:
            raise subprocess.TimeoutExpired("fake", timeout)
        self.returncode = 0 if self.returncode is None else self.returncode
        return self.returncode


def test_start_rejects_string_command():
    manager = ProcessManager()

    with pytest.raises(ProcessError, match="not a string"):
        manager.start("python -m streamlit")


def test_start_rejects_empty_command():
    manager = ProcessManager()

    with pytest.raises(ProcessError, match="non-empty"):
        manager.start([])


def test_start_passes_args_without_shell_true():
    calls = []
    fake = FakePopen()

    def popen_factory(command, **kwargs):
        calls.append((command, kwargs))
        return fake

    manager = ProcessManager(popen_factory=popen_factory)
    process = manager.start(("python", "-m", "streamlit"), cwd="X:/app", env={"A": "1"})

    assert process == ManagedProcess(fake, ("python", "-m", "streamlit"))
    assert calls == [
        (
            ("python", "-m", "streamlit"),
            {"cwd": "X:/app", "env": {"A": "1"}, "shell": False},
        )
    ]


def test_is_running_reflects_poll_result():
    manager = ProcessManager()

    assert (
        manager.is_running(ManagedProcess(FakePopen(returncode=None), ("cmd",))) is True
    )
    assert (
        manager.is_running(ManagedProcess(FakePopen(returncode=0), ("cmd",))) is False
    )


def test_wait_delegates_to_owned_process():
    fake = FakePopen(returncode=7)
    manager = ProcessManager()

    assert manager.wait(ManagedProcess(fake, ("cmd",)), timeout_seconds=4.0) == 7
    assert fake.calls == [("wait", 4.0)]


def test_process_manager_exposes_stop_as_public_safe_shutdown_path():
    manager = ProcessManager()

    assert hasattr(manager, "stop")
    assert not hasattr(manager, "terminate")
    assert not hasattr(manager, "kill")


def test_stop_does_nothing_if_already_exited():
    fake = FakePopen(returncode=0)
    manager = ProcessManager()

    manager.stop(ManagedProcess(fake, ("cmd",)))

    assert fake.calls == []


def test_stop_terminates_owned_running_process():
    fake = FakePopen(returncode=None)
    manager = ProcessManager()

    manager.stop(ManagedProcess(fake, ("cmd",)), terminate_timeout_seconds=2.0)

    assert fake.calls == ["terminate", ("wait", 2.0)]


def test_stop_kills_only_after_terminate_timeout():
    fake = FakePopen(returncode=None, timeout_on_wait=True)
    manager = ProcessManager()

    manager.stop(ManagedProcess(fake, ("cmd",)), terminate_timeout_seconds=2.0)

    assert fake.calls == ["terminate", ("wait", 2.0), "kill", ("wait", 1.0)]


def test_stop_does_not_raise_when_post_kill_wait_times_out():
    fake = FakePopen(
        returncode=None,
        timeout_on_wait=True,
        timeout_after_kill=True,
    )
    manager = ProcessManager()

    manager.stop(ManagedProcess(fake, ("cmd",)), terminate_timeout_seconds=2.0)

    assert fake.calls == ["terminate", ("wait", 2.0), "kill", ("wait", 1.0)]
