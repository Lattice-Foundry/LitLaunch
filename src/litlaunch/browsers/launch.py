"""Browser launch orchestration."""

from __future__ import annotations

import os
import subprocess
import time
import uuid
import webbrowser
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast

from litlaunch._browser_authority import (
    BrowserLaunchAuthority,
    BrowserLaunchStrategy,
    create_browser_launch_authority,
)
from litlaunch._protocols import ClockProvider
from litlaunch._windows_shell import (
    WindowsShellProcess,
    open_windows_shortcut_with_process,
)
from litlaunch.artifacts import browser_shortcuts_dir
from litlaunch.browsers.base import (
    BrowserCapability,
    BrowserKind,
    BrowserLaunchResult,
    BrowserResolution,
)
from litlaunch.browsers.registry import BrowserRegistry, create_default_browser_registry
from litlaunch.config import LaunchMode
from litlaunch.windows_shortcut import (
    join_windows_arguments,
    windows_app_user_model_id,
    write_windows_shortcut,
)


class BrowserLauncher:
    """Launch resolved browser capabilities without owning browser processes."""

    def __init__(
        self,
        *,
        registry: BrowserRegistry | None = None,
        popen_factory: Callable[..., object] = subprocess.Popen,
        browser_open: Callable[[str], bool] = webbrowser.open,
        shortcut_writer: Callable[..., object] = write_windows_shortcut,
        shortcut_opener: Callable[[Path], object] | None = None,
        process_authority_factory: Callable[
            ..., BrowserLaunchAuthority | None
        ] = create_browser_launch_authority,
        clock: ClockProvider = time,
        is_windows: bool | None = None,
    ) -> None:
        self.registry = registry or create_default_browser_registry()
        self.popen_factory = popen_factory
        self.browser_open = browser_open
        self.shortcut_writer = shortcut_writer
        self.shortcut_opener = shortcut_opener or open_windows_shortcut
        self.process_authority_factory = process_authority_factory
        self.clock = clock
        self.is_windows = os.name == "nt" if is_windows is None else is_windows
        self._process_authority: BrowserLaunchAuthority | None = None
        self._pending_authority_launch_id: str | None = None
        self._active_authority_launch_id: str | None = None

    def launch(
        self,
        resolution: BrowserResolution,
        *,
        url: str,
        mode: LaunchMode,
        title: str = "",
        extra_args: Sequence[str] = (),
        allow_fallback: bool = True,
        app_icon: Path | None = None,
        artifact_root: Path | None = None,
    ) -> BrowserLaunchResult:
        """Launch the selected browser capability."""

        self._process_authority = None
        self._active_authority_launch_id = self._pending_authority_launch_id
        self._pending_authority_launch_id = None
        try:
            return self._launch_selected(
                resolution,
                url=url,
                mode=mode,
                title=title,
                extra_args=extra_args,
                allow_fallback=allow_fallback,
                app_icon=app_icon,
                artifact_root=artifact_root,
            )
        finally:
            self._active_authority_launch_id = None

    def _launch_selected(
        self,
        resolution: BrowserResolution,
        *,
        url: str,
        mode: LaunchMode,
        title: str,
        extra_args: Sequence[str],
        allow_fallback: bool,
        app_icon: Path | None,
        artifact_root: Path | None,
    ) -> BrowserLaunchResult:
        """Launch one resolution while a private authority binding is active."""

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
                app_icon=app_icon,
                artifact_root=artifact_root,
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
        app_icon: Path | None,
        artifact_root: Path | None,
    ) -> BrowserLaunchResult:
        if mode == LaunchMode.WEBAPP:
            return self._launch_app_mode(
                capability,
                url=url,
                mode=mode,
                title=title,
                extra_args=extra_args,
                app_icon=app_icon,
                artifact_root=artifact_root,
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
        app_icon: Path | None,
        artifact_root: Path | None,
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
        if _should_launch_with_icon_shortcut(
            command=command,
            app_icon=app_icon,
            is_windows=self.is_windows,
        ):
            shortcut_result = self._launch_app_mode_with_windows_icon_shortcut(
                capability,
                command=command,
                mode=mode,
                title=title,
                app_icon=cast(Path, app_icon),
                artifact_root=artifact_root,
            )
            if shortcut_result.ok:
                return shortcut_result

        launched_at = self.clock.monotonic()
        try:
            process = self.popen_factory(command, shell=False)
        except Exception as exc:
            return BrowserLaunchResult(
                ok=False,
                command=command,
                browser=capability,
                mode=mode,
                message=f"Browser launch failed: {exc}",
            )
        self._retain_process_authority(
            process_id=getattr(process, "pid", None),
            capability=capability,
            command=command,
            launch_strategy=BrowserLaunchStrategy.DIRECT,
            launched_at_monotonic=launched_at,
        )
        return BrowserLaunchResult(
            ok=True,
            command=command,
            browser=capability,
            mode=mode,
            message=f"Launched {capability.name} in app mode.",
        )

    def _launch_app_mode_with_windows_icon_shortcut(
        self,
        capability: BrowserCapability,
        *,
        command: tuple[str, ...],
        mode: LaunchMode,
        title: str,
        app_icon: Path,
        artifact_root: Path | None,
    ) -> BrowserLaunchResult:
        shortcut_path = _browser_icon_shortcut_path(
            artifact_root or Path.cwd(),
            title=title,
            browser_name=capability.name,
        )
        app_user_model_id = windows_app_user_model_id(
            artifact_root or Path.cwd(),
            title,
            app_icon,
        )
        target, *arguments = command
        try:
            self.shortcut_writer(
                shortcut_path=shortcut_path,
                target_path=target,
                arguments=join_windows_arguments(tuple(arguments)),
                working_directory=artifact_root or Path.cwd(),
                icon_path=app_icon,
                app_user_model_id=app_user_model_id,
            )
            launched_at = self.clock.monotonic()
            shell_process = self.shortcut_opener(shortcut_path)
        except Exception as exc:
            _remove_path_quietly(shortcut_path)
            return BrowserLaunchResult(
                ok=False,
                command=command,
                browser=capability,
                mode=mode,
                message=f"Windows icon shortcut launch failed: {exc}",
            )

        if isinstance(shell_process, WindowsShellProcess):
            self._retain_process_authority(
                process_id=shell_process.process_id,
                root_creation_time_100ns=shell_process.creation_time_100ns,
                capability=capability,
                command=command,
                launch_strategy=BrowserLaunchStrategy.WINDOWS_SHORTCUT,
                launched_at_monotonic=launched_at,
            )
        return BrowserLaunchResult(
            ok=True,
            command=command,
            browser=capability,
            mode=mode,
            message=f"Launched {capability.name} in app mode through Windows shortcut.",
            cleanup_callbacks=(_cleanup_shortcut_callback(shortcut_path),),
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
        launched_at = self.clock.monotonic()
        try:
            process = self.popen_factory(command, shell=False)
        except Exception as exc:
            return BrowserLaunchResult(
                ok=False,
                command=command,
                browser=capability,
                mode=mode,
                message=f"Browser launch failed: {exc}",
            )
        self._retain_process_authority(
            process_id=getattr(process, "pid", None),
            capability=capability,
            command=command,
            launch_strategy=BrowserLaunchStrategy.DIRECT,
            launched_at_monotonic=launched_at,
        )
        return BrowserLaunchResult(
            ok=True,
            command=command,
            browser=capability,
            mode=mode,
            message=f"Launched {capability.name}.",
        )

    def _process_authority_snapshot(self) -> BrowserLaunchAuthority | None:
        """Return direct-launch identity without claiming process ownership."""

        return self._process_authority

    def _set_process_authority_launch_id(self, launch_id: str) -> None:
        """Bind the next browser authority to one private transport launch ID."""

        normalized = str(launch_id).strip()
        if not normalized or len(normalized) > 256:
            raise ValueError("Browser authority launch ID is invalid.")
        self._pending_authority_launch_id = normalized

    def _retain_process_authority(
        self,
        *,
        process_id: object,
        capability: BrowserCapability,
        command: tuple[str, ...],
        launch_strategy: BrowserLaunchStrategy,
        launched_at_monotonic: float,
        root_creation_time_100ns: int | None = None,
    ) -> None:
        if (
            isinstance(process_id, bool)
            or not isinstance(process_id, int)
            or process_id <= 0
        ):
            return
        executable_path = capability.executable_path
        if executable_path is None:
            return
        try:
            self._process_authority = self.process_authority_factory(
                root_process_id=process_id,
                root_creation_time_100ns=root_creation_time_100ns,
                browser_kind=capability.kind,
                executable_path=executable_path,
                command=command,
                launch_strategy=launch_strategy,
                launched_at_monotonic=launched_at_monotonic,
                launch_id=self._active_authority_launch_id,
            )
        except Exception:
            self._process_authority = None


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
    if not attempted or result.browser is None:
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
        cleanup_callbacks=result.cleanup_callbacks,
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
        cleanup_callbacks=last.cleanup_callbacks,
    )


def _should_launch_with_icon_shortcut(
    *,
    command: tuple[str, ...],
    app_icon: Path | None,
    is_windows: bool,
) -> bool:
    return (
        is_windows
        and app_icon is not None
        and app_icon.suffix.casefold() == ".ico"
        and bool(command)
    )


def _browser_icon_shortcut_path(
    root: Path,
    *,
    title: str,
    browser_name: str,
) -> Path:
    label = _safe_shortcut_label(title or browser_name or "litlaunch-app")
    return browser_shortcuts_dir(root, create=True) / f"{label}-{uuid.uuid4().hex}.lnk"


def _safe_shortcut_label(value: str) -> str:
    cleaned = "".join(
        char if char.isalnum() or char in ("-", "_") else "-" for char in value.strip()
    ).strip("-_")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned[:48] or "litlaunch-app"


def _cleanup_shortcut_callback(path: Path) -> Callable[[], object]:
    def cleanup_shortcut() -> None:
        _remove_path_quietly(path)

    return cleanup_shortcut


def _remove_path_quietly(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return


def open_windows_shortcut(path: Path) -> WindowsShellProcess | None:
    """Open a Windows shortcut and retain process identity when available."""

    return open_windows_shortcut_with_process(path)
