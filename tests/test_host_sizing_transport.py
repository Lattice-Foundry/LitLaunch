from __future__ import annotations

import copy
import http.client
import json
import socket
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler
from io import StringIO
from pathlib import Path

import pytest

import litlaunch
import litlaunch._host_sizing_transport as transport_module
from litlaunch._host_sizing_transport import (
    HOST_SIZING_ENDPOINT_PATH,
    HOST_SIZING_MAX_BODY_BYTES,
    HOST_SIZING_TOKEN_HEADER,
    LITLAUNCH_HOST_SIZING_ENABLED,
    LITLAUNCH_HOST_SIZING_ENDPOINT,
    LITLAUNCH_HOST_SIZING_LAUNCH_ID,
    LITLAUNCH_HOST_SIZING_ORIGIN,
    LITLAUNCH_HOST_SIZING_PROTOCOL,
    LITLAUNCH_HOST_SIZING_SOURCE_ID,
    LITLAUNCH_HOST_SIZING_TOKEN,
    HostSizingReportDecision,
    HostSizingReportStore,
    HostSizingTransportError,
    normalize_allowed_origin,
    parse_host_sizing_report,
    start_host_sizing_channel,
)
from litlaunch.console import ConsoleMode, ConsoleRenderer
from litlaunch.lifecycle import LaunchResult, LaunchState
from litlaunch.process import ProcessManager
from litlaunch.redaction import format_env_preview
from litlaunch.session import RuntimeSession

ALLOWED_ORIGIN = "http://127.0.0.1:8501"


@pytest.fixture
def channel():
    value = start_host_sizing_channel(allowed_origin=ALLOWED_ORIGIN)
    try:
        yield value
    finally:
        value.close()


def report_payload(
    channel,
    *,
    source_id="primary-surface",
    sequence=1,
    launch_id=None,
):
    return {
        "protocol": 1,
        "launch_id": launch_id or channel.config.launch_id,
        "source_id": source_id,
        "sequence": sequence,
        "device_pixel_ratio": 1.0,
        "content": {"height": 742, "width": 1180},
        "host_viewport": {"height": 812, "width": 1280},
        "desired_host_viewport": {"height": 790},
    }


def send_report(
    channel,
    payload,
    *,
    token=None,
    origin=ALLOWED_ORIGIN,
    content_type="application/json",
    path=HOST_SIZING_ENDPOINT_PATH,
):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{channel.config.port}{path}",
        data=body,
        method="POST",
        headers={
            "Origin": origin,
            HOST_SIZING_TOKEN_HEADER: token or channel.config.token,
            "Content-Type": content_type,
        },
    )
    return open_request(request)


def open_request(request):
    try:
        response = urllib.request.urlopen(request, timeout=2.0)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        headers = exc.headers
        status = exc.code
        exc.close()
    else:
        body = response.read()
        headers = response.headers
        status = response.status
        response.close()
    payload = json.loads(body) if body else None
    return status, payload, headers


def test_channel_binds_literal_loopback_with_private_environment(channel):
    config = channel.config
    env = config.as_env()

    assert config.host == "127.0.0.1"
    assert 1 <= config.port <= 65535
    assert config.endpoint == (
        f"http://127.0.0.1:{config.port}{HOST_SIZING_ENDPOINT_PATH}"
    )
    assert env == {
        LITLAUNCH_HOST_SIZING_ENABLED: "1",
        LITLAUNCH_HOST_SIZING_ENDPOINT: config.endpoint,
        LITLAUNCH_HOST_SIZING_TOKEN: config.token,
        LITLAUNCH_HOST_SIZING_LAUNCH_ID: config.launch_id,
        LITLAUNCH_HOST_SIZING_ORIGIN: ALLOWED_ORIGIN,
        LITLAUNCH_HOST_SIZING_PROTOCOL: "1",
    }
    assert config.token not in config.endpoint
    assert config.token not in repr(config)


