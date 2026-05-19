import json
import socket
import urllib.error
import urllib.request

import pytest

from litlaunch.colors import streamlit_blue
from litlaunch.exceptions import ConfigurationError
from litlaunch.shutdown import (
    LITLAUNCH_SHUTDOWN_ENABLED,
    LITLAUNCH_SHUTDOWN_HOST,
    LITLAUNCH_SHUTDOWN_PORT,
    LITLAUNCH_SHUTDOWN_TOKEN,
    SHUTDOWN_TOKEN_HEADER,
    LauncherRuntime,
    ShutdownClient,
    ShutdownConfig,
    ShutdownHook,
    ShutdownHookRegistry,
    _is_loopback_host,
)


def available_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_shutdown_hook_requires_callable():
    with pytest.raises(ConfigurationError, match="callable"):
        ShutdownHook(func="nope", label="Cleanup")


def test_shutdown_hook_requires_label():
    with pytest.raises(ConfigurationError, match="label"):
        ShutdownHook(func=lambda: None, label=" ")


def test_shutdown_hook_stores_metadata():
    def cleanup():
        return None

    hook = ShutdownHook(
        func=cleanup,
        label="Cleanup",
        success_message="Done",
        failure_message="Failed",
        color=streamlit_blue,
        continue_on_error=False,
    )

    assert hook.func is cleanup
    assert hook.label == "Cleanup"
    assert hook.success_message == "Done"
    assert hook.failure_message == "Failed"
    assert hook.color == streamlit_blue
    assert hook.continue_on_error is False


def test_shutdown_hook_accepts_unknown_custom_color_metadata():
    hook = ShutdownHook(
        func=lambda: None,
        label="Cleanup",
        color="project_custom_color",
    )

    assert hook.color == "project_custom_color"


def test_shutdown_registry_registers_and_runs_hooks_in_order():
    calls = []
    registry = ShutdownHookRegistry()

    registry.register(lambda: calls.append("one"), label="One")

    @registry.hook(label="Two", success_message="Two done", color="blue")
    def two():
        calls.append("two")

    result = registry.run_all()

    assert calls == ["one", "two"]
    assert result.ok is True
    assert [hook.label for hook in registry.hooks] == ["One", "Two"]
    assert [item.ok for item in result.hook_results] == [True, True]
    assert result.hook_results[1].message == "Two done"
    assert result.hook_results[1].color == "blue"


def test_shutdown_registry_continues_on_error_by_default():
    calls = []
    registry = ShutdownHookRegistry()

    def fail():
        calls.append("fail")
        raise RuntimeError("boom")

    registry.register(fail, label="Fail", failure_message="Failed")
    registry.register(lambda: calls.append("after"), label="After")

    result = registry.run_all()

    assert calls == ["fail", "after"]
    assert result.ok is False
    assert [item.ok for item in result.hook_results] == [False, True]
    assert result.hook_results[0].message == "Failed"
    assert result.hook_results[0].error == "boom"


def test_shutdown_registry_stops_when_continue_on_error_is_false():
    calls = []
    registry = ShutdownHookRegistry()

    def fail():
        calls.append("fail")
        raise RuntimeError("boom")

    registry.register(fail, label="Fail", continue_on_error=False)
    registry.register(lambda: calls.append("after"), label="After")

    result = registry.run_all()

    assert calls == ["fail"]
    assert result.ok is False
    assert len(result.hook_results) == 1


def test_launcher_runtime_from_env_unavailable_when_vars_missing():
    runtime = LauncherRuntime.from_env({})

    assert runtime.available is False
    assert runtime.enable_shutdown_endpoint() is False


def test_launcher_runtime_registration_works_when_unavailable():
    calls = []
    runtime = LauncherRuntime.from_env({})

    @runtime.shutdown_hook(label="Cleanup")
    def cleanup():
        calls.append("cleanup")

    result = runtime.run_shutdown_hooks()

    assert runtime.available is False
    assert calls == ["cleanup"]
    assert result.ok is True


def test_launcher_runtime_has_no_duplicate_on_shutdown_alias():
    runtime = LauncherRuntime.from_env({})

    assert not hasattr(runtime, "on_shutdown")


def test_launcher_runtime_available_when_env_vars_present():
    runtime = LauncherRuntime.from_env(
        {
            LITLAUNCH_SHUTDOWN_ENABLED: "1",
            LITLAUNCH_SHUTDOWN_HOST: "127.0.0.1",
            LITLAUNCH_SHUTDOWN_PORT: "9900",
            LITLAUNCH_SHUTDOWN_TOKEN: "secret-token",
        }
    )

    assert runtime.available is True
    assert runtime.config == ShutdownConfig(
        host="127.0.0.1",
        port=9900,
        token="secret-token",
    )


def test_shutdown_config_requires_valid_host_port_and_token():
    with pytest.raises(ConfigurationError, match="host"):
        ShutdownConfig(host=" ", port=9900, token="secret-token")
    with pytest.raises(ConfigurationError, match="port"):
        ShutdownConfig(host="127.0.0.1", port=0, token="secret-token")
    with pytest.raises(ConfigurationError, match="token"):
        ShutdownConfig(host="127.0.0.1", port=9900, token=" ")


