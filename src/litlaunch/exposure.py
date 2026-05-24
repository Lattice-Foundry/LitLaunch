"""Host exposure classification and acknowledgement helpers."""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from litlaunch.config import TrustMode

NETWORK_EXPOSURE_ENV = "LITLAUNCH_ALLOW_NETWORK_EXPOSURE"

__all__ = [
    "ExposureAssessment",
    "ExposureScope",
    "HostExposure",
    "NETWORK_EXPOSURE_ENV",
    "assess_runtime_exposure",
    "classify_exposure_scope",
    "classify_host_exposure",
    "is_loopback_host",
    "network_exposure_acknowledged",
]


class ExposureScope(str, Enum):
    """Operational exposure categories for configured host bindings."""

    LOCALHOST_ONLY = "localhost_only"
    LOOPBACK = "loopback"
    WILDCARD_BIND = "wildcard_bind"
    LOCAL_NETWORK = "local_network"
    PUBLIC_OR_UNKNOWN = "public_or_unknown"
    UNKNOWN = "unknown"


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


@dataclass(frozen=True)
class ExposureAssessment:
    """Operational exposure posture for diagnostics and launch validation."""

    host: str
    trust_mode: TrustMode
    scope: ExposureScope
    acknowledged: bool
    allowed: bool
    severity: str
    summary: str
    recommendation: str
    detail: str

    @property
    def exposed(self) -> bool:
        """Return whether this host binding may be network-visible."""

        return self.scope not in {
            ExposureScope.LOCALHOST_ONLY,
            ExposureScope.LOOPBACK,
        }


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


def classify_exposure_scope(host: str) -> ExposureScope:
    """Classify the exposure scope for a configured host binding."""

    normalized = str(host).strip().lower().rstrip(".")
    if not normalized:
        return ExposureScope.UNKNOWN
    if normalized == "localhost":
        return ExposureScope.LOCALHOST_ONLY
    try:
        ip = ipaddress.ip_address(normalized)
    except ValueError:
        return ExposureScope.PUBLIC_OR_UNKNOWN
    if ip.is_loopback:
        return ExposureScope.LOOPBACK
    if ip.is_unspecified:
        return ExposureScope.WILDCARD_BIND
    if ip.is_private or ip.is_link_local:
        return ExposureScope.LOCAL_NETWORK
    return ExposureScope.PUBLIC_OR_UNKNOWN


def assess_runtime_exposure(
    *,
    host: str,
    trust_mode: TrustMode | str,
    allow_network_exposure: bool = False,
    env: Mapping[str, str] | None = None,
) -> ExposureAssessment:
    """Build a concise runtime exposure assessment."""

    normalized_host = str(host).strip()
    mode = (
        trust_mode if isinstance(trust_mode, TrustMode) else TrustMode(str(trust_mode))
    )
    scope = classify_exposure_scope(normalized_host)
    acknowledged = network_exposure_acknowledged(
        allow_network_exposure=allow_network_exposure,
        env=env,
    )

    if scope in {ExposureScope.LOCALHOST_ONLY, ExposureScope.LOOPBACK}:
        return ExposureAssessment(
            host=normalized_host,
            trust_mode=mode,
            scope=scope,
            acknowledged=acknowledged,
            allowed=True,
            severity="ok",
            summary="Host binding is loopback-only.",
            recommendation="No network exposure acknowledgement is required.",
            detail=_trust_mode_detail(mode),
        )

    if mode == TrustMode.STRICT_LOCAL:
        return ExposureAssessment(
            host=normalized_host,
            trust_mode=mode,
            scope=scope,
            acknowledged=acknowledged,
            allowed=False,
            severity="error",
            summary="Host binding violates strict_local trust mode.",
            recommendation="Use 127.0.0.1, ::1, or localhost for strict_local.",
            detail=(
                "strict_local enforces loopback-only runtime binding. "
                "Exposure acknowledgements do not bypass this mode."
            ),
        )

    if acknowledged:
        return ExposureAssessment(
            host=normalized_host,
            trust_mode=mode,
            scope=scope,
            acknowledged=True,
            allowed=True,
            severity="warning",
            summary="Host binding may be reachable beyond this machine.",
            recommendation=(
                "Use only on trusted networks with appropriate firewall, "
                "routing, authentication, and TLS controls outside LitLaunch."
            ),
            detail=(
                f"{_scope_detail(scope)} Exposure has been explicitly "
                "acknowledged. LitLaunch does not secure Streamlit applications."
            ),
        )

    return ExposureAssessment(
        host=normalized_host,
        trust_mode=mode,
        scope=scope,
        acknowledged=False,
        allowed=False,
        severity="error",
        summary="Network-visible host binding is not acknowledged.",
        recommendation=(
            "Bind to 127.0.0.1 for local-only use or acknowledge intentional "
            "network exposure."
        ),
        detail=(
            f"{_scope_detail(scope)} LitLaunch requires explicit acknowledgement "
            "before launching with non-loopback host bindings."
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


def _trust_mode_detail(mode: TrustMode) -> str:
    if mode == TrustMode.STRICT_LOCAL:
        return "strict_local enforces loopback-only runtime binding."
    if mode == TrustMode.INTERNAL_NETWORK:
        return "internal_network allows intentional network exposure when acknowledged."
    return "development preserves local developer ergonomics with warnings."


def _scope_detail(scope: ExposureScope) -> str:
    if scope == ExposureScope.WILDCARD_BIND:
        return "Wildcard bindings such as 0.0.0.0 or :: may listen on all interfaces."
    if scope == ExposureScope.LOCAL_NETWORK:
        return "Private or link-local addresses may be reachable on a local network."
    if scope == ExposureScope.PUBLIC_OR_UNKNOWN:
        return (
            "Public addresses or non-local hostnames may be reachable depending "
            "on DNS, routing, and firewall configuration."
        )
    return "Host exposure scope could not be classified confidently."