def test_channel_registers_token_redaction_and_env_preview_is_safe():
    stream = StringIO()
    renderer = ConsoleRenderer(mode=ConsoleMode.VERBOSE, stream=stream)
    channel = start_host_sizing_channel(
        allowed_origin=ALLOWED_ORIGIN,
        console_renderer=renderer,
        token="private-host-sizing-token-value-123456",
    )
    try:
        renderer.detail(f"token={channel.config.token}")
        preview = format_env_preview(channel.config.as_env())
    finally:
        channel.close()

    assert channel.config.token not in stream.getvalue()
    assert channel.config.token not in preview
    assert f"{LITLAUNCH_HOST_SIZING_TOKEN}=<redacted>" in preview


@pytest.mark.parametrize(
    "origin",
    [
        "http://0.0.0.0:8501",
        "http://192.168.1.10:8501",
        "https://example.com:8501",
        "http://127.0.0.1",
        "http://127.0.0.1:8501/app",
        "ftp://127.0.0.1:8501",
        "http://user:pass@127.0.0.1:8501",
    ],
)
def test_channel_rejects_non_exact_or_non_loopback_origin_configuration(origin):
    with pytest.raises(HostSizingTransportError):
        start_host_sizing_channel(allowed_origin=origin)


def test_channel_rejects_nonliteral_bind_host():
    with pytest.raises(HostSizingTransportError, match="literal"):
        start_host_sizing_channel(
            allowed_origin=ALLOWED_ORIGIN,
            host="localhost",
        )


@pytest.mark.parametrize(
    ("origin", "normalized"),
    [
        ("http://localhost:8501", "http://localhost:8501"),
        ("http://127.0.0.2:8501", "http://127.0.0.2:8501"),
        ("http://[::1]:8501", "http://[::1]:8501"),
    ],
)
def test_allowed_origin_accepts_exact_loopback_forms(origin, normalized):
    assert normalize_allowed_origin(origin) == normalized


