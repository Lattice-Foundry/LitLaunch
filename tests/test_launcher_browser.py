from litlaunch import BrowserChoice, LauncherConfig
from litlaunch.browsers import BrowserKind, BrowserRegistry, ChromeAdapter, EdgeAdapter
from litlaunch.launcher import StreamlitLauncher
from litlaunch.platforms import PlatformDetector


def test_streamlit_launcher_resolves_browser_from_config():
    platform_info = PlatformDetector(
        system_func=lambda: "Windows",
        machine_func=lambda: "AMD64",
        release_func=lambda: "test",
        python_version_func=lambda: "3.14.5",
        executable_provider=lambda: "python",
    ).detect()
    registry = BrowserRegistry(
        (
            EdgeAdapter("C:/Edge/msedge.exe"),
            ChromeAdapter("C:/Chrome/chrome.exe"),
        )
    )

    class PlatformRegistry(BrowserRegistry):
        def resolve(self, choice, platform_info_arg=None, **kwargs):
            return super().resolve(choice, platform_info, **kwargs)

    launcher = StreamlitLauncher(
        LauncherConfig(
            app_path="app.py",
            mode="webapp",
            browser=BrowserChoice.AUTO,
        ),
        browser_registry=PlatformRegistry(
            tuple(registry.get(name) for name in registry.names())
        ),
    )

    resolution = launcher.resolve_browser()

    assert resolution.selected is not None
    assert resolution.selected.kind == BrowserKind.EDGE
