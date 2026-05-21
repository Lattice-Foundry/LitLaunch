"""Owned subprocess management for LitLaunch."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from litlaunch._protocols import ManagedPopen
from litlaunch.exceptions import ProcessError


@dataclass(frozen=True)
class ManagedProcess:
    """A subprocess started and owned by LitLaunch."""

    popen: ManagedPopen
    command: tuple[str, ...]


class ProcessManager:
    """Start and stop only subprocesses created by this manager."""

    def __init__(
        self,
        *,
        popen_factory: Callable[..., ManagedPopen] = subprocess.Popen,
    ) -> None:
        self.popen_factory = popen_factory

    def start(
        self,
        command: Sequence[str],
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> ManagedProcess:
        """Start a command sequence without shell execution."""

        normalized = self._normalize_command(command)
        popen = self.popen_factory(
            normalized,
            cwd=str(cwd) if cwd is not None else None,
            env=dict(env) if env is not None else None,
            shell=False,
        )
        return ManagedProcess(popen=popen, command=normalized)

    def is_running(self, process: ManagedProcess) -> bool:
        """Return whether the managed process is still running."""

        return process.popen.poll() is None

    def wait(
        self,
        process: ManagedProcess,
        timeout_seconds: float | None = None,
    ) -> int | None:
        """Wait for one managed process to exit and return its code."""

        return process.popen.wait(timeout=timeout_seconds)

    def stop(
        self,
        process: ManagedProcess,
        terminate_timeout_seconds: float = 5.0,
    ) -> None:
        """Stop a managed process, escalating to kill only after timeout."""

        if not self.is_running(process):
            return

        process.popen.terminate()
        try:
            process.popen.wait(timeout=terminate_timeout_seconds)
            return
        except subprocess.TimeoutExpired:
            pass

        if self.is_running(process):
            process.popen.kill()
            try:
                process.popen.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                return

    def _normalize_command(self, command: Sequence[str]) -> tuple[str, ...]:
        if isinstance(command, (str, bytes)):
            raise ProcessError("Command must be a non-empty sequence, not a string.")
        try:
            normalized = tuple(str(part) for part in command)
        except TypeError as exc:
            raise ProcessError("Command must be a non-empty sequence.") from exc
        if not normalized:
            raise ProcessError("Command must be a non-empty sequence.")
        if any(not part for part in normalized):
            raise ProcessError("Command arguments cannot be empty.")
        return normalized
