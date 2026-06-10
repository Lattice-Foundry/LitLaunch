"""Backend command provider abstractions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from litlaunch.config import LauncherConfig
from litlaunch.exceptions import CommandBuildError
from litlaunch.streamlit import StreamlitCommandBuilder


@dataclass(frozen=True)
class BackendCommandContext:
    """Resolved launch context passed to backend command providers."""

    config: LauncherConfig
    host: str
    port: int
    app_url: str
    health_url: str
    headless: bool


@dataclass(frozen=True, init=False)
class BackendCommand:
    """Shell-free command returned by a backend command provider."""

    command: tuple[str, ...]
    description: str
    backend_kind: str | None

    def __init__(
        self,
        command: Sequence[str],
        description: str = "backend",
        backend_kind: str | None = None,
    ) -> None:
        if isinstance(command, (str, bytes)):
            raise CommandBuildError("Backend command must be a sequence of strings.")
        try:
            normalized_command = tuple(str(part) for part in command)
        except TypeError as exc:
            raise CommandBuildError(
                "Backend command must be a sequence of strings."
            ) from exc
        if not normalized_command:
            raise CommandBuildError("Backend command cannot be empty.")
        if any(not part for part in normalized_command):
            raise CommandBuildError("Backend command arguments cannot be empty.")
        object.__setattr__(self, "command", normalized_command)

        normalized_description = str(description).strip()
        if not normalized_description:
            raise CommandBuildError("Backend command description cannot be empty.")
        object.__setattr__(self, "description", normalized_description)

        normalized_kind = None
        if backend_kind is not None:
            kind = str(backend_kind).strip()
            normalized_kind = kind or None
        object.__setattr__(self, "backend_kind", normalized_kind)


class BackendCommandProvider(Protocol):
    """Protocol for command-only backend customization."""

    def build_backend_command(
        self,
        context: BackendCommandContext,
    ) -> BackendCommand:
        """Return the backend command LitLaunch should start."""


class StreamlitBackendCommandProvider:
    """Default backend command provider for source Streamlit apps."""

    description = "Streamlit backend"
    backend_kind = "streamlit"

    def build_backend_command(
        self,
        context: BackendCommandContext,
    ) -> BackendCommand:
        """Build the standard `python -m streamlit run ...` command."""

        return BackendCommand(
            command=StreamlitCommandBuilder(context.config).build(port=context.port),
            description=self.description,
            backend_kind=self.backend_kind,
        )