def test_shutdown_endpoint_rejects_missing_and_wrong_token_and_path():
    port = available_port()
    runtime = LauncherRuntime(
        config=ShutdownConfig(host="127.0.0.1", port=port, token="secret-token")
    )
    assert runtime.enable_shutdown_endpoint() is True
    try:
        with pytest.raises(urllib.error.HTTPError) as missing:
            urllib.request.urlopen(
                urllib.request.Request(
                    f"http://127.0.0.1:{port}/shutdown",
                    method="POST",
                ),
                timeout=2.0,
            )
        assert missing.value.code == 403

        with pytest.raises(urllib.error.HTTPError) as wrong:
            urllib.request.urlopen(
                urllib.request.Request(
                    f"http://127.0.0.1:{port}/shutdown",
                    method="POST",
                    headers={SHUTDOWN_TOKEN_HEADER: "wrong"},
                ),
                timeout=2.0,
            )
        assert wrong.value.code == 403
        assert "secret-token" not in wrong.value.read().decode("utf-8")

        with pytest.raises(urllib.error.HTTPError) as wrong_path:
            urllib.request.urlopen(
                urllib.request.Request(
                    f"http://127.0.0.1:{port}/nope",
                    method="POST",
                    headers={SHUTDOWN_TOKEN_HEADER: "secret-token"},
                ),
                timeout=2.0,
            )
        assert wrong_path.value.code == 404
    finally:
        runtime.close_shutdown_endpoint()


def test_shutdown_endpoint_valid_post_runs_hooks_without_exposing_token():
    port = available_port()
    calls = []
    runtime = LauncherRuntime(
        config=ShutdownConfig(host="127.0.0.1", port=port, token="secret-token")
    )
    runtime.register_shutdown_hook(lambda: calls.append("cleanup"), label="Cleanup")
    assert runtime.enable_shutdown_endpoint() is True
    try:
        response = urllib.request.urlopen(
            urllib.request.Request(
                f"http://127.0.0.1:{port}/shutdown",
                method="POST",
                headers={SHUTDOWN_TOKEN_HEADER: "secret-token"},
            ),
            timeout=2.0,
        )
        body = response.read().decode("utf-8")
    finally:
        runtime.close_shutdown_endpoint()

    assert calls == ["cleanup"]
    assert runtime.shutdown_requested is True
    assert json.loads(body)["ok"] is True
    assert "secret-token" not in body


def test_shutdown_endpoint_duplicate_post_does_not_rerun_hooks():
    port = available_port()
    calls = []
    runtime = LauncherRuntime(
        config=ShutdownConfig(host="127.0.0.1", port=port, token="secret-token")
    )
    runtime.register_shutdown_hook(lambda: calls.append("cleanup"), label="Cleanup")
    assert runtime.enable_shutdown_endpoint() is True
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/shutdown",
            method="POST",
            headers={SHUTDOWN_TOKEN_HEADER: "secret-token"},
        )
        first = urllib.request.urlopen(request, timeout=2.0).read().decode("utf-8")
        second = urllib.request.urlopen(request, timeout=2.0).read().decode("utf-8")
    finally:
        runtime.close_shutdown_endpoint()

    assert calls == ["cleanup"]
    assert json.loads(first)["message"] == "Shutdown hooks completed."
    assert json.loads(second)["message"] == "Shutdown already requested."


def test_ipv6_loopback_is_accepted_for_endpoint_binding_attempt():
    assert _is_loopback_host("::1") is True

    runtime = LauncherRuntime(
        config=ShutdownConfig(host="::1", port=available_port(), token="secret-token")
    )

    # Availability of IPv6 binding varies by environment, but ::1 should pass
    # LitLaunch's loopback policy and either start or fail only at socket bind.
    assert runtime.enable_shutdown_endpoint() in {True, False}
    runtime.close_shutdown_endpoint()


class FakeResponse:
    status = 200

    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_shutdown_client_sends_post_with_token_header():
    calls = []
    response = FakeResponse()

    def opener(request, timeout):
        calls.append((request, timeout))
        return response

    client = ShutdownClient(
        host="127.0.0.1",
        port=9900,
        token="secret-token",
        opener=opener,
        timeout_seconds=1.5,
    )

    result = client.request_shutdown()

    request, timeout = calls[0]
    assert result.ok is True
    assert timeout == 1.5
    assert request.full_url == "http://127.0.0.1:9900/shutdown"
    assert request.get_method() == "POST"
    headers = {key.lower(): value for key, value in request.header_items()}
    assert headers[SHUTDOWN_TOKEN_HEADER.lower()] == "secret-token"
    assert response.closed is True


def test_shutdown_client_formats_ipv6_loopback_url_with_brackets():
    calls = []
    response = FakeResponse()

    def opener(request, timeout):
        calls.append((request, timeout))
        return response

    client = ShutdownClient(
        host="::1",
        port=9900,
        token="secret-token",
        opener=opener,
    )

    result = client.request_shutdown()

    request, _timeout = calls[0]
    assert result.ok is True
    assert request.full_url == "http://[::1]:9900/shutdown"


def test_shutdown_client_failure_message_does_not_include_token():
    def opener(request, timeout):
        raise RuntimeError("network down")

    client = ShutdownClient(
        host="127.0.0.1",
        port=9900,
        token="secret-token",
        opener=opener,
    )

    result = client.request_shutdown()

    assert result.ok is False
    assert result.status_code is None
    assert "secret-token" not in result.message
