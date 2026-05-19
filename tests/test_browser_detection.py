from dataclasses import replace

from litlaunch import BrowserChoice
from litlaunch.browsers import (
    BrowserCapability,
    BrowserKind,
    BrowserRegistry,
    ChromeAdapter,
    DefaultBrowserAdapter,
    EdgeAdapter,
)
from litlaunch.diagnostics import Diagnostics
from litlaunch.platforms import PlatformDetector


def platform_info(system: str):
    return PlatformDetector(
        system_func=lambda: system,
        machine_func=lambda: "AMD64",
        release_func=lambda: "test",
        python_version_func=lambda: "3.14.5",
        executable_provider=lambda: "python",
    ).detect()


def test_browser_capability_is_immutable_and_notes_are_tuples():
    capability = BrowserCapability(
        kind=BrowserKind.EDGE,
        name="Microsoft Edge",
        executable_path=None,
        available=False,
        supports_app_mode=True,
        supports_full_browser=True,
        notes=("not found",),
    )

    assert capability.available is False
    assert isinstance(capability.notes, tuple)


def test_edge_detects_executable_from_injected_path_lookup():
    adapter = EdgeAdapter(which_func=lambda name: "C:/Edge/msedge.exe")

    capability = adapter.detect(platform_info("Windows"))

    assert capability.kind == BrowserKind.EDGE
    assert capability.available is True
    assert capability.executable_path == "C:/Edge/msedge.exe"
    assert capability.supports_app_mode is True


def test_chrome_detects_executable_from_injected_path_lookup():
    adapter = ChromeAdapter(which_func=lambda name: "/usr/bin/google-chrome")

    capability = adapter.detect(platform_info("Linux"))

    assert capability.kind == BrowserKind.CHROME
    assert capability.available is True
    assert capability.executable_path == "/usr/bin/google-chrome"
    assert capability.supports_app_mode is True


def test_browser_unavailable_returns_clean_capability_without_launching():
    calls = []
    adapter = EdgeAdapter(
        which_func=lambda name: calls.append(name) or None,
        env={},
        path_exists_func=lambda path: False,
    )

    capability = adapter.detect(platform_info("Windows"))

    assert capability.available is False
    assert capability.executable_path is None
    assert capability.notes == ("Microsoft Edge executable was not detected.",)
    assert calls


def test_default_browser_detection_uses_platform_capability():
    adapter = DefaultBrowserAdapter()

    assert adapter.detect(platform_info("Windows")).available is True
    assert adapter.detect(platform_info("Plan9")).available is False


def test_windows_auto_app_mode_prefers_edge_before_chrome():
    registry = BrowserRegistry(
        (
            EdgeAdapter("C:/Edge/msedge.exe"),
            ChromeAdapter("C:/Chrome/chrome.exe"),
            DefaultBrowserAdapter(),
        )
    )

    resolution = registry.resolve(
        BrowserChoice.AUTO,
        platform_info("Windows"),
        prefer_app_mode=True,
    )

    assert resolution.selected is not None
    assert resolution.selected.kind == BrowserKind.EDGE
    assert [capability.kind for capability in resolution.fallback_chain] == [
        BrowserKind.EDGE,
        BrowserKind.CHROME,
        BrowserKind.DEFAULT,
    ]


def test_macos_and_linux_auto_app_mode_prefer_chrome_before_edge():
    for system in ("Darwin", "Linux"):
        registry = BrowserRegistry(
            (
                EdgeAdapter("/usr/bin/msedge"),
                ChromeAdapter("/usr/bin/chrome"),
                DefaultBrowserAdapter(),
            )
        )

        resolution = registry.resolve(
            BrowserChoice.AUTO,
            platform_info(system),
            prefer_app_mode=True,
        )

        assert resolution.selected is not None
        assert resolution.selected.kind == BrowserKind.CHROME
        assert resolution.fallback_chain[0].kind == BrowserKind.CHROME


def test_default_browser_resolves_for_full_browser_preference():
    registry = BrowserRegistry((DefaultBrowserAdapter(),))

    resolution = registry.resolve(
        BrowserChoice.DEFAULT,
        platform_info("Linux"),
        prefer_app_mode=False,
    )

    assert resolution.selected is not None
    assert resolution.selected.kind == BrowserKind.DEFAULT


def test_unknown_os_returns_default_only_when_platform_supports_it():
    unsupported = platform_info("Plan9")
    supported_unknown = replace(unsupported, supports_default_browser_open=True)
    registry = BrowserRegistry((DefaultBrowserAdapter(),))

    unsupported_resolution = registry.resolve(
        BrowserChoice.DEFAULT,
        unsupported,
        prefer_app_mode=False,
    )
    supported_resolution = registry.resolve(
        BrowserChoice.DEFAULT,
        supported_unknown,
        prefer_app_mode=False,
    )

    assert unsupported_resolution.selected is None
    assert supported_resolution.selected is not None
    assert supported_resolution.selected.kind == BrowserKind.DEFAULT


def test_explicit_edge_unavailable_without_fallback_selects_none():
    registry = BrowserRegistry(
        (
            EdgeAdapter(
                which_func=lambda name: None, path_exists_func=lambda path: False
            ),
            ChromeAdapter("C:/Chrome/chrome.exe"),
            DefaultBrowserAdapter(),
        )
    )

    resolution = registry.resolve(
        BrowserChoice.EDGE,
        platform_info("Windows"),
        prefer_app_mode=True,
        allow_fallback=False,
    )

    assert resolution.selected is None
    assert resolution.fallback_chain[0].kind == BrowserKind.EDGE


def test_explicit_edge_unavailable_with_fallback_selects_chrome():
    registry = BrowserRegistry(
        (
            EdgeAdapter(
                which_func=lambda name: None, path_exists_func=lambda path: False
            ),
            ChromeAdapter("C:/Chrome/chrome.exe"),
            DefaultBrowserAdapter(),
        )
    )

    resolution = registry.resolve(
        BrowserChoice.EDGE,
        platform_info("Windows"),
        prefer_app_mode=True,
        allow_fallback=True,
    )

    assert resolution.selected is not None
    assert resolution.selected.kind == BrowserKind.CHROME


def test_browser_diagnostics_are_plain_text():
    registry = BrowserRegistry((ChromeAdapter("/usr/bin/chrome"),))
    resolution = registry.resolve(
        BrowserChoice.CHROME,
        platform_info("Linux"),
        prefer_app_mode=True,
    )

    assert Diagnostics.browser_summary(resolution) == (
        "Browser: Chrome or Chromium (Selected Chrome or Chromium.)"
    )
    assert Diagnostics.browser_capabilities(resolution.fallback_chain) == (
        "Chrome or Chromium: available"
    )
