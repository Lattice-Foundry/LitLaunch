"""Public launcher facade."""

from __future__ import annotations

from litlaunch.config import LauncherConfig
from litlaunch.streamlit import StreamlitCommandBuilder


class StreamlitLauncher:
    """High-level Streamlit launcher facade."""

    def __init__(self, config: LauncherConfig) -> None:
        self.config = config
        self.command_builder = StreamlitCommandBuilder(config)

    def build_command(self) -> tuple[str, ...]:
        """Build the Streamlit command without starting a process."""

        return self.command_builder.build()

    def run(self) -> None:
        """Run the configured Streamlit app.

        Full process lifecycle management is intentionally deferred until the
        process, shutdown, browser, and diagnostics boundaries are implemented.
        """

        raise NotImplementedError(
            "StreamlitLauncher.run() is not implemented in the foundation pass."
        )
