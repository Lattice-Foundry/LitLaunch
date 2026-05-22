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
        allow_fallback: bool = True,
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

        attempted: list[BrowserLaunchResult] = []
        for candidate in _launch_candidates(
            resolution,
            mode=mode,
            allow_fallback=allow_fallback,
        ):
            result = self._launch_capability(
                candidate,
                url=url,
                mode=mode,
                title=title,
                extra_args=extra_args,
            )
            if result.ok:
                return _with_fallback_success_message(result, attempted)
            attempted.append(result)

        if attempted:
            return _with_failure_summary(attempted, allow_fallback=allow_fallback)

        return BrowserLaunchResult(
            ok=False,
            command=None,
            browser=capability,
            mode=mode,
            message=f"No compatible launch candidate was available for {mode.value}.",
        )

    def _launch_capability(
        self,
        capability: BrowserCapability,
        *,
        url: str,
        mode: LaunchMode,
        title: str,
        extra_args: Sequence[str],
    ) -> BrowserLaunchResult:
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
            *tuple(str(arg) for arg in extra_args),
            url,
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


def _launch_candidates(
    resolution: BrowserResolution,
    *,
    mode: LaunchMode,
    allow_fallback: bool,
) -> tuple[BrowserCapability, ...]:
    selected = resolution.selected
    if selected is None:
        return ()

    candidates: list[BrowserCapability] = [selected]
    if allow_fallback:
        candidates.extend(resolution.fallback_chain)

    seen: set[BrowserKind] = set()
    launchable: list[BrowserCapability] = []
    for capability in candidates:
        if capability.kind in seen:
            continue
        seen.add(capability.kind)
        if _supports_launch_mode(capability, mode):
            launchable.append(capability)
    return tuple(launchable)


def _supports_launch_mode(capability: BrowserCapability, mode: LaunchMode) -> bool:
    if not capability.available:
        return False
    if mode == LaunchMode.WEBAPP:
        return capability.supports_app_mode
    return capability.supports_full_browser


def _with_fallback_success_message(
    result: BrowserLaunchResult,
    attempted: Sequence[BrowserLaunchResult],
) -> BrowserLaunchResult:
    if not attempted:
        return result
    failed_names = ", ".join(
        attempt.browser.name for attempt in attempted if attempt.browser is not None
    )
    message = (
        f"{failed_names} launch failed; fell back to {result.browser.name}. "
        f"{result.message}"
    )
    return BrowserLaunchResult(
        ok=True,
        command=result.command,
        browser=result.browser,
        mode=result.mode,
        message=message,
    )


def _with_failure_summary(
    attempted: Sequence[BrowserLaunchResult],
    *,
    allow_fallback: bool,
) -> BrowserLaunchResult:
    last = attempted[-1]
    attempts = "; ".join(
        f"{attempt.browser.name if attempt.browser is not None else 'browser'}: "
        f"{attempt.message}"
        for attempt in attempted
    )
    fallback_note = (
        "Fallback was disabled."
        if not allow_fallback
        else "No fallback browser launch succeeded."
    )
    return BrowserLaunchResult(
        ok=False,
        command=last.command,
        browser=last.browser,
        mode=last.mode,
        message=f"{fallback_note} Attempts: {attempts}",
    )
