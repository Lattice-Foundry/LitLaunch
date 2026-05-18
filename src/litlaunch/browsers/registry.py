"""Browser adapter registry."""

from __future__ import annotations

from litlaunch.browsers.base import BrowserAdapter
from litlaunch.exceptions import BrowserError


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
