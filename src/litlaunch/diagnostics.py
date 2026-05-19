"""Diagnostics helpers for LitLaunch."""

from __future__ import annotations

from litlaunch.browsers import BrowserCapability, BrowserResolution
from litlaunch.platforms import PlatformInfo


class Diagnostics:
    """Small diagnostics helpers for launcher/runtime reporting."""

    @staticmethod
    def platform_summary(platform_info: PlatformInfo) -> str:
        """Return a concise platform summary."""

        return platform_info.summary()

    @staticmethod
    def browser_summary(resolution: BrowserResolution) -> str:
        """Return a concise browser resolution summary."""

        if resolution.selected is None:
            return f"Browser: unavailable ({resolution.message})"
        return f"Browser: {resolution.selected.name} ({resolution.message})"

    @staticmethod
    def browser_capabilities(capabilities: tuple[BrowserCapability, ...]) -> str:
        """Return a plain-text capability summary."""

        return ", ".join(
            f"{capability.name}: "
            f"{'available' if capability.available else 'unavailable'}"
            for capability in capabilities
        )
