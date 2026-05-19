"""Google Chrome browser adapter."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from litlaunch.browsers.base import BrowserAdapter, BrowserCapability, BrowserKind
from litlaunch.platforms import OperatingSystem, PlatformInfo


class ChromeAdapter(BrowserAdapter):
    """Detect and build Chrome/Chromium app-mode commands."""

    kind = BrowserKind.CHROME
    name = "chrome"
    supports_app_mode = True
    supports_full_browser = True

    def detect(self, platform_info: PlatformInfo | None = None) -> BrowserCapability:
        info = self._platform_info(platform_info)
        executable = self.executable_path or self._detect_executable(info)
        if executable:
            return BrowserCapability(
                kind=self.kind,
                name="Chrome or Chromium",
                executable_path=executable,
                available=True,
                supports_app_mode=self.supports_app_mode,
                supports_full_browser=self.supports_full_browser,
                notes=(),
            )
        return BrowserCapability(
            kind=self.kind,
            name="Chrome or Chromium",
            executable_path=None,
            available=False,
            supports_app_mode=self.supports_app_mode,
            supports_full_browser=self.supports_full_browser,
            notes=("Chrome or Chromium executable was not detected.",),
        )

    def build_launch_command(
        self,
        url: str,
        *,
        title: str = "",
        extra_args: Sequence[str] = (),
    ) -> tuple[str, ...]:
        executable_path = self.require_executable_path()
        return (
            executable_path,
            f"--app={url}",
            *tuple(str(arg) for arg in extra_args),
        )

    def _detect_executable(self, platform_info: PlatformInfo) -> str | None:
        path_match = self._find_by_names(
            (
                "chrome",
                "google-chrome",
                "google-chrome-stable",
                "chromium",
                "chromium-browser",
            )
        )
        if path_match:
            return path_match

        if platform_info.os == OperatingSystem.WINDOWS:
            return self._find_by_paths(_windows_chrome_paths(self.env))
        if platform_info.os == OperatingSystem.MACOS:
            return self._find_by_paths(
                (
                    Path(
                        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                    ),
                    Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
                )
            )
        return None


def _windows_chrome_paths(env: dict[str, str]) -> tuple[Path, ...]:
    roots = (
        env.get("PROGRAMFILES"),
        env.get("PROGRAMFILES(X86)"),
        env.get("LOCALAPPDATA"),
    )
    paths: list[Path] = []
    for root in roots:
        if root:
            paths.append(
                Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe"
            )
            paths.append(Path(root) / "Chromium" / "Application" / "chrome.exe")
    return tuple(dict.fromkeys(paths))
