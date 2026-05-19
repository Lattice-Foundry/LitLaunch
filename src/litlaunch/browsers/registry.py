"""Browser adapter registry."""

from __future__ import annotations

from litlaunch.browsers.base import (
    BrowserAdapter,
    BrowserCapability,
    BrowserKind,
    BrowserResolution,
)
from litlaunch.browsers.chrome import ChromeAdapter
from litlaunch.browsers.default import DefaultBrowserAdapter
from litlaunch.browsers.edge import EdgeAdapter
from litlaunch.config import BrowserChoice
from litlaunch.exceptions import BrowserError
from litlaunch.platforms import OperatingSystem, PlatformDetector, PlatformInfo


class BrowserRegistry:
    """Small explicit registry for browser adapters."""

    def __init__(
        self,
        adapters: list[BrowserAdapter] | tuple[BrowserAdapter, ...] = (),
    ) -> None:
        self._adapters: dict[str, BrowserAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: BrowserAdapter) -> None:
        """Register or replace an adapter by name."""

        self._adapters[adapter.name] = adapter

    def names(self) -> tuple[str, ...]:
        """Return registered adapter names in deterministic order."""

        return tuple(sorted(self._adapters))

    def get(self, name: str) -> BrowserAdapter:
        """Return an adapter by name."""

        try:
            return self._adapters[name]
        except KeyError as exc:
            raise BrowserError(f"Unknown browser adapter: {name}") from exc

    def detect_all(
        self,
        platform_info: PlatformInfo | None = None,
    ) -> tuple[BrowserCapability, ...]:
        """Detect all registered browser capabilities."""

        info = platform_info or PlatformDetector().detect()
        return tuple(self._adapters[name].detect(info) for name in self.names())

    def resolve(
        self,
        choice: BrowserChoice,
        platform_info: PlatformInfo | None = None,
        *,
        prefer_app_mode: bool = False,
        allow_fallback: bool = True,
    ) -> BrowserResolution:
        """Resolve a browser choice against detected capabilities."""

        info = platform_info or PlatformDetector().detect()
        normalized_choice = (
            choice if isinstance(choice, BrowserChoice) else BrowserChoice(str(choice))
        )
        capabilities = {
            capability.kind: capability for capability in self.detect_all(info)
        }
        ordered_kinds = self._resolution_order(normalized_choice, info, prefer_app_mode)
        fallback_chain = tuple(
            capability
            for kind in ordered_kinds
            if (capability := capabilities.get(kind)) is not None
        )

        for capability in fallback_chain:
            if not capability.available:
                if not allow_fallback and normalized_choice != BrowserChoice.AUTO:
                    break
                continue
            if prefer_app_mode and not capability.supports_app_mode:
                if not allow_fallback and normalized_choice != BrowserChoice.AUTO:
                    break
                continue
            return BrowserResolution(
                requested=normalized_choice,
                selected=capability,
                fallback_chain=fallback_chain,
                message=f"Selected {capability.name}.",
            )

        return BrowserResolution(
            requested=normalized_choice,
            selected=None,
            fallback_chain=fallback_chain,
            message="No compatible browser capability was available.",
        )

    def _resolution_order(
        self,
        choice: BrowserChoice,
        platform_info: PlatformInfo,
        prefer_app_mode: bool,
    ) -> tuple[BrowserKind, ...]:
        if choice == BrowserChoice.EDGE:
            return _explicit_order(BrowserKind.EDGE, allow_default=not prefer_app_mode)
        if choice == BrowserChoice.CHROME:
            return _explicit_order(
                BrowserKind.CHROME, allow_default=not prefer_app_mode
            )
        if choice == BrowserChoice.DEFAULT:
            return (BrowserKind.DEFAULT,)
        if not prefer_app_mode:
            return (BrowserKind.DEFAULT, BrowserKind.CHROME, BrowserKind.EDGE)
        if platform_info.os == OperatingSystem.WINDOWS:
            return (BrowserKind.EDGE, BrowserKind.CHROME, BrowserKind.DEFAULT)
        return (BrowserKind.CHROME, BrowserKind.EDGE, BrowserKind.DEFAULT)


def create_default_browser_registry() -> BrowserRegistry:
    """Create the default browser registry."""

    return BrowserRegistry(
        (
            EdgeAdapter(),
            ChromeAdapter(),
            DefaultBrowserAdapter(),
        )
    )


def _explicit_order(
    preferred: BrowserKind,
    *,
    allow_default: bool,
) -> tuple[BrowserKind, ...]:
    alternatives = {
        BrowserKind.EDGE: BrowserKind.CHROME,
        BrowserKind.CHROME: BrowserKind.EDGE,
    }
    if allow_default:
        return (preferred, alternatives[preferred], BrowserKind.DEFAULT)
    return (preferred, alternatives[preferred])
