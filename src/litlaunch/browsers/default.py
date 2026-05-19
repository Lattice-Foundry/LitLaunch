"""Default browser adapter capability."""

from __future__ import annotations

from collections.abc import Sequence

from litlaunch.browsers.base import BrowserAdapter, BrowserCapability, BrowserKind
from litlaunch.exceptions import BrowserError
from litlaunch.platforms import PlatformInfo


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
