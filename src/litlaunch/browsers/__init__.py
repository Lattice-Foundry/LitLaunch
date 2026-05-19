"""Browser adapter implementations."""

from litlaunch.browsers.base import (
    BrowserAdapter,
    BrowserCapability,
    BrowserKind,
    BrowserResolution,
)
from litlaunch.browsers.chrome import ChromeAdapter
from litlaunch.browsers.default import DefaultBrowserAdapter
from litlaunch.browsers.edge import EdgeAdapter
from litlaunch.browsers.registry import BrowserRegistry, create_default_browser_registry

__all__ = [
    "BrowserAdapter",
    "BrowserCapability",
    "BrowserKind",
    "BrowserResolution",
    "BrowserRegistry",
    "ChromeAdapter",
    "DefaultBrowserAdapter",
    "EdgeAdapter",
    "create_default_browser_registry",
]
