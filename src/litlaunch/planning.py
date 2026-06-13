"""Launch planning helpers for LitLaunch."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from litlaunch.artifacts import browser_profiles_dir, runtime_state_root_for_config
from litlaunch.backend import (
    BackendCommand,
    BackendCommandContext,
    BackendCommandProvider,
)
from litlaunch.browser_profiles import has_browser_switch
from litlaunch.browsers import BrowserResolution
from litlaunch.config import (
    FlagValue,
    LauncherConfig,
    LaunchMode,
    NormalizedStreamlitFlags,
)
from litlaunch.exceptions import CommandBuildError
from litlaunch.health import build_streamlit_app_url, build_streamlit_health_url
from litlaunch.lifecycle import LaunchPlan
from litlaunch.ports import PortManager
from litlaunch.redaction import format_command_preview, format_env_preview
from litlaunch.streamlit import StreamlitCommandBuilder


def build_launch_plan(
    *,
    config: LauncherConfig,
    port_manager: PortManager,
    command_builder: StreamlitCommandBuilder,
    backend_command_provider: BackendCommandProvider,
    browser_resolver: Callable[[], BrowserResolution],
    include_browser_resolution: bool,
) -> LaunchPlan:
    """Build a resolved launch plan without starting backend or browser."""

    resolved_port = port_manager.resolve_port(config)
    context = build_backend_command_context(
        config=config,
        command_builder=command_builder,
        port=resolved_port,
    )
    backend_command = build_backend_command(backend_command_provider, context)
    runtime_state_root = runtime_state_root_for_config(config)
    return LaunchPlan(
        command=backend_command.command,
        command_display=format_command_preview(backend_command.command),
        backend_description=backend_command.description,
        backend_kind=backend_command.backend_kind,
        cwd=config.cwd,
        app_url=context.app_url,
        health_url=context.health_url,
        host=config.host,
        port=config.port,
        resolved_port=resolved_port,
        auto_port=config.auto_port,
        mode=config.mode,
        headless=context.headless,
        browser_requested=config.browser,
        browser_resolution=(browser_resolver() if include_browser_resolution else None),
        allow_browser_fallback=config.allow_browser_fallback,
        app_args=config.app_args,
        streamlit_flags=copy_streamlit_flags(config.streamlit_flags),
        streamlit_args=config.streamlit_args,
        extra_env_preview=(
            format_env_preview(config.extra_env) if config.extra_env else "none"
        ),
        streamlit_chrome_policy=streamlit_chrome_policy(config),
        app_icon=config.app_icon,
        app_icon_support=app_icon_support(config),
        runtime_state_root=runtime_state_root,
        browser_profile_root=browser_profiles_dir(runtime_state_root),
        browser_profile_policy=browser_profile_policy(config),
        browser_profile_cleanup=browser_profile_cleanup(config),
    )


def build_backend_command_context(
    *,
    config: LauncherConfig,
    command_builder: StreamlitCommandBuilder,
    port: int,
) -> BackendCommandContext:
    """Build the context passed to backend command providers."""

    return BackendCommandContext(
        config=config,
        host=config.host,
        port=port,
        app_url=build_streamlit_app_url(config.host, port),
        health_url=build_streamlit_health_url(config.host, port),
        headless=command_builder.resolve_headless(),
    )


def build_backend_command(
    provider: BackendCommandProvider,
    context: BackendCommandContext,
) -> BackendCommand:
    """Invoke and validate a backend command provider."""

    try:
        backend_command = provider.build_backend_command(context)
    except CommandBuildError:
        raise
    except Exception as exc:
        raise CommandBuildError(f"Backend command provider failed: {exc}") from exc

    if not isinstance(backend_command, BackendCommand):
        raise CommandBuildError(
            "Backend command provider must return a BackendCommand."
        )
    return backend_command


def copy_streamlit_flags(
    flags: NormalizedStreamlitFlags,
) -> Mapping[str, FlagValue] | tuple[str, ...]:
    """Return a LaunchPlan-safe copy of Streamlit flags."""

    if hasattr(flags, "items"):
        return dict(flags.items())
    return tuple(flags)


def streamlit_chrome_policy(config: LauncherConfig) -> str:
    """Return the user-facing Streamlit app chrome policy name."""

    return "visible" if config.show_streamlit_chrome else "hidden"


def app_icon_support(config: LauncherConfig) -> str:
    """Return the honest launch-surface support summary for an app icon."""

    if config.app_icon is None:
        return "not configured"
    if config.mode == LaunchMode.WEBAPP:
        return (
            "native shortcuts can use this icon; Windows .ico webapp launches "
            "try shortcut icon metadata and live window-icon overrides where "
            "supported"
        )
    return "native shortcuts can use this icon; browser-tab launches ignore it"


def browser_profile_policy(config: LauncherConfig) -> str:
    """Return the browser profile ownership policy for this launch plan."""

    if has_browser_switch(config.extra_browser_args, "--user-data-dir"):
        return "external/caller-provided browser profile"
    if config.mode == LaunchMode.WEBAPP:
        return "ephemeral isolated browser profile"
    return "external/default browser profile"


def browser_profile_cleanup(config: LauncherConfig) -> str:
    """Return the browser profile cleanup policy for this launch plan."""

    if has_browser_switch(config.extra_browser_args, "--user-data-dir"):
        return "not owned by LitLaunch"
    if config.mode == LaunchMode.WEBAPP:
        return "best-effort cleanup after runtime stops"
    return "not owned by LitLaunch"
