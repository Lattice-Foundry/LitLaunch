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