def test_request_server_refuses_workers_beyond_its_hard_bound():
    entered = threading.Event()
    release = threading.Event()
    active = 0
    peak = 0
    lock = threading.Lock()

    class BlockingHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - HTTP handler contract.
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            entered.set()
            release.wait(2.0)
            with lock:
                active -= 1
            self.send_response(204)
            self.end_headers()

        def log_message(self, format, *args):
            return

    server = transport_module._BoundedThreadingHTTPServer(
        ("127.0.0.1", 0),
        BlockingHandler,
        max_workers=1,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    first = socket.create_connection(server.server_address, timeout=1.0)
    second = None
    try:
        first.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
        assert entered.wait(1.0)
        second = socket.create_connection(server.server_address, timeout=1.0)
        second.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
        second.settimeout(1.0)
        try:
            refused = second.recv(1)
        except ConnectionResetError:
            refused = b""
        assert refused == b""
        assert peak == 1
    finally:
        release.set()
        first.close()
        if second is not None:
            second.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def test_incomplete_request_body_times_out_without_retaining_a_worker(channel):
    client = socket.create_connection(
        ("127.0.0.1", channel.config.port),
        timeout=1.0,
    )
    client.settimeout(4.0)
    try:
        request = (
            "POST /host-sizing/report HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            f"Origin: {ALLOWED_ORIGIN}\r\n"
            f"{HOST_SIZING_TOKEN_HEADER}: {channel.config.token}\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: 20\r\n\r\n"
            "{"
        ).encode()
        client.sendall(request)
        response = client.recv(4096)
    finally:
        client.close()

    assert b"408 Request Timeout" in response
    assert channel.snapshot().rejection_counts["request_timeout"] == 1


def test_channel_bind_failure_leaves_no_endpoint_thread():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    before = {
        thread.ident
        for thread in __import__("threading").enumerate()
        if thread.name == "litlaunch-host-sizing-endpoint"
    }
    try:
        with pytest.raises(HostSizingTransportError, match="Could not bind"):
            start_host_sizing_channel(
                allowed_origin=ALLOWED_ORIGIN,
                port=port,
            )
    finally:
        listener.close()
    after = {
        thread.ident
        for thread in __import__("threading").enumerate()
        if thread.name == "litlaunch-host-sizing-endpoint"
    }

    assert after == before


def test_valid_report_is_accepted_and_only_latest_is_retained(channel):
    status, body, headers = send_report(channel, report_payload(channel))

    assert status == 202
    assert body == {
        "decision": "accepted",
        "message": "Host-sizing report accepted.",
        "ok": True,
    }
    assert headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
    assert headers["Cache-Control"] == "no-store"

    second = report_payload(channel, sequence=2)
    second["desired_host_viewport"]["height"] = 820
    assert send_report(channel, second)[0] == 202

    snapshot = channel.snapshot()
    assert snapshot.active is True
    assert snapshot.bound_source_id == "primary-surface"
    assert snapshot.last_sequence == 2
    assert snapshot.accepted_count == 2
    assert snapshot.latest_report is not None
    assert snapshot.latest_report.desired_host_viewport.height == 820


def test_only_accepted_typed_reports_reach_the_consumer_callback():
    accepted = []
    channel = start_host_sizing_channel(
        allowed_origin=ALLOWED_ORIGIN,
        accepted_report_callback=accepted.append,
    )
    try:
        valid = report_payload(channel, sequence=5)

        assert send_report(channel, valid)[0] == 202
        assert send_report(channel, valid)[0] == 409
        assert send_report(channel, valid, token="x" * 40)[0] == 403
        invalid = report_payload(channel, sequence=6)
        invalid["device_pixel_ratio"] = 0
        assert send_report(channel, invalid)[0] == 400
    finally:
        channel.close()

    assert len(accepted) == 1
    assert accepted[0] == channel.snapshot().latest_report
    assert accepted[0].sequence == 5
    assert accepted[0].device_pixel_ratio == 1.0


def test_channel_enforces_configured_source_before_store_binding():
    channel = start_host_sizing_channel(
        allowed_origin=ALLOWED_ORIGIN,
        expected_source_id="primary-surface",
    )
    try:
        rejected = send_report(
            channel,
            report_payload(channel, source_id="secondary-surface"),
        )
        accepted_response = send_report(channel, report_payload(channel, sequence=2))
        snapshot = channel.snapshot()
    finally:
        channel.close()

    assert rejected[0] == 403
    assert accepted_response[0] == 202
    assert snapshot.bound_source_id == "primary-surface"
    assert snapshot.rejection_counts["source_id"] == 1
    assert LITLAUNCH_HOST_SIZING_SOURCE_ID not in channel.config.as_env()


def test_consumer_failure_is_contained_by_transport_boundary():
    def reject_consumer(_report):
        raise RuntimeError("private consumer failed")

    channel = start_host_sizing_channel(
        allowed_origin=ALLOWED_ORIGIN,
        accepted_report_callback=reject_consumer,
    )
    try:
        status, body, _headers = send_report(channel, report_payload(channel))
        snapshot = channel.snapshot()
    finally:
        channel.close()

    assert status == 202
    assert body["decision"] == "accepted"
    assert snapshot.accepted_count == 1
    assert snapshot.rejection_counts["consumer"] == 1


def test_preflight_allows_only_exact_origin_post_and_bounded_headers(channel):
    request = urllib.request.Request(
        channel.config.endpoint,
        method="OPTIONS",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": (
                f"Content-Type, {HOST_SIZING_TOKEN_HEADER}"
            ),
            "Access-Control-Request-Private-Network": "true",
        },
    )

    status, body, headers = open_request(request)

    assert status == 204
    assert body is None
    assert headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
    assert headers["Access-Control-Allow-Methods"] == "POST, OPTIONS"
    assert HOST_SIZING_TOKEN_HEADER in headers["Access-Control-Allow-Headers"]
    assert headers["Access-Control-Allow-Private-Network"] == "true"
    assert headers["Vary"] == "Origin"


def test_preflight_rejects_wrong_origin_method_and_headers(channel):
    wrong_origin = urllib.request.Request(
        channel.config.endpoint,
        method="OPTIONS",
        headers={
            "Origin": "http://localhost:8501",
            "Access-Control-Request-Method": "POST",
        },
    )
    wrong_method = urllib.request.Request(
        channel.config.endpoint,
        method="OPTIONS",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "DELETE",
        },
    )
    wrong_headers = urllib.request.Request(
        channel.config.endpoint,
        method="OPTIONS",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-Unsafe-Header",
        },
    )

    origin_status, _, origin_headers = open_request(wrong_origin)
    method_status, _, _ = open_request(wrong_method)
    headers_status, _, _ = open_request(wrong_headers)

    assert origin_status == 403
    assert "Access-Control-Allow-Origin" not in origin_headers
    assert method_status == 405
    assert headers_status == 400


