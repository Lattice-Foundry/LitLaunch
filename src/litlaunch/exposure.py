"""Host exposure classification and acknowledgement helpers."""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from dataclasses import dataclass

NETWORK_EXPOSURE_ENV = "LITLAUNCH_ALLOW_NETWORK_EXPOSURE"


@dataclass(frozen=True)
class HostExposure:
    """Resolved network exposure posture for a configured host binding."""

    host: str
    is_loopback: bool
    warning: str | None

    @property
    def exposed(self) -> bool:
        """Return whether the host may bind beyond this machine."""

        return not self.is_loopback


def classify_host_exposure(host: str) -> HostExposure:
    """Classify whether a configured host is loopback-only or network-facing."""

    normalized = str(host).strip()
    if _is_loopback_host(normalized):
        return HostExposure(host=normalized, is_loopback=True, warning=None)
    return HostExposure(
        host=normalized,
        is_loopback=False,
        warning=(
            f"Host {normalized!r} is not loopback-only. Streamlit may be "
            "reachable from the local network or broader network depending on "
            "routing and firewall configuration."
        ),
    )


def is_loopback_host(host: str) -> bool:
    """Return whether a host string is known to be loopback-only."""

    return _is_loopback_host(str(host).strip())


def network_exposure_acknowledged(
    *,
    allow_network_exposure: bool = False,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Return whether network exposure has been explicitly acknowledged."""

    if allow_network_exposure:
        return True
    values = os.environ if env is None else env
    return str(values.get(NETWORK_EXPOSURE_ENV, "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _is_loopback_host(host: str) -> bool:
    normalized = host.lower().rstrip(".")
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False
