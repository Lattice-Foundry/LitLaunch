"""Streamlit package availability probing for diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata


@dataclass(frozen=True)
class StreamlitAvailability:
    """Streamlit import/version availability check result."""

    available: bool
    version: str | None
    message: str


def check_streamlit_availability() -> StreamlitAvailability:
    """Return Streamlit package availability using package metadata only."""

    try:
        version = metadata.version("streamlit")
    except metadata.PackageNotFoundError:
        return StreamlitAvailability(
            available=False,
            version=None,
            message="Streamlit is not installed in this Python environment.",
        )
    return StreamlitAvailability(
        available=True,
        version=version,
        message=f"Streamlit {version} detected.",
    )
