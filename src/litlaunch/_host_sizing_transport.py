"""Private authenticated host-sizing report transport foundation.

This module accepts and retains sizing observations only. It intentionally has no
window, browser, geometry, or native mutation dependency.
"""

from __future__ import annotations

import hmac
import json
import math
import re
import secrets
import socket
import threading
import time
from collections import Counter, deque
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import MappingProxyType
from typing import Any
from urllib.parse import urlparse

from litlaunch.console import ConsoleRenderer
from litlaunch.exposure import is_loopback_host

HOST_SIZING_PROTOCOL_VERSION = 1
HOST_SIZING_ENDPOINT_PATH = "/host-sizing/report"
HOST_SIZING_TOKEN_HEADER = "X-LitLaunch-Host-Sizing-Token"
HOST_SIZING_DEFAULT_HOST = "127.0.0.1"
HOST_SIZING_MAX_BODY_BYTES = 4096
HOST_SIZING_MAX_DIMENSION_CSS = 16384.0
HOST_SIZING_MAX_SEQUENCE = (1 << 63) - 1
HOST_SIZING_MAX_SOURCE_ID_LENGTH = 128
HOST_SIZING_MIN_DEVICE_PIXEL_RATIO = 0.5
HOST_SIZING_MAX_DEVICE_PIXEL_RATIO = 8.0
HOST_SIZING_MAX_REQUEST_WORKERS = 8
HOST_SIZING_CONNECTION_TIMEOUT_SECONDS = 2.0

LITLAUNCH_HOST_SIZING_ENABLED = "LITLAUNCH_HOST_SIZING_ENABLED"
LITLAUNCH_HOST_SIZING_ENDPOINT = "LITLAUNCH_HOST_SIZING_ENDPOINT"
LITLAUNCH_HOST_SIZING_TOKEN = "LITLAUNCH_HOST_SIZING_TOKEN"
LITLAUNCH_HOST_SIZING_LAUNCH_ID = "LITLAUNCH_HOST_SIZING_LAUNCH_ID"
LITLAUNCH_HOST_SIZING_ORIGIN = "LITLAUNCH_HOST_SIZING_ORIGIN"
LITLAUNCH_HOST_SIZING_PROTOCOL = "LITLAUNCH_HOST_SIZING_PROTOCOL"
LITLAUNCH_HOST_SIZING_SOURCE_ID = "LITLAUNCH_HOST_SIZING_SOURCE_ID"
HOST_SIZING_ENV_KEYS = frozenset(
    {
        LITLAUNCH_HOST_SIZING_ENABLED,
        LITLAUNCH_HOST_SIZING_ENDPOINT,
        LITLAUNCH_HOST_SIZING_TOKEN,
        LITLAUNCH_HOST_SIZING_LAUNCH_ID,
        LITLAUNCH_HOST_SIZING_ORIGIN,
        LITLAUNCH_HOST_SIZING_PROTOCOL,
        LITLAUNCH_HOST_SIZING_SOURCE_ID,
    }
)

_SOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_LAUNCH_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,256}$")
_ALLOWED_REQUEST_HEADERS = frozenset(
    {
        "content-type",
        HOST_SIZING_TOKEN_HEADER.lower(),
    }
)
_SocketRequest = socket.socket | tuple[bytes, socket.socket]


class HostSizingTransportError(RuntimeError):
    """Raised when the private host-sizing channel cannot be created safely."""