def test_report_requires_exact_origin_token_and_launch_id(channel):
    payload = report_payload(channel)
    wrong_origin = send_report(
        channel,
        payload,
        origin="http://localhost:8501",
    )
    wrong_token = send_report(channel, payload, token="x" * 40)
    wrong_launch = send_report(
        channel,
        report_payload(channel, launch_id="other-launch-id-123456789"),
    )

    assert wrong_origin[0] == 403
    assert "Access-Control-Allow-Origin" not in wrong_origin[2]
    assert wrong_token[0] == 403
    assert wrong_token[2]["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
    assert wrong_launch[0] == 403
    rendered = json.dumps((wrong_origin[1], wrong_token[1], wrong_launch[1]))
    assert channel.config.token not in rendered
    assert channel.snapshot().latest_report is None


def test_report_requires_json_and_enforces_body_limit(channel):
    wrong_type = send_report(
        channel,
        report_payload(channel),
        content_type="text/plain",
    )
    too_large = send_report(
        channel,
        b"{" + b"x" * HOST_SIZING_MAX_BODY_BYTES,
    )

    assert wrong_type[0] == 415
    assert too_large[0] == 413
    assert channel.snapshot().latest_report is None


def test_report_requires_content_length(channel):
    connection = http.client.HTTPConnection(
        "127.0.0.1",
        channel.config.port,
        timeout=2.0,
    )
    connection.putrequest("POST", HOST_SIZING_ENDPOINT_PATH)
    connection.putheader("Origin", ALLOWED_ORIGIN)
    connection.putheader(HOST_SIZING_TOKEN_HEADER, channel.config.token)
    connection.putheader("Content-Type", "application/json")
    connection.endheaders()
    response = connection.getresponse()
    body = json.loads(response.read())
    connection.close()

    assert response.status == 411
    assert body["ok"] is False


def test_unknown_path_and_get_are_not_accepted(channel):
    wrong_path = send_report(
        channel,
        report_payload(channel),
        path="/other",
    )
    get_request = urllib.request.Request(channel.config.endpoint, method="GET")

    get_status, _, _ = open_request(get_request)

    assert wrong_path[0] == 404
    assert get_status == 405
    assert channel.snapshot().latest_report is None


def test_valid_protocol_report_parses_to_frozen_values(channel):
    payload = json.dumps(report_payload(channel)).encode()

    report = parse_host_sizing_report(payload)

    assert report.protocol == 1
    assert report.sequence == 1
    assert report.device_pixel_ratio == 1.0
    assert report.content.height == 742
    assert report.content.width == 1180
    assert report.host_viewport.height == 812
    assert report.desired_host_viewport.height == 790
    assert report.desired_host_viewport.width is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(protocol=2),
        lambda value: value.update(sequence=0),
        lambda value: value.update(sequence=True),
        lambda value: value.update(source_id="bad source"),
        lambda value: value.update(device_pixel_ratio=0.49),
        lambda value: value.update(device_pixel_ratio=8.01),
        lambda value: value.update(device_pixel_ratio=True),
        lambda value: value["content"].update(height=0),
        lambda value: value["host_viewport"].update(height=-1),
        lambda value: value["desired_host_viewport"].update(height=20000),
        lambda value: value.update(extra="field"),
        lambda value: value["content"].update(extra="field"),
        lambda value: value.pop("desired_host_viewport"),
    ],
)
def test_strict_schema_rejects_invalid_values(channel, mutate):
    payload = copy.deepcopy(report_payload(channel))
    mutate(payload)

    status, body, _ = send_report(channel, payload)

    assert status == 400
    assert body["ok"] is False
    assert channel.snapshot().latest_report is None


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        b'{"protocol":1,"protocol":1}',
        b'{"protocol":NaN}',
        b"\xff",
        b"[]",
    ],
)
def test_strict_json_rejects_malformed_duplicate_nonfinite_and_nonobject(
    channel,
    payload,
):
    status, _, _ = send_report(channel, payload)

    assert status == 400
    assert channel.snapshot().latest_report is None


