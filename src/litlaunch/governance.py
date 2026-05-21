"""Lightweight runtime governance assessment for LitLaunch."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from litlaunch.config import LauncherConfig, StreamlitFlags, TrustMode
from litlaunch.exposure import (
    ExposureAssessment,
    ExposureScope,
    assess_runtime_exposure,
)
from litlaunch.transport import TlsStatus, TransportPosture, evaluate_transport_posture


@dataclass(frozen=True)
class RuntimeGovernanceAssessment:
    """Concise operational governance summary for one runtime configuration."""

    trust_mode: TrustMode
    host: str
    exposure_scope: ExposureScope
    exposure_acknowledged: bool
    tls_status: TlsStatus
    transport_posture: TransportPosture
    exposure_assessment: ExposureAssessment
    launch_allowed: bool
    highest_severity: str
    findings: tuple[str, ...]
    recommendations: tuple[str, ...]


def evaluate_runtime_governance(
    config: LauncherConfig | None = None,
    *,
    host: str | None = None,
    trust_mode: TrustMode | str | None = None,
    allow_network_exposure: bool | None = None,
    streamlit_flags: StreamlitFlags | None = None,
    streamlit_args: Sequence[str] = (),
) -> RuntimeGovernanceAssessment:
    """Compose trust, exposure, acknowledgement, and transport posture."""

    resolved_host = (
        config.host
        if config is not None and host is None
        else host
        if host is not None
        else "127.0.0.1"
    )
    resolved_trust_mode = (
        config.trust_mode
        if config is not None and trust_mode is None
        else trust_mode
        if trust_mode is not None
        else TrustMode.DEVELOPMENT
    )
    mode = (
        resolved_trust_mode
        if isinstance(resolved_trust_mode, TrustMode)
        else TrustMode(str(resolved_trust_mode))
    )
    resolved_allow_exposure = (
        config.allow_network_exposure
        if config is not None and allow_network_exposure is None
        else bool(allow_network_exposure)
    )
    resolved_streamlit_flags = (
        config.streamlit_flags
        if config is not None and streamlit_flags is None
        else streamlit_flags
    )
    resolved_streamlit_args = (
        config.streamlit_args
        if config is not None and streamlit_args == ()
        else streamlit_args
    )

    exposure = assess_runtime_exposure(
        host=resolved_host,
        trust_mode=mode,
        allow_network_exposure=resolved_allow_exposure,
    )
    transport = evaluate_transport_posture(
        exposure_assessment=exposure,
        streamlit_flags=resolved_streamlit_flags,
        streamlit_args=resolved_streamlit_args,
    )
    findings = _findings(exposure, transport)
    recommendations = _recommendations(exposure, transport)
    highest = _highest_severity(exposure.severity, transport.severity)
    return RuntimeGovernanceAssessment(
        trust_mode=mode,
        host=exposure.host,
        exposure_scope=exposure.scope,
        exposure_acknowledged=exposure.acknowledged,
        tls_status=transport.tls_status,
        transport_posture=transport,
        exposure_assessment=exposure,
        launch_allowed=exposure.allowed,
        highest_severity=highest,
        findings=tuple(findings),
        recommendations=tuple(recommendations),
    )


def validate_runtime_governance(config: LauncherConfig) -> RuntimeGovernanceAssessment:
    """Validate launch governance while preserving existing exposure behavior."""

    assessment = evaluate_runtime_governance(config)
    exposure = assessment.exposure_assessment
    if exposure.allowed:
        return assessment
    if assessment.trust_mode == TrustMode.STRICT_LOCAL and exposure.exposed:
        raise ValueError(
            "trust_mode strict_local requires loopback-only host binding. "
            "Use 127.0.0.1, ::1, or localhost."
        )
    raise ValueError(
        "Network exposure requires explicit acknowledgement. "
        "Use --allow-network-exposure, set allow_network_exposure=true in "
        "the profile, set LITLAUNCH_ALLOW_NETWORK_EXPOSURE=1, or bind to "
        "127.0.0.1 for localhost-only use."
    )


def _findings(
    exposure: ExposureAssessment,
    transport: TransportPosture,
) -> list[str]:
    findings = [exposure.summary]
    if transport.severity != "ok" or transport.network_visible:
        findings.append(transport.summary)
    elif exposure.trust_mode == TrustMode.STRICT_LOCAL:
        findings.append("strict_local is enforcing loopback-only posture.")
    return findings


def _recommendations(
    exposure: ExposureAssessment,
    transport: TransportPosture,
) -> list[str]:
    recommendations: list[str] = []
    if not exposure.exposed:
        recommendations.append("Use strict_local for localhost-only tools.")
    elif exposure.trust_mode == TrustMode.STRICT_LOCAL:
        recommendations.append(
            "Bind to a loopback host such as 127.0.0.1, ::1, or localhost."
        )
    elif not exposure.acknowledged:
        recommendations.append(
            "Use internal_network only when the app is intentionally exposed."
        )
    else:
        recommendations.append(
            "Use internal_network only when the app is intentionally exposed."
        )
    if transport.plaintext_network_risk:
        recommendations.append(
            "Use Streamlit TLS or an approved reverse proxy for "
            "network-visible deployments."
        )
    elif transport.tls_status == TlsStatus.INCOMPLETE:
        recommendations.append(
            "Set both server.sslCertFile and server.sslKeyFile, or remove "
            "partial TLS settings."
        )
    recommendations.append("Review diagnostics bundles manually before sharing.")
    return _dedupe(recommendations)


def _highest_severity(*severities: str) -> str:
    order = {"ok": 0, "info": 0, "warning": 1, "error": 2}
    return max(severities, key=lambda value: order.get(value, 0))


def _dedupe(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        deduped.append(value)
        seen.add(value)
    return tuple(deduped)
