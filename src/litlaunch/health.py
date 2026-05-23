"""Streamlit health-check helpers."""

from __future__ import annotations

import ipaddress
import time
from collections.abc import Callable
from urllib import request


def build_streamlit_health_url(host: str, port: int) -> str:
    """Build the Streamlit health endpoint URL."""

    return (
        f"http://{_format_host_for_url(_host_for_client_url(host))}:{port}"
        "/_stcore/health"
    )


def build_streamlit_app_url(host: str, port: int) -> str:
    """Build the Streamlit app URL."""

    return f"http://{_format_host_for_url(_host_for_client_url(host))}:{port}"


def _host_for_client_url(host: str) -> str:
    normalized = str(host).strip()
    try:
        address = ipaddress.ip_address(normalized.strip("[]"))
    except ValueError:
        return normalized
    if address.is_unspecified:
        return "::1" if address.version == 6 else "127.0.0.1"
    return normalized


def _format_host_for_url(host: str) -> str:
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


class HealthChecker:
    """Poll Streamlit's health endpoint until it responds or times out."""

    def __init__(
        self,
        *,
        opener: Callable[..., object] = request.urlopen,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.opener = opener
        self.sleep = sleep
        self.monotonic = monotonic

    def check_once(self, url: str) -> bool:
        """Return whether one health check request succeeds."""

        try:
            with self.opener(url, timeout=1) as response:
                status = int(getattr(response, "status", 200))
        except Exception:
            return False
        return 200 <= status < 300

    def wait_until_healthy(
        self,
        url: str,
        timeout_seconds: float = 15.0,
        interval_seconds: float = 0.25,
    ) -> bool:
        """Poll the health endpoint until it succeeds or the timeout expires."""

        deadline = self.monotonic() + timeout_seconds
        while True:
            if self.check_once(url):
                return True
            if self.monotonic() >= deadline:
                return False
            self.sleep(interval_seconds)