def test_stale_sequence_and_second_source_fail_closed(channel):
    assert send_report(channel, report_payload(channel, sequence=5))[0] == 202

    duplicate = send_report(channel, report_payload(channel, sequence=5))
    older = send_report(channel, report_payload(channel, sequence=4))
    conflict = send_report(
        channel,
        report_payload(channel, source_id="second-surface", sequence=6),
    )

    assert duplicate[0] == 409
    assert duplicate[1]["decision"] == "stale"
    assert older[0] == 409
    assert conflict[0] == 409
    assert conflict[1]["decision"] == "authority_conflict"
    snapshot = channel.snapshot()
    assert snapshot.last_sequence == 5
    assert snapshot.bound_source_id == "primary-surface"
    assert snapshot.accepted_count == 1


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def monotonic(self):
        return self.value


def test_report_store_rate_limit_is_bounded_and_recovers():
    clock = FakeClock()
    store = HostSizingReportStore(
        clock=clock,
        max_reports_per_window=2,
        rate_window_seconds=1.0,
        max_accepted_reports=10,
    )
    base = parse_host_sizing_report(
        json.dumps(
            {
                "protocol": 1,
                "launch_id": "launch-id-1234567890",
                "source_id": "primary-surface",
                "sequence": 1,
                "device_pixel_ratio": 1.0,
                "content": {"height": 742},
                "host_viewport": {"height": 812},
                "desired_host_viewport": {"height": 790},
            }
        ).encode()
    )

    assert store.accept(base).accepted is True
    assert store.accept(copy_report(base, sequence=2)).accepted is True
    limited = store.accept(copy_report(base, sequence=3))
    clock.value = 1.1
    recovered = store.accept(copy_report(base, sequence=3))

    assert limited.decision == HostSizingReportDecision.RATE_LIMITED
    assert recovered.decision == HostSizingReportDecision.ACCEPTED
    assert store.snapshot().accepted_count == 3


def copy_report(report, *, sequence):
    return type(report)(
        protocol=report.protocol,
        launch_id=report.launch_id,
        source_id=report.source_id,
        sequence=sequence,
        device_pixel_ratio=report.device_pixel_ratio,
        content=report.content,
        host_viewport=report.host_viewport,
        desired_host_viewport=report.desired_host_viewport,
    )


def test_concurrent_reports_leave_monotonic_latest_state(channel):
    def submit(sequence):
        return send_report(channel, report_payload(channel, sequence=sequence))[0]

    with ThreadPoolExecutor(max_workers=10) as executor:
        statuses = tuple(executor.map(submit, range(1, 11)))

    snapshot = channel.snapshot()
    assert set(statuses).issubset({202, 409})
    assert 202 in statuses
    assert snapshot.last_sequence == 10
    assert snapshot.latest_report is not None
    assert snapshot.latest_report.sequence == 10


def test_close_is_idempotent_retains_snapshot_and_refuses_direct_accept(channel):
    assert send_report(channel, report_payload(channel))[0] == 202
    retained = channel.snapshot().latest_report

    channel.close()
    channel.close()
    direct = channel.store.accept(retained)

    assert channel.active is False
    assert channel.snapshot().active is False
    assert channel.snapshot().latest_report == retained
    assert direct.decision == HostSizingReportDecision.CLOSED


def test_runtime_session_cleanup_callback_closes_channel(channel):
    session = RuntimeSession(
        result=LaunchResult(
            ok=False,
            state=LaunchState.FAILED,
            command=None,
            pid=None,
            url=None,
            message="not started",
            events=(),
        ),
        process=None,
        process_manager=ProcessManager(),
        cleanup_callbacks=(channel.close,),
    )

    session.stop()

    assert channel.active is False
    assert channel.snapshot().active is False


def test_private_transport_has_no_public_export_or_native_mutation_dependency():
    source = Path(transport_module.__file__).read_text(encoding="utf-8")

    assert not hasattr(litlaunch, "HostSizingChannel")
    assert not hasattr(litlaunch, "start_host_sizing_channel")
    assert "_host_sizing_geometry" not in source
    assert "WindowsGeometryBackend" not in source
    assert "SetWindowPos" not in source
    assert "WindowSizer" not in source
