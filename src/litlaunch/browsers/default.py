"""Default browser adapter capability."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from litlaunch.browsers.base import BrowserAdapter, BrowserCapability, BrowserKind
from litlaunch.exceptions import BrowserError
from litlaunch.platforms import OperatingSystem, PlatformDetector, PlatformInfo

WINDOWS_URL_ASSOCIATION_KEYS = (
    r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice",
    r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice",
)


class DefaultBrowserAdapter(BrowserAdapter):
    """Represent Python/default-browser full-browser capability."""

    kind = BrowserKind.DEFAULT
    name = "default"
    supports_app_mode = False
    supports_full_browser = True

    def detect(self, platform_info: PlatformInfo | None = None) -> BrowserCapability:
        info = self._platform_info(platform_info)
        available = info.supports_default_browser_open
        notes = () if available else ("Default browser opening is not supported.",)
        return BrowserCapability(
            kind=self.kind,
            name="Default browser",
            executable_path=None,
            available=available,
            supports_app_mode=self.supports_app_mode,
            supports_full_browser=self.supports_full_browser,
            notes=notes,
        )

    def build_launch_command(
        self,
        url: str,
        *,
        title: str = "",
        extra_args: Sequence[str] = (),
    ) -> tuple[str, ...]:
        raise BrowserError(
            "Default browser launches are commandless and will use webbrowser later."
        )


def detect_default_chromium_browser(
    platform_info: PlatformInfo | None = None,
    *,
    registry_value_reader: Callable[[str, str], str | None] | None = None,
) -> BrowserKind | None:
    """Return the Chromium browser kind for the Windows default browser if known."""

    info = platform_info or PlatformDetector().detect()
    if info.os != OperatingSystem.WINDOWS:
        return None

    reader = registry_value_reader or _read_windows_registry_value
    for key_path in WINDOWS_URL_ASSOCIATION_KEYS:
        prog_id = reader(key_path, "ProgId")
        browser_kind = _browser_kind_from_windows_prog_id(prog_id)
        if browser_kind is not None:
            return browser_kind
    return None


def _browser_kind_from_windows_prog_id(prog_id: str | None) -> BrowserKind | None:
    if not prog_id:
        return None
    normalized = str(prog_id).strip().lower()
    if "msedge" in normalized or "microsoftedge" in normalized:
        return BrowserKind.EDGE
    if "chrome" in normalized or "chromium" in normalized:
        return BrowserKind.CHROME
    return None


def _read_windows_registry_value(key_path: str, value_name: str) -> str | None:
    try:
        import winreg
    except ImportError:  # pragma: no cover - non-Windows Python builds.
        return None

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
    except OSError:
        return None
    return str(value)
