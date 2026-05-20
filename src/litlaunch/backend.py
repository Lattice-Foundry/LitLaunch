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


@dataclass(frozen=True)
class BackendCommand:
    """Shell-free command returned by a backend command provider."""

    command: Sequence[str]
    description: str = "backend"
    backend_kind: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.command, (str, bytes)):
            raise CommandBuildError("Backend command must be a sequence of strings.")
        try:
            command = tuple(str(part) for part in self.command)
        except TypeError as exc:
            raise CommandBuildError(
                "Backend command must be a sequence of strings."
            ) from exc
        if not command:
            raise CommandBuildError("Backend command cannot be empty.")
        if any(not part for part in command):
            raise CommandBuildError("Backend command arguments cannot be empty.")
        object.__setattr__(self, "command", command)

        description = str(self.description).strip()
        if not description:
            raise CommandBuildError("Backend command description cannot be empty.")
        object.__setattr__(self, "description", description)

        if self.backend_kind is not None:
            kind = str(self.backend_kind).strip()
            object.__setattr__(self, "backend_kind", kind or None)


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
