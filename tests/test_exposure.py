from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pytest

from litlaunch.config import LauncherConfig
from litlaunch.console import ConsoleRenderer
from litlaunch.exceptions import LitLaunchError
from litlaunch.exposure import (
    classify_host_exposure,
    is_loopback_host,
    network_exposure_acknowledged,
    validate_host_exposure_policy,
)
from litlaunch.inspect import DiagnosticCollector
from litlaunch.launcher import StreamlitLauncher
from litlaunch.platforms import Architecture, OperatingSystem, PlatformInfo


@pytest.fixture
def tmp_path():
    with tempfile.TemporaryDirectory(prefix="litlaunch-exposure-") as path:
        yield Path(path)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
def test_loopback_hosts_are_not_exposed(host: str):
    exposure = classify_host_exposure(host)

    assert is_loopback_host(host)
    assert exposure.is_loopback is True
    assert exposure.warning is None


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.10", "app.internal"])
def test_non_loopback_hosts_are_exposed(host: str):
    exposure = classify_host_exposure(host)

    assert not is_loopback_host(host)
    assert exposure.exposed is True
    assert "not loopback-only" in (exposure.warning or "")


def test_network_exposure_acknowledgement_accepts_flag_or_env():
    assert network_exposure_acknowledged(allow_network_exposure=True)
    assert network_exposure_acknowledged(env={"LITLAUNCH_ALLOW_NETWORK_EXPOSURE": "1"})
    assert not network_exposure_acknowledged(env={})


def test_development_requires_acknowledgement_for_non_loopback():
    with pytest.raises(ValueError, match="Network exposure requires"):
        validate_host_exposure_policy(
            host="0.0.0.0",
            trust_mode="development",
            allow_network_exposure=False,
            env={},
        )

    exposure = validate_host_exposure_policy(
        host="0.0.0.0",
        trust_mode="development",
        allow_network_exposure=True,
        env={},
    )

    assert exposure.exposed is True


def test_strict_local_refuses_non_loopback_even_when_acknowledged():
    with pytest.raises(ValueError, match="strict_local requires loopback-only"):
        validate_host_exposure_policy(
            host="0.0.0.0",
            trust_mode="strict_local",
            allow_network_exposure=True,
            env={"LITLAUNCH_ALLOW_NETWORK_EXPOSURE": "1"},
        )


def test_internal_network_requires_acknowledgement_for_non_loopback():
    with pytest.raises(ValueError, match="Network exposure requires"):
        validate_host_exposure_policy(
            host="0.0.0.0",
            trust_mode="internal_network",
            allow_network_exposure=False,
            env={},
        )

    exposure = validate_host_exposure_policy(
        host="0.0.0.0",
        trust_mode="internal_network",
        allow_network_exposure=False,
        env={"LITLAUNCH_ALLOW_NETWORK_EXPOSURE": "1"},
    )

    assert exposure.exposed is True


def test_launcher_blocks_unacknowledged_network_exposure(tmp_path: Path):
    app = tmp_path / "app.py"
    app.write_text("print('hi')\n", encoding="utf-8")
    stream = io.StringIO()
    launcher = StreamlitLauncher(
        LauncherConfig(app_path=app, host="0.0.0.0"),
        console_renderer=ConsoleRenderer(stream=stream, env={"NO_COLOR": "1"}),
    )

    with pytest.raises(LitLaunchError, match="Network exposure requires"):
        launcher.start_backend()

    output = stream.getvalue()
    assert "Runtime: network exposure requested." in output
    assert "0.0.0.0" in output


def test_launcher_strict_local_blocks_even_acknowledged_network_exposure(
    tmp_path: Path,
):
    app = tmp_path / "app.py"
    app.write_text("print('hi')\n", encoding="utf-8")
    launcher = StreamlitLauncher(
        LauncherConfig(
            app_path=app,
            host="0.0.0.0",
            trust_mode="strict_local",
            allow_network_exposure=True,
        ),
        console_renderer=ConsoleRenderer(stream=io.StringIO(), env={"NO_COLOR": "1"}),
    )

    with pytest.raises(LitLaunchError, match="strict_local requires loopback-only"):
        launcher.start_backend()


def test_diagnostics_warn_about_non_loopback_host(tmp_path: Path):
    app = tmp_path / "app.py"
    app.write_text("print('hi')\n", encoding="utf-8")
    report = DiagnosticCollector(
        platform_detector=FakePlatformDetector(),
        browser_registry=FakeBrowserRegistry(),
        streamlit_checker=lambda: FakeStreamlitAvailability(),
    ).collect(app_path=app, host="0.0.0.0")

    target = next(section for section in report.sections if section.title == "Target")
    host_item = next(item for item in target.items if item.name == "Host binding")

    assert host_item.status.value == "warning"
    assert "0.0.0.0 may be reachable" in host_item.message
    assert "does not secure Streamlit" in (host_item.detail or "")


def test_diagnostics_report_trust_mode(tmp_path: Path):
    app = tmp_path / "app.py"
    app.write_text("print('hi')\n", encoding="utf-8")
    report = DiagnosticCollector(
        platform_detector=FakePlatformDetector(),
        browser_registry=FakeBrowserRegistry(),
        streamlit_checker=lambda: FakeStreamlitAvailability(),
    ).collect(app_path=app, trust_mode="internal_network")

    target = next(section for section in report.sections if section.title == "Target")
    trust_item = next(item for item in target.items if item.name == "Trust mode")

    assert trust_item.message == "internal_network"


class FakePlatformDetector:
    def detect(self) -> PlatformInfo:
        return PlatformInfo(
            os=OperatingSystem.WINDOWS,
            architecture=Architecture.X64,
            python_version="3.14.5",
            python_executable="X:/Python/python.exe",
            machine="AMD64",
            system="Windows",
            release="11",
            is_windows=True,
            is_macos=False,
            is_linux=False,
            supports_chromium_app_mode=True,
            supports_window_monitoring=True,
            supports_default_browser_open=True,
            notes=(),
        )


class FakeStreamlitAvailability:
    available = True
    message = "Streamlit is available."


class FakeBrowserRegistry:
    def detect_all(self, platform_info):
        return ()

    def resolve(
        self,
        browser,
        platform_info=None,
        *,
        prefer_app_mode=False,
        allow_fallback=True,
    ):
        from litlaunch.browsers.base import BrowserResolution

        return BrowserResolution(
            requested=browser,
            selected=None,
            fallback_chain=(),
            message="Browser resolution skipped.",
        )
