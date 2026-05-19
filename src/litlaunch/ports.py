"""Port management for LitLaunch backend runs."""

from __future__ import annotations

import socket
from collections.abc import Callable

from litlaunch.config import LauncherConfig
from litlaunch.exceptions import PortError


class PortManager:
    """Resolve Streamlit backend ports without touching existing owners."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        *,
        socket_factory: Callable[..., socket.socket] = socket.socket,
    ) -> None:
        self.host = host
        self.socket_factory = socket_factory

    def validate_port(self, port: int) -> int:
        """Validate and return a TCP port number."""

        if not isinstance(port, int) or isinstance(port, bool):
            raise PortError("Port must be an integer from 1 to 65535.")
        if port < 1 or port > 65535:
            raise PortError("Port must be an integer from 1 to 65535.")
        return port

    def is_port_available(self, host: str, port: int) -> bool:
        """Return whether a port can be bound on the requested host."""

        self.validate_port(port)
        try:
            with self.socket_factory(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((host, port))
        except OSError:
            return False
        return True

    def find_available_port(
        self,
        host: str,
        start_port: int = 8501,
        max_attempts: int = 100,
    ) -> int:
        """Find the first available port at or after start_port."""

        self.validate_port(start_port)
        if max_attempts < 1:
            raise PortError("max_attempts must be at least 1.")

        for offset in range(max_attempts):
            candidate = start_port + offset
            if candidate > 65535:
                break
            if self.is_port_available(host, candidate):
                return candidate

        raise PortError(
            f"No available port found on {host} starting at {start_port} "
            f"after {max_attempts} attempts."
        )

    def resolve_port(self, config: LauncherConfig) -> int:
        """Resolve the concrete Streamlit port for a launcher config."""

        host = config.host or self.host
        if config.port is None:
            return self.find_available_port(host, 8501)

        port = self.validate_port(config.port)
        if self.is_port_available(host, port):
            return port

        if not config.auto_port:
            raise PortError(f"Port {port} is already in use on {host}.")

        next_port = port + 1
        if next_port > 65535:
            raise PortError(f"Port {port} is unavailable and no higher port exists.")
        return self.find_available_port(host, next_port)
