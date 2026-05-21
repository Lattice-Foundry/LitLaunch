"""Diagnostics report collection."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from litlaunch.browsers import BrowserCapability, BrowserResolution
from litlaunch.browsers.registry import BrowserRegistry, create_default_browser_registry
from litlaunch.config import (
    BrowserChoice,
    LauncherConfig,
    LaunchMode,
    StreamlitFlags,
    TrustMode,
)
from litlaunch.exposure import assess_runtime_exposure, classify_host_exposure
from litlaunch.inspect.models import (
    DiagnosticItem,
    DiagnosticSection,
    DiagnosticsReport,
    DiagnosticStatus,
)
from litlaunch.inspect.streamlit_check import (
    StreamlitAvailability,
    check_streamlit_availability,
)
from litlaunch.launcher import StreamlitLauncher
from litlaunch.platforms import PlatformDetector, PlatformInfo
from litlaunch.version import __version__
from litlaunch.windowing import WindowMonitorConfig


class DiagnosticCollector:
    """Collect local LitLaunch diagnostics without launching Streamlit."""

    def __init__(
        self,
        *,
        platform_detector: PlatformDetector | None = None,
        browser_registry: BrowserRegistry | None = None,
        streamlit_checker: Callable[[], StreamlitAvailability] | None = None,
        launcher_factory: type[StreamlitLauncher] = StreamlitLauncher,
    ) -> None:
        self.platform_detector = platform_detector or PlatformDetector()
        self.browser_registry = browser_registry or create_default_browser_registry()
        self.streamlit_checker = streamlit_checker or check_streamlit_availability
        self.launcher_factory = launcher_factory

    def collect(
        self,
        app_path: str | Path | None = None,
        *,
        mode: LaunchMode | str = LaunchMode.BROWSER,
        browser: BrowserChoice | str = BrowserChoice.AUTO,
        host: str = "127.0.0.1",
        port: int | None = None,
        auto_port: bool = True,
        allow_browser_fallback: bool = True,
        allow_network_exposure: bool = False,
        trust_mode: TrustMode | str = TrustMode.DEVELOPMENT,
        cwd: str | Path | None = None,
        extra_env: Mapping[str, str] | None = None,
        streamlit_flags: StreamlitFlags | None = None,
        streamlit_args: Sequence[str] = (),
        app_args: Sequence[str] = (),
        profile_name: str | None = None,
        monitor_window: bool | None = None,
        graceful_timeout_seconds: float | None = None,
        window_monitor_config: WindowMonitorConfig | None = None,
    ) -> DiagnosticsReport:
        """Collect diagnostics for the current environment and optional app target."""

        platform_info = self.platform_detector.detect()
        streamlit = self.streamlit_checker()
        capabilities = self.browser_registry.detect_all(platform_info)
        resolution = self.browser_registry.resolve(
            _normalize_browser_choice(browser),
            platform_info,
            prefer_app_mode=_normalize_launch_mode(mode) == LaunchMode.WEBAPP,
            allow_fallback=allow_browser_fallback,
        )

        sections = [
            self._litlaunch_section(),
            self._platform_section(platform_info),
            self._streamlit_section(streamlit),
            self._browser_section(capabilities, resolution),
            self._runtime_exposure_section(
                host=host,
                trust_mode=trust_mode,
                allow_network_exposure=allow_network_exposure,
                extra_env=extra_env or {},
            ),
        ]
        if profile_name is not None:
            sections.append(
                self._profile_section(
                    profile_name,
                    monitor_window=monitor_window,
                    graceful_timeout_seconds=graceful_timeout_seconds,
                    window_monitor_config=window_monitor_config,
                )
            )
        if app_path is not None:
            sections.append(
                self._target_section(
                    app_path,
                    mode=mode,
                    browser=browser,
                    host=host,
                    port=port,
                    auto_port=auto_port,
                    allow_browser_fallback=allow_browser_fallback,
                    allow_network_exposure=allow_network_exposure,
                    trust_mode=trust_mode,
                    cwd=cwd,
                    extra_env=extra_env or {},
                    streamlit_flags=streamlit_flags or {},
                    streamlit_args=streamlit_args,
                    app_args=app_args,
                )
            )

        return DiagnosticsReport("LitLaunch Inspect", tuple(sections))

    def _litlaunch_section(self) -> DiagnosticSection:
        return DiagnosticSection(
            "LitLaunch",
            (
                DiagnosticItem(
                    "Version",
                    DiagnosticStatus.OK,
                    f"LitLaunch {__version__}",
                ),
            ),
        )

    def _platform_section(self, platform_info: PlatformInfo) -> DiagnosticSection:
        return DiagnosticSection(
            "Platform",
            (
                DiagnosticItem(
                    "Platform",
                    DiagnosticStatus.OK,
                    platform_info.summary(),
                ),
                DiagnosticItem(
                    "Python executable",
                    DiagnosticStatus.INFO,
                    platform_info.python_executable,
                ),
                DiagnosticItem(
                    "Chromium app mode",
                    _capability_status(platform_info.supports_chromium_app_mode),
                    _supported_message(platform_info.supports_chromium_app_mode),
                ),
                DiagnosticItem(
                    "Default browser open",
                    _capability_status(platform_info.supports_default_browser_open),
                    _supported_message(platform_info.supports_default_browser_open),
                ),
                DiagnosticItem(
                    "Window monitoring",
                    _capability_status(platform_info.supports_window_monitoring),
                    _supported_message(platform_info.supports_window_monitoring),
                ),
            ),
        )

    def _streamlit_section(
        self,
        streamlit: StreamlitAvailability,
    ) -> DiagnosticSection:
        status = DiagnosticStatus.OK if streamlit.available else DiagnosticStatus.ERROR
        return DiagnosticSection(
            "Streamlit",
            (
                DiagnosticItem(
                    "Availability",
                    status,
                    streamlit.message,
                ),
            ),
        )

    def _browser_section(
        self,
        capabilities: tuple[BrowserCapability, ...],
        resolution: BrowserResolution,
    ) -> DiagnosticSection:
        items: list[DiagnosticItem] = []
        for capability in capabilities:
            status = (
                DiagnosticStatus.OK
                if capability.available
                else DiagnosticStatus.WARNING
            )
            support = []
            if capability.supports_app_mode:
                support.append("app-mode")
            if capability.supports_full_browser:
                support.append("full-browser")
            support_text = ", ".join(support) if support else "no launch modes"
            availability = "available" if capability.available else "unavailable"
            detail = "; ".join(capability.notes) if capability.notes else None
            items.append(
                DiagnosticItem(
                    capability.name,
                    status,
                    f"{availability}, {support_text}",
                    detail=detail,
                )
            )

        resolution_status = (
            DiagnosticStatus.OK
            if resolution.selected is not None
            else DiagnosticStatus.WARNING
        )
        items.append(
            DiagnosticItem(
                "Browser resolution",
                resolution_status,
                resolution.message,
            )
        )
        return DiagnosticSection("Browsers", tuple(items))

    def _profile_section(
        self,
        profile_name: str,
        *,
        monitor_window: bool | None,
        graceful_timeout_seconds: float | None,
        window_monitor_config: WindowMonitorConfig | None,
    ) -> DiagnosticSection:
        items = [
            DiagnosticItem(
                "Profile",
                DiagnosticStatus.INFO,
                profile_name,
            ),
        ]
        if monitor_window is not None:
            items.append(
                DiagnosticItem(
                    "Window monitoring",
                    DiagnosticStatus.INFO,
                    "enabled" if monitor_window else "disabled",
                )
            )
        if graceful_timeout_seconds is not None:
            items.append(
                DiagnosticItem(
                    "Graceful timeout",
                    DiagnosticStatus.INFO,
                    f"{float(graceful_timeout_seconds):g} seconds",
                )
            )
        if window_monitor_config is not None:
            items.extend(
                (
                    DiagnosticItem(
                        "Monitor appear timeout",
                        DiagnosticStatus.INFO,
                        f"{window_monitor_config.appear_timeout_seconds:g} seconds",
                    ),
                    DiagnosticItem(
                        "Monitor poll interval",
                        DiagnosticStatus.INFO,
                        f"{window_monitor_config.poll_interval_seconds:g} seconds",
                    ),
                    DiagnosticItem(
                        "Monitor stable polls",
                        DiagnosticStatus.INFO,
                        str(window_monitor_config.stable_poll_count),
                    ),
                )
            )
        return DiagnosticSection("Profile", tuple(items))

    def _runtime_exposure_section(
        self,
        *,
        host: str,
        trust_mode: TrustMode | str,
        allow_network_exposure: bool,
        extra_env: Mapping[str, str],
    ) -> DiagnosticSection:
        assessment = assess_runtime_exposure(
            host=host,
            trust_mode=trust_mode,
            allow_network_exposure=allow_network_exposure,
        )
        status = _posture_status(assessment.severity)
        items = [
            DiagnosticItem("Configured host", status, assessment.host),
            DiagnosticItem(
                "Exposure scope",
                status,
                assessment.scope.value,
                detail=assessment.summary,
            ),
            DiagnosticItem(
                "Trust mode",
                DiagnosticStatus.INFO,
                assessment.trust_mode.value,
                detail=_trust_mode_message(assessment.trust_mode),
            ),
            DiagnosticItem(
                "Network exposure acknowledgement",
                (
                    DiagnosticStatus.OK
                    if assessment.acknowledged or not assessment.exposed
                    else DiagnosticStatus.ERROR
                ),
                "acknowledged" if assessment.acknowledged else "not acknowledged",
                detail=assessment.recommendation,
            ),
            DiagnosticItem(
                "Exposure policy",
                DiagnosticStatus.OK if assessment.allowed else DiagnosticStatus.ERROR,
                "allowed by current trust mode"
                if assessment.allowed
                else "blocked by current trust mode",
                detail=assessment.detail,
            ),
            DiagnosticItem(
                "Shutdown endpoint scope",
                DiagnosticStatus.OK,
                "loopback-only",
                detail=(
                    "LitLaunch graceful shutdown hooks use a tokened loopback "
                    "endpoint for owned app cleanup."
                ),
            ),
            DiagnosticItem(
                "Browser ownership boundary",
                DiagnosticStatus.INFO,
                "browser processes are not owned by LitLaunch",
                detail=(
                    "LitLaunch launches browser windows but does not kill or "
                    "control browser processes."
                ),
            ),
            DiagnosticItem(
                "Diagnostics privacy",
                DiagnosticStatus.WARNING,
                "review diagnostics before sharing",
                detail=(
                    "Sanitization is pattern-based and may not catch encoded, "
                    "URL-wrapped, reformatted, or app-specific secrets."
                ),
            ),
        ]
        if extra_env:
            items.append(
                DiagnosticItem(
                    "Profile environment values",
                    DiagnosticStatus.WARNING,
                    "extra_env values are stored as plaintext profile TOML",
                    detail=(
                        "Avoid storing secrets directly in profile extra_env "
                        "unless the profile file is protected appropriately."
                    ),
                )
            )
        return DiagnosticSection("Runtime Exposure", tuple(items))

    def _target_section(
        self,
        app_path: str | Path,
        *,
        mode: LaunchMode | str,
        browser: BrowserChoice | str,
        host: str,
        port: int | None,
        auto_port: bool,
        allow_browser_fallback: bool,
        allow_network_exposure: bool,
        trust_mode: TrustMode | str,
        cwd: str | Path | None,
        extra_env: Mapping[str, str],
        streamlit_flags: StreamlitFlags,
        streamlit_args: Sequence[str],
        app_args: Sequence[str],
    ) -> DiagnosticSection:
        path = Path(app_path)
        resolved_path = path.resolve()
        items: list[DiagnosticItem] = []

        exists = path.exists()
        is_file = path.is_file()
        items.append(
            DiagnosticItem(
                "App path exists",
                DiagnosticStatus.OK if exists else DiagnosticStatus.ERROR,
                f"{path} exists" if exists else f"{path} does not exist",
            )
        )
        items.append(
            DiagnosticItem(
                "App path is file",
                DiagnosticStatus.OK if is_file else DiagnosticStatus.ERROR,
                f"{path} is a file" if is_file else f"{path} is not a file",
            )
        )
        items.append(
            DiagnosticItem(
                "Resolved app path",
                DiagnosticStatus.INFO,
                str(resolved_path),
            )
        )

        if not exists or not is_file:
            return DiagnosticSection("Target", tuple(items))

        try:
            config = LauncherConfig(
                app_path=path,
                mode=mode,
                browser=browser,
                host=host,
                port=port,
                auto_port=auto_port,
                allow_browser_fallback=allow_browser_fallback,
                allow_network_exposure=allow_network_exposure,
                trust_mode=trust_mode,
                cwd=cwd,
                extra_env=extra_env,
                streamlit_flags=streamlit_flags,
                streamlit_args=streamlit_args,
                app_args=app_args,
            )
            launcher = self.launcher_factory(config)
            plan = launcher.build_launch_plan()
        except Exception as exc:
            items.append(
                DiagnosticItem(
                    "Launch preview",
                    DiagnosticStatus.ERROR,
                    str(exc),
                )
            )
            return DiagnosticSection("Target", tuple(items))

        items.extend(
            (
                _host_binding_item(plan.host, config.allow_network_exposure),
                DiagnosticItem(
                    "Trust mode",
                    DiagnosticStatus.INFO,
                    config.trust_mode.value,
                ),
                DiagnosticItem(
                    "Command preview",
                    DiagnosticStatus.OK,
                    "Streamlit command can be built.",
                    detail=plan.command_display,
                ),
                DiagnosticItem(
                    "App URL preview",
                    DiagnosticStatus.INFO,
                    plan.app_url,
                ),
                DiagnosticItem(
                    "Health URL preview",
                    DiagnosticStatus.INFO,
                    plan.health_url,
                ),
                DiagnosticItem(
                    "Working directory",
                    DiagnosticStatus.INFO,
                    str(plan.cwd) if plan.cwd is not None else "not set",
                ),
                DiagnosticItem(
                    "Environment overrides",
                    DiagnosticStatus.INFO,
                    plan.extra_env_preview,
                ),
                DiagnosticItem(
                    "Browser resolution",
                    (
                        DiagnosticStatus.OK
                        if plan.browser_resolution is not None
                        and plan.browser_resolution.selected is not None
                        else DiagnosticStatus.WARNING
                    ),
                    (
                        plan.browser_resolution.message
                        if plan.browser_resolution is not None
                        else "Browser resolution skipped."
                    ),
                ),
            )
        )
        return DiagnosticSection("Target", tuple(items))


def _capability_status(supported: bool) -> DiagnosticStatus:
    return DiagnosticStatus.OK if supported else DiagnosticStatus.WARNING


def _supported_message(supported: bool) -> str:
    return "supported" if supported else "not supported"


def _posture_status(severity: str) -> DiagnosticStatus:
    if severity == "error":
        return DiagnosticStatus.ERROR
    if severity == "warning":
        return DiagnosticStatus.WARNING
    return DiagnosticStatus.OK


def _trust_mode_message(trust_mode: TrustMode) -> str:
    if trust_mode == TrustMode.STRICT_LOCAL:
        return "strict_local enforces loopback-only runtime binding."
    if trust_mode == TrustMode.INTERNAL_NETWORK:
        return "internal_network is for intentional internal/LAN exposure."
    return "development is the permissive local developer posture."


def _host_binding_item(host: str, allow_network_exposure: bool) -> DiagnosticItem:
    exposure = classify_host_exposure(host)
    if exposure.is_loopback:
        return DiagnosticItem(
            "Host binding",
            DiagnosticStatus.OK,
            f"{host} (loopback-only)",
        )
    detail = (
        "Explicitly acknowledged for this profile or command."
        if allow_network_exposure
        else "Launch requires --allow-network-exposure or profile acknowledgement."
    )
    return DiagnosticItem(
        "Host binding",
        DiagnosticStatus.WARNING,
        (
            f"{host} may be reachable beyond this machine. "
            "LitLaunch does not secure Streamlit."
        ),
        detail=(
            "LitLaunch does not secure Streamlit applications. "
            f"{exposure.warning} {detail}"
        ),
    )


def _normalize_launch_mode(value: LaunchMode | str) -> LaunchMode:
    return value if isinstance(value, LaunchMode) else LaunchMode(str(value))


def _normalize_browser_choice(value: BrowserChoice | str) -> BrowserChoice:
    return value if isinstance(value, BrowserChoice) else BrowserChoice(str(value))
