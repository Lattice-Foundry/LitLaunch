"""Transport/TLS posture helpers for LitLaunch diagnostics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from litlaunch.config import StreamlitFlags, TrustMode
from litlaunch.exposure import ExposureAssessment, assess_runtime_exposure

TLS_CERT_FLAG = "server.sslcertfile"
TLS_KEY_FLAG = "server.sslkeyfile"


class TlsStatus(str, Enum):
    """Streamlit-native TLS configuration state."""

    NOT_CONFIGURED = "not_configured"
    CONFIGURED = "configured"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True)
class TransportPosture:
    """Concise transport posture for diagnostics and launch warnings."""

    tls_status: TlsStatus
    cert_configured: bool
    key_configured: bool
    network_visible: bool
    plaintext_network_risk: bool
    severity: str
    summary: str
    recommendation: str
    detail: str


def evaluate_transport_posture(
    *,
    host: str | None = None,
    trust_mode: TrustMode | str = TrustMode.DEVELOPMENT,
    allow_network_exposure: bool = False,
    exposure_assessment: ExposureAssessment | None = None,
    streamlit_flags: StreamlitFlags | None = None,
    streamlit_args: Sequence[str] = (),
) -> TransportPosture:
    """Evaluate Streamlit-native TLS and network transport posture."""

    assessment = exposure_assessment or assess_runtime_exposure(
        host=host or "127.0.0.1",
        trust_mode=trust_mode,
        allow_network_exposure=allow_network_exposure,
    )
    cert_configured = _streamlit_flag_has_value(
        TLS_CERT_FLAG,
        streamlit_flags=streamlit_flags,
        streamlit_args=streamlit_args,
    )
    key_configured = _streamlit_flag_has_value(
        TLS_KEY_FLAG,
        streamlit_flags=streamlit_flags,
        streamlit_args=streamlit_args,
    )
    if cert_configured and key_configured:
        tls_status = TlsStatus.CONFIGURED
    elif cert_configured or key_configured:
        tls_status = TlsStatus.INCOMPLETE
    else:
        tls_status = TlsStatus.NOT_CONFIGURED

    network_visible = assessment.exposed
    if tls_status == TlsStatus.INCOMPLETE:
        return TransportPosture(
            tls_status=tls_status,
            cert_configured=cert_configured,
            key_configured=key_configured,
            network_visible=network_visible,
            plaintext_network_risk=network_visible,
            severity="warning",
            summary="Streamlit TLS configuration appears incomplete.",
            recommendation=(
                "Set both server.sslCertFile and server.sslKeyFile, or remove "
                "partial TLS settings."
            ),
            detail=_tls_detail(cert_configured, key_configured),
        )

    if network_visible and tls_status == TlsStatus.NOT_CONFIGURED:
        return TransportPosture(
            tls_status=tls_status,
            cert_configured=False,
            key_configured=False,
            network_visible=True,
            plaintext_network_risk=True,
            severity="warning",
            summary="Network-visible traffic appears to use plaintext HTTP.",
            recommendation=(
                "Use Streamlit-native TLS or approved reverse-proxy/network "
                "infrastructure for internal deployments."
            ),
            detail=(
                "LitLaunch does not terminate TLS or add authentication. "
                "Non-loopback HTTP should be treated as network-visible plaintext."
            ),
        )

    if network_visible and tls_status == TlsStatus.CONFIGURED:
        return TransportPosture(
            tls_status=tls_status,
            cert_configured=True,
            key_configured=True,
            network_visible=True,
            plaintext_network_risk=False,
            severity="warning",
            summary="Streamlit-native TLS appears configured for network exposure.",
            recommendation=(
                "Confirm certificate handling, authentication, and network "
                "controls outside LitLaunch."
            ),
            detail=(
                "TLS encrypts transport but does not authenticate users or secure "
                "the Streamlit app by itself."
            ),
        )

    if tls_status == TlsStatus.CONFIGURED:
        return TransportPosture(
            tls_status=tls_status,
            cert_configured=True,
            key_configured=True,
            network_visible=False,
            plaintext_network_risk=False,
            severity="ok",
            summary="Streamlit-native TLS appears configured.",
            recommendation="No network-visible transport risk was detected.",
            detail="Both server.sslCertFile and server.sslKeyFile are configured.",
        )

    return TransportPosture(
        tls_status=tls_status,
        cert_configured=False,
        key_configured=False,
        network_visible=False,
        plaintext_network_risk=False,
        severity="ok",
        summary="TLS is not configured for this local-only posture.",
        recommendation="Loopback/local development does not require TLS.",
        detail=(
            "LitLaunch reports transport posture; it does not terminate TLS or "
            "secure Streamlit applications."
        ),
    )


def _streamlit_flag_has_value(
    flag_name: str,
    *,
    streamlit_flags: StreamlitFlags | None,
    streamlit_args: Sequence[str],
) -> bool:
    normalized_flag = _normalize_flag_name(flag_name)
    for name, value in _iter_streamlit_flag_values(streamlit_flags):
        if _normalize_flag_name(name) == normalized_flag and _has_value(value):
            return True
    for name, value in _iter_sequence_flag_values(streamlit_args):
        if _normalize_flag_name(name) == normalized_flag and _has_value(value):
            return True
    return False


def _iter_streamlit_flag_values(
    streamlit_flags: StreamlitFlags | None,
) -> tuple[tuple[str, object], ...]:
    if streamlit_flags is None:
        return ()
    if isinstance(streamlit_flags, Mapping):
        return tuple((str(key), value) for key, value in streamlit_flags.items())
    return tuple(_iter_sequence_flag_values(streamlit_flags))


def _iter_sequence_flag_values(
    values: Sequence[str],
) -> tuple[tuple[str, object], ...]:
    items = tuple(str(value) for value in values)
    parsed: list[tuple[str, object]] = []
    index = 0
    while index < len(items):
        item = items[index].strip()
        if not item.startswith("--"):
            index += 1
            continue
        if "=" in item:
            name, value = item.split("=", 1)
            parsed.append((name, value))
            index += 1
            continue
        next_value = items[index + 1] if index + 1 < len(items) else None
        if next_value is not None and not next_value.strip().startswith("--"):
            parsed.append((item, next_value))
            index += 2
            continue
        parsed.append((item, None))
        index += 1
    return tuple(parsed)


def _normalize_flag_name(name: str) -> str:
    stripped = str(name).strip()
    if stripped.startswith("--"):
        stripped = stripped[2:]
    return stripped.split("=", 1)[0].replace("_", ".").lower()


def _has_value(value: object) -> bool:
    return value is not None and str(value).strip() != ""


def _tls_detail(cert_configured: bool, key_configured: bool) -> str:
    missing = []
    if not cert_configured:
        missing.append("server.sslCertFile")
    if not key_configured:
        missing.append("server.sslKeyFile")
    configured = []
    if cert_configured:
        configured.append("server.sslCertFile")
    if key_configured:
        configured.append("server.sslKeyFile")
    configured_text = ", ".join(configured) or "none"
    missing_text = ", ".join(missing) or "none"
    return f"Configured: {configured_text}. Missing: {missing_text}."
