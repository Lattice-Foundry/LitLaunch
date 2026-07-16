"""Credential-free public host-sizing eligibility assessment."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum

from litlaunch.browser_profiles import has_browser_switch
from litlaunch.config import (
    BrowserChoice,
    HostSizingPolicy,
    LauncherConfig,
    LaunchMode,
)
from litlaunch.exposure import is_loopback_host


class HostSizingEligibilityStatus(str, Enum):
    """Static host-sizing eligibility states safe for public diagnostics."""

    DISABLED = "disabled"
    ELIGIBLE = "eligible"
    UNSUPPORTED_PLATFORM = "unsupported_platform"
    UNSUPPORTED_MODE = "unsupported_mode"
    UNSUPPORTED_BROWSER = "unsupported_browser"
    REQUIRES_MANAGED_PROFILE = "requires_managed_profile"
    REQUIRES_LOOPBACK = "requires_loopback"


@dataclass(frozen=True)
class HostSizingEligibility:
    """Credential-free pre-launch assessment for an enabled sizing policy."""

    policy: HostSizingPolicy
    status: HostSizingEligibilityStatus
    reason: str
    experimental: bool = True

    @property
    def eligible(self) -> bool:
        """Return whether runtime authority collection may be attempted."""

        return self.status == HostSizingEligibilityStatus.ELIGIBLE


def evaluate_host_sizing_eligibility(
    config: LauncherConfig,
    *,
    is_windows: bool | None = None,
) -> HostSizingEligibility:
    """Evaluate only prerequisites known before backend or browser launch."""

    if config.host_sizing == HostSizingPolicy.OFF:
        return HostSizingEligibility(
            config.host_sizing,
            HostSizingEligibilityStatus.DISABLED,
            "Host sizing is off.",
        )
    windows = sys.platform == "win32" if is_windows is None else bool(is_windows)
    if not windows:
        return HostSizingEligibility(
            config.host_sizing,
            HostSizingEligibilityStatus.UNSUPPORTED_PLATFORM,
            "Experimental host sizing requires Windows.",
        )
    if config.mode != LaunchMode.WEBAPP:
        return HostSizingEligibility(
            config.host_sizing,
            HostSizingEligibilityStatus.UNSUPPORTED_MODE,
            "Experimental host sizing requires webapp mode.",
        )
    if config.browser not in {BrowserChoice.EDGE, BrowserChoice.CHROME}:
        return HostSizingEligibility(
            config.host_sizing,
            HostSizingEligibilityStatus.UNSUPPORTED_BROWSER,
            "Experimental host sizing requires explicit Edge or Chrome selection.",
        )
    if has_browser_switch(config.extra_browser_args, "--user-data-dir"):
        return HostSizingEligibility(
            config.host_sizing,
            HostSizingEligibilityStatus.REQUIRES_MANAGED_PROFILE,
            "Experimental host sizing requires a LitLaunch-managed browser profile.",
        )
    if not is_loopback_host(config.host):
        return HostSizingEligibility(
            config.host_sizing,
            HostSizingEligibilityStatus.REQUIRES_LOOPBACK,
            "Experimental host sizing requires a loopback application host.",
        )
    return HostSizingEligibility(
        config.host_sizing,
        HostSizingEligibilityStatus.ELIGIBLE,
        "Configuration is eligible; exact runtime window authority is still required.",
    )
