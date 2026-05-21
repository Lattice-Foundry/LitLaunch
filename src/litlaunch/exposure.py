"""Host exposure classification and acknowledgement helpers."""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from dataclasses import dataclass

from litlaunch.config import TrustMode

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


def validate_host_exposure_policy(
    *,
    host: str,
    trust_mode: TrustMode | str,
    allow_network_exposure: bool = False,
    env: Mapping[str, str] | None = None,
) -> HostExposure:
    """Validate the host binding against the configured trust mode."""

    mode = (
        trust_mode if isinstance(trust_mode, TrustMode) else TrustMode(str(trust_mode))
    )
    exposure = classify_host_exposure(host)
    if not exposure.exposed:
        return exposure
    if mode == TrustMode.STRICT_LOCAL:
        raise ValueError(
            "trust_mode strict_local requires loopback-only host binding. "
            "Use 127.0.0.1, ::1, or localhost."
        )
    if mode in {TrustMode.DEVELOPMENT, TrustMode.INTERNAL_NETWORK} and (
        network_exposure_acknowledged(
            allow_network_exposure=allow_network_exposure,
            env=env,
        )
    ):
        return exposure
    raise ValueError(
        "Network exposure requires explicit acknowledgement. "
        "Use --allow-network-exposure, set allow_network_exposure=true in "
        "the profile, set LITLAUNCH_ALLOW_NETWORK_EXPOSURE=1, or bind to "
        "127.0.0.1 for localhost-only use."
    )


def _is_loopback_host(host: str) -> bool:
    normalized = host.lower().rstrip(".")
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False
