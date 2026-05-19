"""Browser launch orchestration."""

from __future__ import annotations

import subprocess
import webbrowser
from collections.abc import Callable, Sequence

from litlaunch.browsers.base import (
    BrowserCapability,
    BrowserKind,
    BrowserLaunchResult,
    BrowserResolution,
)
from litlaunch.browsers.registry import BrowserRegistry, create_default_browser_registry
from litlaunch.config import LaunchMode


class BrowserLauncher:
    """Launch resolved browser capabilities without owning browser processes."""

    def __init__(
        self,
        *,
        registry: BrowserRegistry | None = None,
        popen_factory: Callable[..., object] = subprocess.Popen,
        browser_open: Callable[[str], bool] = webbrowser.open,
    ) -> None:
        self.registry = registry or create_default_browser_registry()
        self.popen_factory = popen_factory
        self.browser_open = browser_open

    def launch(
        self,
        resolution: BrowserResolution,
        *,
        url: str,
        mode: LaunchMode,
        title: str = "",
        extra_args: Sequence[str] = (),
    ) -> BrowserLaunchResult:
        """Launch the selected browser capability."""

        capability = resolution.selected
        if capability is None:
            return BrowserLaunchResult(
                ok=False,
                command=None,
                browser=None,
                mode=mode,
                message=resolution.message,
            )

        if mode == LaunchMode.WEBAPP:
            return self._launch_app_mode(
                capability,
                url=url,
                mode=mode,
                title=title,
                extra_args=extra_args,
            )

        return self._launch_full_browser(
            capability,
            url=url,
            mode=mode,
            extra_args=extra_args,
        )

    def _launch_app_mode(
        self,
        capability: BrowserCapability,
        *,
        url: str,
        mode: LaunchMode,
        title: str,
        extra_args: Sequence[str],
    ) -> BrowserLaunchResult:
        if not capability.supports_app_mode:
            return BrowserLaunchResult(
                ok=False,
                command=None,
                browser=capability,
                mode=mode,
                message=f"{capability.name} does not support app-mode launches.",
            )
        if capability.executable_path is None:
            return BrowserLaunchResult(
                ok=False,
                command=None,
                browser=capability,
                mode=mode,
                message=f"{capability.name} has no executable path.",
            )

        adapter = self.registry.get(capability.kind.value).with_executable_path(
            capability.executable_path
        )
        command = adapter.build_launch_command(
            url,
            title=title,
            extra_args=extra_args,
        )
        try:
            self.popen_factory(command, shell=False)
        except Exception as exc:
            return BrowserLaunchResult(
                ok=False,
                command=command,
                browser=capability,
                mode=mode,
                message=f"Browser launch failed: {exc}",
            )
        return BrowserLaunchResult(
            ok=True,
            command=command,
            browser=capability,
            mode=mode,
            message=f"Launched {capability.name} in app mode.",
        )

    def _launch_full_browser(
        self,
        capability: BrowserCapability,
        *,
        url: str,
        mode: LaunchMode,
        extra_args: Sequence[str],
    ) -> BrowserLaunchResult:
        if capability.kind == BrowserKind.DEFAULT:
            opened = bool(self.browser_open(url))
            return BrowserLaunchResult(
                ok=opened,
                command=None,
                browser=capability,
                mode=mode,
                message=(
                    "Opened URL in default browser."
                    if opened
                    else "Default browser open returned false."
                ),
            )

        if capability.executable_path is None:
            return BrowserLaunchResult(
                ok=False,
                command=None,
                browser=capability,
                mode=mode,
                message=f"{capability.name} has no executable path.",
            )

        command = (
            capability.executable_path,
            url,
            *tuple(str(arg) for arg in extra_args),
        )
        try:
            self.popen_factory(command, shell=False)
        except Exception as exc:
            return BrowserLaunchResult(
                ok=False,
                command=command,
                browser=capability,
                mode=mode,
                message=f"Browser launch failed: {exc}",
            )
        return BrowserLaunchResult(
            ok=True,
            command=command,
            browser=capability,
            mode=mode,
            message=f"Launched {capability.name}.",
        )
