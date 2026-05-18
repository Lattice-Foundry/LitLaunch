"""Google Chrome browser adapter."""

from __future__ import annotations

from collections.abc import Sequence

from litlaunch.browsers.base import BrowserAdapter


class ChromeAdapter(BrowserAdapter):
    """Build Google Chrome Chromium app-mode commands."""

    name = "chrome"
    supports_app_mode = True

    def build_launch_command(
        self,
        url: str,
        *,
        title: str,
        extra_args: Sequence[str] = (),
    ) -> tuple[str, ...]:
        executable_path = self.require_executable_path()
        return (
            str(executable_path),
            f"--app={url}",
            *tuple(str(arg) for arg in extra_args),
        )