class _BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Serve a small bounded set of local requests without retaining workers."""

    daemon_threads = True
    request_queue_size = HOST_SIZING_MAX_REQUEST_WORKERS

    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler_class: type[BaseHTTPRequestHandler],
        *,
        max_workers: int = HOST_SIZING_MAX_REQUEST_WORKERS,
    ) -> None:
        if max_workers < 1:
            raise ValueError("Host-sizing request worker bound must be positive.")
        self._worker_slots = threading.BoundedSemaphore(max_workers)
        super().__init__(server_address, request_handler_class)

    def process_request(self, request: _SocketRequest, client_address: object) -> None:
        if not self._worker_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._worker_slots.release()
            raise

    def process_request_thread(
        self,
        request: _SocketRequest,
        client_address: object,
    ) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._worker_slots.release()


class HostSizingReportDecision(str, Enum):
    """Private report retention decisions."""

    ACCEPTED = "accepted"
    STALE = "stale"
    AUTHORITY_CONFLICT = "authority_conflict"
    RATE_LIMITED = "rate_limited"
    CLOSED = "closed"


@dataclass(frozen=True)
class SurfaceDimensions:
    """Validated CSS-pixel dimensions from one report section."""

    height: float
    width: float | None = None


@dataclass(frozen=True)
class HostSizingReport:
    """Validated private protocol-v1 host-sizing observation."""

    protocol: int
    launch_id: str
    source_id: str
    sequence: int
    device_pixel_ratio: float
    content: SurfaceDimensions
    host_viewport: SurfaceDimensions
    desired_host_viewport: SurfaceDimensions


@dataclass(frozen=True)
class HostSizingReportResult:
    """Result from retaining or rejecting one authenticated valid report."""

    decision: HostSizingReportDecision
    message: str
    accepted: bool


@dataclass(frozen=True)
class HostSizingChannelSnapshot:
    """Thread-safe bounded diagnostic snapshot without credentials."""

    active: bool
    bound_source_id: str | None
    last_sequence: int | None
    latest_report: HostSizingReport | None
    accepted_count: int
    rejection_counts: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "rejection_counts",
            MappingProxyType(dict(self.rejection_counts)),
        )


@dataclass(frozen=True)
class HostSizingChannelConfig:
    """Private per-launch endpoint configuration for app environment handoff."""

    host: str
    port: int
    token: str = field(repr=False)
    launch_id: str
    allowed_origin: str
    protocol: int = HOST_SIZING_PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if self.host != HOST_SIZING_DEFAULT_HOST:
            raise HostSizingTransportError(
                "Host-sizing transport must bind to literal 127.0.0.1."
            )
        if not isinstance(self.port, int) or isinstance(self.port, bool):
            raise HostSizingTransportError("Host-sizing port must be an integer.")
        if self.port < 1 or self.port > 65535:
            raise HostSizingTransportError("Host-sizing port is outside 1-65535.")
        if len(self.token) < 32:
            raise HostSizingTransportError(
                "Host-sizing capability token is unexpectedly short."
            )
        if not _LAUNCH_ID_PATTERN.fullmatch(self.launch_id):
            raise HostSizingTransportError("Host-sizing launch ID is invalid.")
        normalized_origin = normalize_allowed_origin(self.allowed_origin)
        object.__setattr__(self, "allowed_origin", normalized_origin)
        if self.protocol != HOST_SIZING_PROTOCOL_VERSION:
            raise HostSizingTransportError("Unsupported host-sizing protocol version.")

    @property
    def endpoint(self) -> str:
        """Return the token-free loopback report endpoint."""

        return f"http://{self.host}:{self.port}{HOST_SIZING_ENDPOINT_PATH}"

    def as_env(self) -> dict[str, str]:
        """Return launch-scoped environment values for deliberate app handoff."""

        return {
            LITLAUNCH_HOST_SIZING_ENABLED: "1",
            LITLAUNCH_HOST_SIZING_ENDPOINT: self.endpoint,
            LITLAUNCH_HOST_SIZING_TOKEN: self.token,
            LITLAUNCH_HOST_SIZING_LAUNCH_ID: self.launch_id,
            LITLAUNCH_HOST_SIZING_ORIGIN: self.allowed_origin,
            LITLAUNCH_HOST_SIZING_PROTOCOL: str(self.protocol),
        }


class HostSizingReportStore:
    """Thread-safe one-source latest-report retention with bounded request rate."""

    def __init__(
        self,
        *,
        clock: Any = time,
        max_reports_per_window: int = 60,
        rate_window_seconds: float = 1.0,
        max_accepted_reports: int | None = 1024,
    ) -> None:
        # max_accepted_reports is a one-shot lifetime ceiling. ``None`` disables it
        # so a session-length policy (continuous) is bounded only by the sliding
        # per-window rate limit and never permanently stops accepting reports.
        if max_reports_per_window < 1:
            raise ValueError("Host-sizing report limits must be positive.")
        if max_accepted_reports is not None and max_accepted_reports < 1:
            raise ValueError("Host-sizing report limits must be positive.")
        if rate_window_seconds <= 0:
            raise ValueError("Host-sizing rate window must be positive.")
        self._clock = clock
        self._max_reports_per_window = max_reports_per_window
        self._rate_window_seconds = float(rate_window_seconds)
        self._max_accepted_reports = max_accepted_reports
        self._lock = threading.Lock()
        self._active = True
        self._bound_source_id: str | None = None
        self._last_sequence: int | None = None
        self._latest_report: HostSizingReport | None = None
        self._accepted_count = 0
        self._rejections: Counter[str] = Counter()
        self._request_times: deque[float] = deque()

    def accept(self, report: HostSizingReport) -> HostSizingReportResult:
        """Retain the latest monotonic report or fail closed."""

        with self._lock:
            if not self._active:
                return self._reject(
                    HostSizingReportDecision.CLOSED,
                    "Host-sizing channel is closed.",
                )

            now = float(self._clock.monotonic())
            cutoff = now - self._rate_window_seconds
            while self._request_times and self._request_times[0] <= cutoff:
                self._request_times.popleft()
            if len(self._request_times) >= self._max_reports_per_window or (
                self._max_accepted_reports is not None
                and self._accepted_count >= self._max_accepted_reports
            ):
                return self._reject(
                    HostSizingReportDecision.RATE_LIMITED,
                    "Host-sizing report rate limit exceeded.",
                )
            self._request_times.append(now)

            if (
                self._bound_source_id is not None
                and report.source_id != self._bound_source_id
            ):
                return self._reject(
                    HostSizingReportDecision.AUTHORITY_CONFLICT,
                    "Host-sizing source authority conflict.",
                )
            if (
                self._last_sequence is not None
                and report.sequence <= self._last_sequence
            ):
                return self._reject(
                    HostSizingReportDecision.STALE,
                    "Host-sizing report sequence is stale.",
                )

            if self._bound_source_id is None:
                self._bound_source_id = report.source_id
            self._last_sequence = report.sequence
            self._latest_report = report
            self._accepted_count += 1
            return HostSizingReportResult(
                HostSizingReportDecision.ACCEPTED,
                "Host-sizing report accepted.",
                True,
            )

    def close(self) -> None:
        """Permanently stop accepting reports while retaining the final snapshot."""

        with self._lock:
            self._active = False
            self._request_times.clear()

    def snapshot(self) -> HostSizingChannelSnapshot:
        """Return an immutable credential-free view of retained state."""

        with self._lock:
            return HostSizingChannelSnapshot(
                active=self._active,
                bound_source_id=self._bound_source_id,
                last_sequence=self._last_sequence,
                latest_report=self._latest_report,
                accepted_count=self._accepted_count,
                rejection_counts=dict(self._rejections),
            )

    def record_rejection(self, reason: str) -> None:
        """Count HTTP/auth/schema rejection classes without retaining payloads."""

        with self._lock:
            self._rejections[str(reason)] += 1

    def _reject(
        self,
        decision: HostSizingReportDecision,
        message: str,
    ) -> HostSizingReportResult:
        self._rejections[decision.value] += 1
        return HostSizingReportResult(decision, message, False)


class HostSizingChannel:
    """Owned private loopback endpoint with an idempotent session cleanup seam."""

    def __init__(
        self,
        *,
        config: HostSizingChannelConfig,
        store: HostSizingReportStore,
        server: _BoundedThreadingHTTPServer,
        thread: threading.Thread,
    ) -> None:
        self.config = config
        self.store = store
        self._server = server
        self._thread = thread
        self._close_lock = threading.Lock()
        self._closed = False

    @property
    def active(self) -> bool:
        """Return whether the channel has not been closed."""

        with self._close_lock:
            return not self._closed

    def snapshot(self) -> HostSizingChannelSnapshot:
        """Return the latest bounded report-store snapshot."""

        return self.store.snapshot()

    def close(self) -> None:
        """Stop acceptance first, then close the HTTP server exactly once."""

        with self._close_lock:
            if self._closed:
                return
            self._closed = True
            self.store.close()
            server = self._server
            thread = self._thread
        server.shutdown()
        server.server_close()
        if thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def __enter__(self) -> HostSizingChannel:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


@dataclass(frozen=True)
class _HostSizingRequestContext:
    token: str = field(repr=False)
    launch_id: str
    allowed_origin: str
    store: HostSizingReportStore
    expected_source_id: str | None = None
    accepted_report_callback: Callable[[HostSizingReport], object] | None = None


def start_host_sizing_channel(
    *,
    allowed_origin: str,
    host: str = HOST_SIZING_DEFAULT_HOST,
    port: int = 0,
    console_renderer: ConsoleRenderer | None = None,
    token: str | None = None,
    launch_id: str | None = None,
    store: HostSizingReportStore | None = None,
    expected_source_id: str | None = None,
    accepted_report_callback: Callable[[HostSizingReport], object] | None = None,
) -> HostSizingChannel:
    """Start one private loopback channel or fail without a partial lease."""

    if host != HOST_SIZING_DEFAULT_HOST or not is_loopback_host(host):
        raise HostSizingTransportError(
            "Host-sizing transport must bind to literal 127.0.0.1."
        )
    if not isinstance(port, int) or isinstance(port, bool) or not 0 <= port <= 65535:
        raise HostSizingTransportError("Host-sizing port must be 0-65535.")
    normalized_origin = normalize_allowed_origin(allowed_origin)
    resolved_token = token or secrets.token_urlsafe(32)
    resolved_launch_id = launch_id or secrets.token_urlsafe(18)
    resolved_source_id = (
        _require_identifier(
            expected_source_id,
            name="expected_source_id",
            pattern=_SOURCE_ID_PATTERN,
        )
        if expected_source_id is not None
        else None
    )
    resolved_store = store or HostSizingReportStore()
    request_context = _HostSizingRequestContext(
        token=resolved_token,
        launch_id=resolved_launch_id,
        allowed_origin=normalized_origin,
        store=resolved_store,
        expected_source_id=resolved_source_id,
        accepted_report_callback=accepted_report_callback,
    )
    handler = _build_host_sizing_handler(request_context)

    try:
        server = _BoundedThreadingHTTPServer((host, port), handler)
    except OSError as exc:
        resolved_store.close()
        raise HostSizingTransportError(
            "Could not bind the private host-sizing loopback endpoint."
        ) from exc
    actual_port = int(server.server_address[1])
    try:
        config = HostSizingChannelConfig(
            host=host,
            port=actual_port,
            token=resolved_token,
            launch_id=resolved_launch_id,
            allowed_origin=normalized_origin,
        )
        if console_renderer is not None:
            console_renderer.add_redaction(resolved_token)
        thread = threading.Thread(
            target=server.serve_forever,
            daemon=True,
            name="litlaunch-host-sizing-endpoint",
        )
        thread.start()
    except Exception:
        resolved_store.close()
        server.server_close()
        raise
    return HostSizingChannel(
        config=config,
        store=resolved_store,
        server=server,
        thread=thread,
    )


def normalize_allowed_origin(value: str) -> str:
    """Validate one exact loopback HTTP(S) origin without path or credentials."""

    origin = str(value).strip()
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"}:
        raise HostSizingTransportError("Allowed origin must use http or https.")
    if parsed.username or parsed.password:
        raise HostSizingTransportError("Allowed origin must not include credentials.")
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise HostSizingTransportError("Allowed origin must not include a path.")
    if parsed.hostname is None or not is_loopback_host(parsed.hostname):
        raise HostSizingTransportError("Allowed origin must resolve to loopback.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise HostSizingTransportError("Allowed origin port is invalid.") from exc
    if port is None:
        raise HostSizingTransportError("Allowed origin must include an explicit port.")
    host = parsed.hostname.lower().rstrip(".")
    if ":" in host:
        host = f"[{host}]"
    return f"{parsed.scheme.lower()}://{host}:{port}"


def parse_host_sizing_report(payload: bytes) -> HostSizingReport:
    """Parse strict protocol-v1 JSON without retaining malformed input."""

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HostSizingTransportError("Report body must be UTF-8 JSON.") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise HostSizingTransportError("Report body is not strict JSON.") from exc
    root = _require_object(value, "report")
    _require_keys(
        root,
        required={
            "protocol",
            "launch_id",
            "source_id",
            "sequence",
            "device_pixel_ratio",
            "content",
            "host_viewport",
            "desired_host_viewport",
        },
        name="report",
    )

    protocol = root["protocol"]
    if (
        not isinstance(protocol, int)
        or isinstance(protocol, bool)
        or protocol != HOST_SIZING_PROTOCOL_VERSION
    ):
        raise HostSizingTransportError("Unsupported host-sizing protocol version.")
    launch_id = _require_identifier(
        root["launch_id"],
        name="launch_id",
        pattern=_LAUNCH_ID_PATTERN,
    )
    source_id = _require_identifier(
        root["source_id"],
        name="source_id",
        pattern=_SOURCE_ID_PATTERN,
    )
    sequence = root["sequence"]
    if (
        not isinstance(sequence, int)
        or isinstance(sequence, bool)
        or sequence < 1
        or sequence > HOST_SIZING_MAX_SEQUENCE
    ):
        raise HostSizingTransportError(
            "sequence must be an integer from 1 through 2^63-1."
        )

    return HostSizingReport(
        protocol=protocol,
        launch_id=launch_id,
        source_id=source_id,
        sequence=sequence,
        device_pixel_ratio=_require_device_pixel_ratio(root["device_pixel_ratio"]),
        content=_parse_dimensions(
            root["content"],
            name="content",
            width_optional=True,
        ),
        host_viewport=_parse_dimensions(
            root["host_viewport"],
            name="host_viewport",
            width_optional=True,
        ),
        desired_host_viewport=_parse_dimensions(
            root["desired_host_viewport"],
            name="desired_host_viewport",
            width_optional=True,
        ),
    )


def _build_host_sizing_handler(
    context: _HostSizingRequestContext,
) -> type[BaseHTTPRequestHandler]:
    class HostSizingHandler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(HOST_SIZING_CONNECTION_TIMEOUT_SECONDS)

        def do_OPTIONS(self) -> None:  # noqa: N802 - HTTP handler contract.
            if self.path != HOST_SIZING_ENDPOINT_PATH:
                self._write_json(404, {"ok": False, "message": "Not found."})
                return
            if not self._host_header_allowed():
                context.store.record_rejection("host")
                self._write_json(403, {"ok": False, "message": "Forbidden."})
                return
            origin = self.headers.get("Origin", "")
            if not self._origin_allowed(origin):
                context.store.record_rejection("origin")
                self._write_json(403, {"ok": False, "message": "Forbidden."})
                return
            requested_method = self.headers.get(
                "Access-Control-Request-Method",
                "",
            ).upper()
            if requested_method != "POST":
                context.store.record_rejection("preflight_method")
                self._write_json(
                    405,
                    {"ok": False, "message": "Method not allowed."},
                    origin=origin,
                )
                return
            requested_headers = {
                item.strip().lower()
                for item in self.headers.get(
                    "Access-Control-Request-Headers",
                    "",
                ).split(",")
                if item.strip()
            }
            if not requested_headers.issubset(_ALLOWED_REQUEST_HEADERS):
                context.store.record_rejection("preflight_headers")
                self._write_json(
                    400,
                    {"ok": False, "message": "Invalid preflight headers."},
                    origin=origin,
                )
                return
            self.send_response(204)
            self._write_cors_headers(origin)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802 - HTTP handler contract.
            if self.path != HOST_SIZING_ENDPOINT_PATH:
                self._write_json(404, {"ok": False, "message": "Not found."})
                return
            if not self._host_header_allowed():
                context.store.record_rejection("host")
                self._write_json(403, {"ok": False, "message": "Forbidden."})
                return
            origin = self.headers.get("Origin", "")
            if not self._origin_allowed(origin):
                context.store.record_rejection("origin")
                self._write_json(403, {"ok": False, "message": "Forbidden."})
                return
            supplied_token = self.headers.get(HOST_SIZING_TOKEN_HEADER, "")
            if not supplied_token or not hmac.compare_digest(
                supplied_token,
                context.token,
            ):
                context.store.record_rejection("authentication")
                self._write_json(
                    403,
                    {"ok": False, "message": "Forbidden."},
                    origin=origin,
                )
                return
            content_type = self.headers.get("Content-Type", "")
            if content_type.split(";", 1)[0].strip().lower() != "application/json":
                context.store.record_rejection("content_type")
                self._write_json(
                    415,
                    {"ok": False, "message": "Content-Type must be application/json."},
                    origin=origin,
                )
                return
            content_length = self.headers.get("Content-Length")
            if content_length is None:
                context.store.record_rejection("content_length")
                self._write_json(
                    411,
                    {"ok": False, "message": "Content-Length is required."},
                    origin=origin,
                )
                return
            try:
                body_length = int(content_length)
            except ValueError:
                body_length = -1
            if body_length < 0:
                context.store.record_rejection("content_length")
                self._write_json(
                    400,
                    {"ok": False, "message": "Content-Length is invalid."},
                    origin=origin,
                )
                return
            if body_length > HOST_SIZING_MAX_BODY_BYTES:
                context.store.record_rejection("body_too_large")
                self._write_json(
                    413,
                    {"ok": False, "message": "Report body is too large."},
                    origin=origin,
                )
                return
            try:
                body = self.rfile.read(body_length)
            except (TimeoutError, OSError):
                context.store.record_rejection("request_timeout")
                self.close_connection = True
                with suppress(OSError):
                    self._write_json(
                        408,
                        {"ok": False, "message": "Request timed out."},
                        origin=origin,
                    )
                return
            if len(body) != body_length:
                context.store.record_rejection("truncated_body")
                self._write_json(
                    400,
                    {"ok": False, "message": "Request body is incomplete."},
                    origin=origin,
                )
                return
            try:
                report = parse_host_sizing_report(body)
            except HostSizingTransportError as exc:
                context.store.record_rejection("schema")
                self._write_json(
                    400,
                    {"ok": False, "message": str(exc)},
                    origin=origin,
                )
                return
            if not hmac.compare_digest(report.launch_id, context.launch_id):
                context.store.record_rejection("launch_id")
                self._write_json(
                    403,
                    {"ok": False, "message": "Forbidden."},
                    origin=origin,
                )
                return
            if context.expected_source_id is not None and not hmac.compare_digest(
                report.source_id,
                context.expected_source_id,
            ):
                context.store.record_rejection("source_id")
                self._write_json(
                    403,
                    {"ok": False, "message": "Forbidden."},
                    origin=origin,
                )
                return

            result = context.store.accept(report)
            if result.accepted and context.accepted_report_callback is not None:
                try:
                    context.accepted_report_callback(report)
                except Exception:
                    context.store.record_rejection("consumer")
            status = {
                HostSizingReportDecision.ACCEPTED: 202,
                HostSizingReportDecision.STALE: 409,
                HostSizingReportDecision.AUTHORITY_CONFLICT: 409,
                HostSizingReportDecision.RATE_LIMITED: 429,
                HostSizingReportDecision.CLOSED: 410,
            }[result.decision]
            self._write_json(
                status,
                {
                    "ok": result.accepted,
                    "decision": result.decision.value,
                    "message": result.message,
                },
                origin=origin,
            )

        def do_GET(self) -> None:  # noqa: N802 - HTTP handler contract.
            self._write_json(
                405,
                {"ok": False, "message": "Method not allowed."},
            )

        def _host_header_allowed(self) -> bool:
            # Defense-in-depth against DNS rebinding: only accept the literal
            # loopback host:port this endpoint is bound to, so a rebound name that
            # resolves to 127.0.0.1 cannot reach the endpoint even if a page
            # forges an allowed Origin.
            host_header = self.headers.get("Host", "")
            if not host_header:
                return False
            server_address = self.server.server_address
            if not isinstance(server_address, tuple) or len(server_address) < 2:
                return False
            server_host, server_port = server_address[0], server_address[1]
            return host_header in {f"{server_host}:{server_port}", str(server_host)}

        def _origin_allowed(self, origin: str) -> bool:
            return bool(origin) and hmac.compare_digest(
                origin,
                context.allowed_origin,
            )

        def _write_cors_headers(self, origin: str) -> None:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header(
                "Access-Control-Allow-Headers",
                f"Content-Type, {HOST_SIZING_TOKEN_HEADER}",
            )
            if (
                self.headers.get(
                    "Access-Control-Request-Private-Network",
                    "",
                ).lower()
                == "true"
            ):
                self.send_header("Access-Control-Allow-Private-Network", "true")

        def _write_json(
            self,
            status: int,
            payload: Mapping[str, object],
            *,
            origin: str | None = None,
        ) -> None:
            body = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(status)
            if origin is not None and self._origin_allowed(origin):
                self._write_cors_headers(origin)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return HostSizingHandler


def _parse_dimensions(
    value: object,
    *,
    name: str,
    width_optional: bool,
) -> SurfaceDimensions:
    dimensions = _require_object(value, name)
    required = {"height"}
    optional = {"width"} if width_optional else set()
    _require_keys(dimensions, required=required, optional=optional, name=name)
    height = _require_dimension(dimensions["height"], f"{name}.height")
    width_value = dimensions.get("width")
    width = (
        None
        if width_value is None
        else _require_dimension(width_value, f"{name}.width")
    )
    return SurfaceDimensions(height=height, width=width)


def _require_dimension(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HostSizingTransportError(f"{name} must be a number.")
    normalized = float(value)
    if (
        not math.isfinite(normalized)
        or normalized <= 0
        or normalized > HOST_SIZING_MAX_DIMENSION_CSS
    ):
        raise HostSizingTransportError(
            f"{name} must be finite and within the protocol dimension bounds."
        )
    return normalized


def _require_device_pixel_ratio(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HostSizingTransportError("device_pixel_ratio must be a number.")
    normalized = float(value)
    if (
        not math.isfinite(normalized)
        or normalized < HOST_SIZING_MIN_DEVICE_PIXEL_RATIO
        or normalized > HOST_SIZING_MAX_DEVICE_PIXEL_RATIO
    ):
        raise HostSizingTransportError(
            "device_pixel_ratio is outside the protocol bounds."
        )
    return normalized


def _require_identifier(value: object, *, name: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise HostSizingTransportError(f"{name} is invalid.")
    return value


def _require_object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise HostSizingTransportError(f"{name} must be a JSON object.")
    if not all(isinstance(key, str) for key in value):
        raise HostSizingTransportError(f"{name} keys must be strings.")
    return value


def _require_keys(
    value: Mapping[str, object],
    *,
    required: set[str],
    optional: set[str] | None = None,
    name: str,
) -> None:
    allowed = required | (optional or set())
    present = set(value)
    missing = required - present
    unexpected = present - allowed
    if missing:
        raise HostSizingTransportError(
            f"{name} is missing required fields: {', '.join(sorted(missing))}."
        )
    if unexpected:
        raise HostSizingTransportError(
            f"{name} contains unexpected fields: {', '.join(sorted(unexpected))}."
        )


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key.")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"Invalid JSON numeric constant: {value}")
