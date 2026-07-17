import socket

import pytest

from litlaunch import LauncherConfig
from litlaunch.exceptions import PortError
from litlaunch.ports import PortManager


class FakePortManager(PortManager):
    def __init__(self, available_ports):
        self.available_ports = set(available_ports)
        self.checked_ports = []

    def is_port_available(self, host: str, port: int) -> bool:
        self.checked_ports.append((host, port))
        self.validate_port(port)
        return port in self.available_ports


class FakeSocket:
    def __init__(self, family, socktype, proto, log, busy_addresses):
        self.family = family
        self.socktype = socktype
        self.proto = proto
        self.log = log
        self.busy_addresses = busy_addresses
        self.options = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        return False

    def setsockopt(self, *_args):
        self.options.append(_args)
        return None

    def bind(self, sockaddr):
        self.log.append((self.family, self.socktype, self.proto, sockaddr))
        if sockaddr in self.busy_addresses:
            raise OSError("busy")


class FakeSocketFactory:
    def __init__(self, *, busy_addresses=()):
        self.log = []
        self.sockets = []
        self.busy_addresses = set(busy_addresses)

    def __call__(self, family, socktype, proto=0):
        fake = FakeSocket(family, socktype, proto, self.log, self.busy_addresses)
        self.sockets.append(fake)
        return fake


def test_fixed_available_port_returns_as_expected():
    manager = FakePortManager({8501})
    config = LauncherConfig(app_path="app.py", port=8501, auto_port=False)

    assert manager.resolve_port(config) == 8501
    assert manager.checked_ports == [("127.0.0.1", 8501)]


def test_unavailable_fixed_port_without_auto_raises():
    manager = FakePortManager(set())
    config = LauncherConfig(app_path="app.py", port=8501, auto_port=False)

    with pytest.raises(PortError, match="already in use"):
        manager.resolve_port(config)


def test_unavailable_fixed_port_with_auto_finds_next_available():
    manager = FakePortManager({8503})
    config = LauncherConfig(app_path="app.py", port=8501, auto_port=True)

    assert manager.resolve_port(config) == 8503
    assert manager.checked_ports == [
        ("127.0.0.1", 8501),
        ("127.0.0.1", 8502),
        ("127.0.0.1", 8503),
    ]


def test_unavailable_default_port_with_auto_finds_next_available():
    manager = FakePortManager({8502})
    config = LauncherConfig(app_path="app.py", port_range=[8501, 8599])

    assert manager.resolve_port(config) == 8502
    assert manager.checked_ports == [
        ("127.0.0.1", 8501),
        ("127.0.0.1", 8502),
    ]


def test_auto_port_obeys_configured_port_range():
    manager = FakePortManager({8511})
    config = LauncherConfig(
        app_path="app.py",
        port=8509,
        auto_port=True,
        port_range=[8509, 8511],
    )

    assert manager.resolve_port(config) == 8511
    assert manager.checked_ports == [
        ("127.0.0.1", 8509),
        ("127.0.0.1", 8510),
        ("127.0.0.1", 8511),
    ]


def test_auto_port_wraps_below_requested_port_within_range():
    manager = FakePortManager({8505})
    config = LauncherConfig(
        app_path="app.py",
        port=8510,
        auto_port=True,
        port_range=[8500, 8520],
    )

    # Only 8505 (below the requested 8510) is free; the whole declared range is
    # usable, so auto-port wraps down after exhausting the higher ports.
    assert manager.resolve_port(config) == 8505
    assert manager.checked_ports[0] == ("127.0.0.1", 8510)
    assert ("127.0.0.1", 8505) in manager.checked_ports


def test_auto_port_exhausted_range_errors_with_range_message():
    manager = FakePortManager(set())
    config = LauncherConfig(
        app_path="app.py",
        port=8510,
        auto_port=True,
        port_range=[8500, 8520],
    )

    with pytest.raises(PortError, match="no free port remains"):
        manager.resolve_port(config)


def test_exhausted_port_range_errors_cleanly():
    manager = FakePortManager(set())
    config = LauncherConfig(app_path="app.py", port_range=[8501, 8502])

    with pytest.raises(PortError, match="No available port found"):
        manager.resolve_port(config)


def test_port_none_finds_available_from_default_start():
    manager = FakePortManager({8502})
    config = LauncherConfig(app_path="app.py")

    assert manager.resolve_port(config) == 8502
    assert manager.checked_ports == [
        ("127.0.0.1", 8501),
        ("127.0.0.1", 8502),
    ]


@pytest.mark.parametrize("port", [0, 65536, -1, True, "8501"])
def test_invalid_port_raises(port):
    manager = PortManager()

    with pytest.raises(PortError):
        manager.validate_port(port)


def test_port_manager_exposes_no_kill_methods():
    manager = PortManager()

    assert not hasattr(manager, "kill")
    assert not hasattr(manager, "terminate")


def test_port_manager_uses_getaddrinfo_for_ipv4_and_ipv6(monkeypatch):
    def fake_getaddrinfo(host, port, *, type, proto):
        assert host == "localhost"
        assert port == 8501
        assert type == socket.SOCK_STREAM
        assert proto == socket.IPPROTO_TCP
        return [
            (
                socket.AF_INET6,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("::1", 8501, 0, 0),
            ),
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("127.0.0.1", 8501),
            ),
        ]

    fake_socket_factory = FakeSocketFactory()
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    manager = PortManager(socket_factory=fake_socket_factory)

    assert manager.is_port_available("localhost", 8501) is True
    assert fake_socket_factory.log == [
        (
            socket.AF_INET6,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            ("::1", 8501, 0, 0),
        ),
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            ("127.0.0.1", 8501),
        ),
    ]
    for fake_socket in fake_socket_factory.sockets:
        assert all(option[1] != socket.SO_REUSEADDR for option in fake_socket.options)


def test_port_manager_normalizes_bracketed_ipv6_hosts(monkeypatch):
    def fake_getaddrinfo(host, port, *, type, proto):
        assert host == "::1"
        assert port == 8501
        return [
            (
                socket.AF_INET6,
                type,
                proto,
                "",
                ("::1", 8501, 0, 0),
            )
        ]

    fake_socket_factory = FakeSocketFactory()
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    manager = PortManager(socket_factory=fake_socket_factory)

    assert manager.is_port_available("[::1]", 8501) is True


def test_port_manager_requires_all_resolved_addresses_available(monkeypatch):
    def fake_getaddrinfo(host, port, *, type, proto):
        return [
            (
                socket.AF_INET6,
                type,
                proto,
                "",
                ("::1", port, 0, 0),
            ),
            (
                socket.AF_INET,
                type,
                proto,
                "",
                ("127.0.0.1", port),
            ),
        ]

    fake_socket_factory = FakeSocketFactory(busy_addresses={("127.0.0.1", 8501)})
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    manager = PortManager(socket_factory=fake_socket_factory)

    assert manager.is_port_available("localhost", 8501) is False
