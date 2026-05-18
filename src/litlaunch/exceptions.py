"""Exception hierarchy for LitLaunch."""


class LitLaunchError(Exception):
    """Base exception for LitLaunch failures."""


class ConfigurationError(LitLaunchError):
    """Raised when launcher configuration is invalid."""


class CommandBuildError(LitLaunchError):
    """Raised when a launch command cannot be built safely."""


class BrowserError(LitLaunchError):
    """Raised for browser adapter failures."""


class ProcessError(LitLaunchError):
    """Raised for process lifecycle failures."""


class PortError(LitLaunchError):
    """Raised for port selection or port ownership failures."""
