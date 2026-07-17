"""Port management for LitLaunch backend runs."""

from __future__ import annotations

import socket
from collections.abc import Callable
from typing import TypeAlias, cast

from litlaunch.config import LauncherConfig
from litlaunch.exceptions import PortError

_SocketAddress: TypeAlias = tuple[str, int] | tuple[str, int, int, int]
_SocketAddressInfo: TypeAlias = tuple[
    socket.AddressFamily,
    socket.SocketKind,
    int,
    _SocketAddress,
]


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
            addresses = self._bind_addresses(host, port)
        except OSError:
            return False

        if not addresses:
            return False

        try:
            for family, socktype, proto, sockaddr in addresses:
                with self.socket_factory(family, socktype, proto) as sock:
                    _set_exclusive_bind_options(sock)
                    sock.bind(sockaddr)
        except OSError:
            return False
        return True

    def _bind_addresses(
        self,
        host: str,
        port: int,
    ) -> tuple[_SocketAddressInfo, ...]:
        """Resolve host/port pairs into bindable socket addresses."""

        bind_host = _normalize_bind_host(host)
        infos = socket.getaddrinfo(
            bind_host,
            port,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
        addresses: list[_SocketAddressInfo] = []
        seen: set[_SocketAddressInfo] = set()
        for family, socktype, proto, _canonname, sockaddr in infos:
            key = cast(_SocketAddressInfo, (family, socktype, proto, sockaddr))
            if key in seen:
                continue
            seen.add(key)
            addresses.append(key)
        return tuple(addresses)

    def find_available_port(
        self,
        host: str,
        start_port: int = 8501,
        max_attempts: int = 100,
        end_port: int | None = None,
    ) -> int:
        """Find the first available port at or after start_port."""

        self.validate_port(start_port)
        if end_port is not None:
            self.validate_port(end_port)
            if end_port < start_port:
                raise PortError("end_port must be greater than or equal to start_port.")
        if max_attempts < 1:
            raise PortError("max_attempts must be at least 1.")

        for offset in range(max_attempts):
            candidate = start_port + offset
            if candidate > 65535:
                break
            if end_port is not None and candidate > end_port:
                break
            if self.is_port_available(host, candidate):
                return candidate

        range_text = f" through {end_port}" if end_port is not None else ""
        raise PortError(
            f"No available port found on {host} starting at {start_port}"
            f"{range_text} after {max_attempts} attempts."
        )

    def resolve_port(self, config: LauncherConfig) -> int:
        """Resolve the concrete Streamlit port for a launcher config."""

        host = config.host or self.host
        range_start, range_end = _port_range_bounds(config)
        if config.port is None:
            return self.find_available_port(
                host,
                range_start,
                max_attempts=_range_attempts(range_start, range_end),
                end_port=range_end,
            )

        port = self.validate_port(config.port)
        if self.is_port_available(host, port):
            return port

        if not config.auto_port:
            raise PortError(
                f"Port {port} is already in use on {host}. "
                "Close the existing app, choose another port, or enable auto-port."
            )

        # auto_port: prefer higher ports within the configured range, then wrap
        # to lower ports so the whole declared range stays usable, not just ports
        # above the requested one.
        for candidate in _auto_port_candidates(port, range_start, range_end):
            if self.is_port_available(host, candidate):
                return candidate
        raise PortError(
            f"Port {port} is unavailable and no free port remains in "
            f"{range_start} through {range_end}."
        )


def _auto_port_candidates(port: int, range_start: int, range_end: int) -> list[int]:
    """Return adaptive port candidates: higher ports first, then wrap to lower.

    The requested port is excluded because it was already probed. Ordering is
    deterministic so two runs behave predictably.
    """

    return [*range(port + 1, range_end + 1), *range(range_start, port)]


def _port_range_bounds(config: LauncherConfig) -> tuple[int, int]:
    if config.port_range is not None:
        return config.port_range
    start = config.port if config.port is not None else 8501
    return (start, min(65535, start + 99))


def _range_attempts(start_port: int, end_port: int) -> int:
    return max(1, end_port - start_port + 1)


def _set_exclusive_bind_options(sock: socket.socket) -> None:
    exclusive_addr_use = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
    if exclusive_addr_use is not None:
        sock.setsockopt(socket.SOL_SOCKET, exclusive_addr_use, 1)


def _normalize_bind_host(host: str) -> str:
    """Normalize URL-style hosts into socket bind hosts."""

    if host.startswith("[") and host.endswith("]"):
        return host[1:-1]
    return host
