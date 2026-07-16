"""Public application handoff for Experimental host sizing."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from litlaunch._host_sizing_transport import (
    HOST_SIZING_ENDPOINT_PATH,
    HOST_SIZING_PROTOCOL_VERSION,
    HOST_SIZING_TOKEN_HEADER,
    LITLAUNCH_HOST_SIZING_ENABLED,
    LITLAUNCH_HOST_SIZING_ENDPOINT,
    LITLAUNCH_HOST_SIZING_LAUNCH_ID,
    LITLAUNCH_HOST_SIZING_ORIGIN,
    LITLAUNCH_HOST_SIZING_PROTOCOL,
    LITLAUNCH_HOST_SIZING_SOURCE_ID,
    LITLAUNCH_HOST_SIZING_TOKEN,
    HostSizingTransportError,
    normalize_allowed_origin,
)

_LAUNCH_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,256}$")
_SOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True)
class HostSizingHandoff:
    """Short-lived capability metadata for deliberate app-to-frontend handoff.

    Treat instances as credentials: do not log, persist, or embed them into static
    frontend assets.
    """

    endpoint: str
    launch_id: str
    protocol: int
    source_id: str
    token_header: str
    capability_token: str = field(repr=False)

    def __repr__(self) -> str:
        """Return a useful representation without exposing the capability token."""

        return (
            "HostSizingHandoff("
            f"endpoint={self.endpoint!r}, "
            f"launch_id={self.launch_id!r}, "
            f"protocol={self.protocol!r}, "
            f"source_id={self.source_id!r}, "
            f"token_header={self.token_header!r}, "
            "capability_token='<redacted>')"
        )


def get_host_sizing_handoff() -> HostSizingHandoff | None:
    """Return the active launch handoff, or ``None`` when unavailable.

    Applications must deliberately forward the result to one trusted frontend
    sizing surface. LitLaunch does not discover or inject frontend adapters.
    """

    return _handoff_from_env(os.environ)


def _handoff_from_env(env: Mapping[str, str]) -> HostSizingHandoff | None:
    if str(env.get(LITLAUNCH_HOST_SIZING_ENABLED, "")).strip() != "1":
        return None
    endpoint = str(env.get(LITLAUNCH_HOST_SIZING_ENDPOINT, "")).strip()
    token = str(env.get(LITLAUNCH_HOST_SIZING_TOKEN, "")).strip()
    launch_id = str(env.get(LITLAUNCH_HOST_SIZING_LAUNCH_ID, "")).strip()
    origin = str(env.get(LITLAUNCH_HOST_SIZING_ORIGIN, "")).strip()
    protocol_text = str(env.get(LITLAUNCH_HOST_SIZING_PROTOCOL, "")).strip()
    source_id = str(env.get(LITLAUNCH_HOST_SIZING_SOURCE_ID, "")).strip()
    values = (endpoint, token, launch_id, origin, protocol_text, source_id)
    if any(not value or "\x00" in value for value in values):
        return None
    try:
        protocol = int(protocol_text)
    except ValueError:
        return None
    if protocol != HOST_SIZING_PROTOCOL_VERSION:
        return None
    if len(token) < 32:
        return None
    if not _LAUNCH_ID_PATTERN.fullmatch(launch_id):
        return None
    if not _SOURCE_ID_PATTERN.fullmatch(source_id):
        return None
    if not _valid_endpoint_url(endpoint):
        return None
    try:
        normalized_origin = normalize_allowed_origin(origin)
    except HostSizingTransportError:
        return None
    if normalized_origin != origin:
        return None
    return HostSizingHandoff(
        endpoint=endpoint,
        launch_id=launch_id,
        protocol=protocol,
        source_id=source_id,
        token_header=HOST_SIZING_TOKEN_HEADER,
        capability_token=token,
    )


def _valid_endpoint_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "http"
        and parsed.hostname == "127.0.0.1"
        and port is not None
        and parsed.username is None
        and parsed.password is None
        and parsed.path == HOST_SIZING_ENDPOINT_PATH
        and not parsed.query
        and not parsed.fragment
    )


__all__ = ["HostSizingHandoff", "get_host_sizing_handoff"]
