"""Browser adapter implementations."""

from litlaunch.browsers.base import BrowserAdapter
from litlaunch.browsers.chrome import ChromeAdapter
from litlaunch.browsers.edge import EdgeAdapter
from litlaunch.browsers.registry import BrowserRegistry

__all__ = [
    "BrowserAdapter",
    "BrowserRegistry",
    "ChromeAdapter",
    "EdgeAdapter",
]
