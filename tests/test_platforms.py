from litlaunch import Architecture, OperatingSystem, PlatformDetector
from litlaunch.platforms.detect import normalize_architecture, normalize_os


def make_detector(
    *,
    system: str,
    machine: str = "AMD64",
    release: str = "test-release",
    python_version: str = "3.14.5",
    executable: str = "C:/Python/python.exe",
) -> PlatformDetector:
    return PlatformDetector(
        system_func=lambda: system,
        machine_func=lambda: machine,
        release_func=lambda: release,
        python_version_func=lambda: python_version,
        executable_provider=lambda: executable,
    )


def test_os_normalization():
    assert normalize_os("Windows") == OperatingSystem.WINDOWS
    assert normalize_os("Darwin") == OperatingSystem.MACOS
    assert normalize_os("Linux") == OperatingSystem.LINUX
    assert normalize_os("Plan9") == OperatingSystem.UNKNOWN


def test_architecture_normalization():
    assert normalize_architecture("AMD64") == Architecture.X64
    assert normalize_architecture("x86_64") == Architecture.X64
    assert normalize_architecture("arm64") == Architecture.ARM64
    assert normalize_architecture("aarch64") == Architecture.ARM64
    assert normalize_architecture("i386") == Architecture.X86
    assert normalize_architecture("i686") == Architecture.X86
    assert normalize_architecture("x86") == Architecture.X86
    assert normalize_architecture("mystery") == Architecture.UNKNOWN
    assert normalize_architecture("") == Architecture.UNKNOWN


def test_windows_capabilities():
    info = make_detector(system="Windows", machine="AMD64").detect()

    assert info.os == OperatingSystem.WINDOWS
    assert info.architecture == Architecture.X64
    assert info.is_windows is True
    assert info.is_macos is False
    assert info.is_linux is False
    assert info.supports_default_browser_open is True
    assert info.supports_chromium_app_mode is True
    assert info.supports_window_monitoring is True
    assert any("Windows-first" in note for note in info.notes)


def test_macos_and_linux_support_chromium_app_mode_without_window_monitoring():
    for system, expected_os in (
        ("Darwin", OperatingSystem.MACOS),
        ("Linux", OperatingSystem.LINUX),
    ):
        info = make_detector(system=system, machine="arm64").detect()

        assert info.os == expected_os
        assert info.architecture == Architecture.ARM64
        assert info.supports_default_browser_open is True
        assert info.supports_chromium_app_mode is True
        assert info.supports_window_monitoring is False


def test_unknown_os_uses_conservative_capabilities_and_notes():
    info = make_detector(system="Plan9", machine="weirdcpu").detect()

    assert info.os == OperatingSystem.UNKNOWN
    assert info.architecture == Architecture.UNKNOWN
    assert info.is_windows is False
    assert info.is_macos is False
    assert info.is_linux is False
    assert info.supports_default_browser_open is False
    assert info.supports_chromium_app_mode is False
    assert info.supports_window_monitoring is False
    assert "Unsupported or unknown operating system." in info.notes
    assert "Unknown CPU architecture." in info.notes


def test_platform_summary_is_deterministic():
    info = make_detector(
        system="Windows",
        machine="x86_64",
        python_version="3.14.5",
    ).detect()

    assert info.summary() == "Windows x64 / Python 3.14.5"


def test_platform_as_dict_contains_expected_keys():
    info = make_detector(
        system="Linux",
        machine="aarch64",
        release="6.1",
        python_version="3.12.3",
        executable="/usr/bin/python",
    ).detect()

    data = info.as_dict()

    assert data == {
        "os": "linux",
        "architecture": "arm64",
        "python_version": "3.12.3",
        "python_executable": "/usr/bin/python",
        "machine": "aarch64",
        "system": "Linux",
        "release": "6.1",
        "is_windows": False,
        "is_macos": False,
        "is_linux": True,
        "supports_chromium_app_mode": True,
        "supports_window_monitoring": False,
        "supports_default_browser_open": True,
        "notes": (),
    }
    assert isinstance(info.notes, tuple)
