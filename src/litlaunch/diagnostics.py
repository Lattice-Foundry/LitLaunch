"""Diagnostics helpers for LitLaunch."""

from __future__ import annotations

from litlaunch.platforms import PlatformInfo


class Diagnostics:
    """Small diagnostics helpers for launcher/runtime reporting."""

    @staticmethod
    def platform_summary(platform_info: PlatformInfo) -> str:
        """Return a concise platform summary."""

        return platform_info.summary()
