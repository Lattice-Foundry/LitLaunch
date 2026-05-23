"""Opt-in graceful shutdown support for LitLaunch apps."""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from litlaunch.exceptions import ConfigurationError

LITLAUNCH_SHUTDOWN_HOST = "LITLAUNCH_SHUTDOWN_HOST"
LITLAUNCH_SHUTDOWN_PORT = "LITLAUNCH_SHUTDOWN_PORT"
LITLAUNCH_SHUTDOWN_TOKEN = "LITLAUNCH_SHUTDOWN_TOKEN"
LITLAUNCH_SHUTDOWN_ENABLED = "LITLAUNCH_SHUTDOWN_ENABLED"

SHUTDOWN_TOKEN_HEADER = "X-LitLaunch-Token"
SHUTDOWN_ENDPOINT_PATH = "/shutdown"
DEFAULT_SHUTDOWN_HOST = "127.0.0.1"


class HookConsoleVisibility(str, Enum):
    """Console visibility for developer-defined shutdown hook messages."""

    NORMAL = "normal"
    VERBOSE = "verbose"


@dataclass(frozen=True)
class ShutdownHookStatus:
    """Optional status returned by a shutdown hook to customize console output."""

    message: str | None = None
    ok: bool = True
    color: str | None = None
    console_visibility: HookConsoleVisibility | str | None = None
    show_in_quiet: bool | None = None
    render: bool = True

    def __post_init__(self) -> None:
        if self.console_visibility is not None:
            object.__setattr__(
                self,
                "console_visibility",
                _normalize_hook_console_visibility(self.console_visibility),
            )


@dataclass(frozen=True)
class ShutdownHook:
    """A cleanup hook registered by a Streamlit app."""

    func: Callable[[], object]
    label: str
    success_message: str | None = None
    failure_message: str | None = None
    color: str | None = None
    console_visibility: HookConsoleVisibility | str = HookConsoleVisibility.NORMAL
    show_in_quiet: bool = False
    continue_on_error: bool = True

    def __post_init__(self) -> None:
        if not callable(self.func):
            raise ConfigurationError("Shutdown hook func must be callable.")
        if not self.label or not self.label.strip():
            raise ConfigurationError("Shutdown hook label cannot be empty.")
        object.__setattr__(
            self,
            "console_visibility",
            _normalize_hook_console_visibility(self.console_visibility),
        )


@dataclass(frozen=True)
class ShutdownHookResult:
    """Result from one shutdown hook."""

    label: str
    ok: bool
    message: str
    error: str | None = None
    color: str | None = None
    console_visibility: HookConsoleVisibility | str = HookConsoleVisibility.NORMAL
    show_in_quiet: bool = False
    render: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "console_visibility",
            _normalize_hook_console_visibility(self.console_visibility),
        )


@dataclass(frozen=True)
class ShutdownResult:
    """Result from running registered shutdown hooks."""

    ok: bool
    hook_results: tuple[ShutdownHookResult, ...]
    message: str


@dataclass(frozen=True)
class ShutdownConfig:
    """Shutdown endpoint configuration passed to the Streamlit subprocess."""

    host: str
    port: int
    token: str
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.host or not self.host.strip():
            raise ConfigurationError("Shutdown host cannot be empty.")
        object.__setattr__(self, "port", _validate_port(self.port))
        if not self.token or not self.token.strip():
            raise ConfigurationError("Shutdown token cannot be empty.")

    def as_env(self) -> dict[str, str]:
        """Return environment variables for a launched app process."""

        return {
            LITLAUNCH_SHUTDOWN_ENABLED: "1" if self.enabled else "0",
            LITLAUNCH_SHUTDOWN_HOST: self.host,
            LITLAUNCH_SHUTDOWN_PORT: str(self.port),
            LITLAUNCH_SHUTDOWN_TOKEN: self.token,
        }


@dataclass(frozen=True)
class ShutdownRequestResult:
    """Result from requesting graceful app shutdown."""

    ok: bool
    status_code: int | None
    message: str
    hook_results: tuple[ShutdownHookResult, ...] = ()


class ShutdownHookRegistry:
    """Register and run app cleanup hooks in deterministic order."""

    def __init__(self) -> None:
        self._hooks: list[ShutdownHook] = []

    @property
    def hooks(self) -> tuple[ShutdownHook, ...]:
        """Return registered hooks as an immutable tuple."""

        return tuple(self._hooks)

    def register(
        self,
        func: Callable[[], object],
        *,
        label: str,
        success_message: str | None = None,
        failure_message: str | None = None,
        color: str | None = None,
        console_visibility: HookConsoleVisibility | str = HookConsoleVisibility.NORMAL,
        show_in_quiet: bool = False,
        continue_on_error: bool = True,
    ) -> Callable[[], object]:
        """Register a shutdown hook and return the original function."""

        self._hooks.append(
            ShutdownHook(
                func=func,
                label=label,
                success_message=success_message,
                failure_message=failure_message,
                color=color,
                console_visibility=console_visibility,
                show_in_quiet=show_in_quiet,
                continue_on_error=continue_on_error,
            )
        )
        return func

    def hook(
        self,
        *,
        label: str,
        success_message: str | None = None,
        failure_message: str | None = None,
        color: str | None = None,
        console_visibility: HookConsoleVisibility | str = HookConsoleVisibility.NORMAL,
        show_in_quiet: bool = False,
        continue_on_error: bool = True,
    ) -> Callable[[Callable[[], object]], Callable[[], object]]:
        """Return a decorator that registers a shutdown hook."""

        def decorator(func: Callable[[], object]) -> Callable[[], object]:
            return self.register(
                func,
                label=label,
                success_message=success_message,
                failure_message=failure_message,
                color=color,
                console_visibility=console_visibility,
                show_in_quiet=show_in_quiet,
                continue_on_error=continue_on_error,
            )

        return decorator

    def run_all(self) -> ShutdownResult:
        """Run all registered hooks in registration order."""

        if not self._hooks:
            return ShutdownResult(
                ok=True,
                hook_results=(),
                message="No shutdown hooks registered.",
            )

        results: list[ShutdownHookResult] = []
        for hook in self._hooks:
            try:
                status = _normalize_hook_return(hook.func())
            except Exception as exc:
                results.append(
                    ShutdownHookResult(
                        label=hook.label,
                        ok=False,
                        message=hook.failure_message
                        or f"Shutdown hook failed: {hook.label}",
                        error=str(exc),
                        color=hook.color,
                        console_visibility=hook.console_visibility,
                        show_in_quiet=hook.show_in_quiet,
                    )
                )
                if not hook.continue_on_error:
                    break
            else:
                message = (
                    status.message
                    if status.message is not None
                    else (hook.success_message if status.ok else hook.failure_message)
                )
                if message is None:
                    message = (
                        f"Shutdown hook completed: {hook.label}"
                        if status.ok
                        else f"Shutdown hook failed: {hook.label}"
                    )
                results.append(
                    ShutdownHookResult(
                        label=hook.label,
                        ok=status.ok,
                        message=message,
                        color=status.color if status.color is not None else hook.color,
                        console_visibility=(
                            status.console_visibility
                            if status.console_visibility is not None
                            else hook.console_visibility
                        ),
                        show_in_quiet=(
                            status.show_in_quiet
                            if status.show_in_quiet is not None
                            else hook.show_in_quiet
                        ),
                        render=status.render,
                    )
                )
                if not status.ok and not hook.continue_on_error:
                    break

        ok = all(result.ok for result in results)
        return ShutdownResult(
            ok=ok,
            hook_results=tuple(results),
            message=(
                "Shutdown hooks completed."
                if ok
                else "One or more shutdown hooks failed."
            ),
        )


class LauncherRuntime:
    """App-side helper for LitLaunch graceful shutdown hooks."""

    def __init__(
        self,
        *,
        config: ShutdownConfig | None = None,
        registry: ShutdownHookRegistry | None = None,
    ) -> None:
        self.config = config
        self.registry = registry or ShutdownHookRegistry()
        self._shutdown_completion_callback: (
            Callable[[ShutdownResult], object] | None
        ) = None
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._shutdown_lock = threading.Lock()
        self._completion_lock = threading.Lock()
        self._shutdown_requested = False
        self._shutdown_result: ShutdownResult | None = None
        self._shutdown_completion_started = False
        self._shutdown_completion_error: str | None = None

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> LauncherRuntime:
        """Create app runtime state from LitLaunch-provided environment."""

        source = environ if environ is not None else os.environ
        if source.get(LITLAUNCH_SHUTDOWN_ENABLED) != "1":
            return cls()

        host = source.get(LITLAUNCH_SHUTDOWN_HOST, DEFAULT_SHUTDOWN_HOST)
        port_text = source.get(LITLAUNCH_SHUTDOWN_PORT)
        token = source.get(LITLAUNCH_SHUTDOWN_TOKEN)
        if not port_text or not token:
            return cls()

        try:
            port = _validate_port(port_text)
        except ConfigurationError:
            return cls()

        try:
            config = ShutdownConfig(host=host, port=port, token=token)
        except ConfigurationError:
            return cls()
        return cls(config=config)

    @property
    def available(self) -> bool:
        """Return whether this app was launched with shutdown endpoint settings."""

        return self.config is not None and self.config.enabled

    @property
    def shutdown_requested(self) -> bool:
        """Return whether the local endpoint accepted a shutdown request."""

        return self._shutdown_requested

    def _mark_shutdown_complete(self, result: ShutdownResult) -> None:
        """Store the completed shutdown result for idempotent endpoint replies."""

        self._shutdown_result = result

    def set_shutdown_completion_callback(
        self,
        callback: Callable[[ShutdownResult], object],
    ) -> Callable[[ShutdownResult], object]:
        """Register a callback to run after endpoint shutdown response is sent."""

        if not callable(callback):
            raise ConfigurationError("Shutdown completion callback must be callable.")
        self._shutdown_completion_callback = callback
        return callback

    def shutdown_hook(
        self,
        *,
        label: str,
        success_message: str | None = None,
        failure_message: str | None = None,
        color: str | None = None,
        console_visibility: HookConsoleVisibility | str = HookConsoleVisibility.NORMAL,
        show_in_quiet: bool = False,
        continue_on_error: bool = True,
    ) -> Callable[[Callable[[], object]], Callable[[], object]]:
        """Return a decorator for registering an app shutdown hook."""

        return self.registry.hook(
            label=label,
            success_message=success_message,
            failure_message=failure_message,
            color=color,
            console_visibility=console_visibility,
            show_in_quiet=show_in_quiet,
            continue_on_error=continue_on_error,
        )

    def register_shutdown_hook(
        self,
        func: Callable[[], object],
        **metadata: object,
    ) -> Callable[[], object]:
        """Register a shutdown hook."""

        return self.registry.register(func, **metadata)

    def run_shutdown_hooks(self) -> ShutdownResult:
        """Run registered shutdown hooks."""

        return self.registry.run_all()

    def _schedule_shutdown_completion(self, result: ShutdownResult) -> None:
        with self._completion_lock:
            if (
                self._shutdown_completion_callback is None
                or self._shutdown_completion_started
            ):
                return
            self._shutdown_completion_started = True

        thread = threading.Thread(
            target=self._run_shutdown_completion,
            args=(result,),
            daemon=True,
            name="litlaunch-shutdown-completion",
        )
        thread.start()

    def _run_shutdown_completion(self, result: ShutdownResult) -> None:
        callback = self._shutdown_completion_callback
        if callback is None:
            return
        try:
            callback(result)
        except Exception as exc:
            self._shutdown_completion_error = type(exc).__name__

    def enable_shutdown_endpoint(self) -> bool:
        """Start the loopback tokened shutdown endpoint when available."""

        if not self.available or self.config is None:
            return False
        if self._server is not None:
            return True
        if not _is_loopback_host(self.config.host):
            return False

        handler = _build_shutdown_handler(self)
        try:
            self._server = ThreadingHTTPServer(
                (self.config.host, self.config.port),
                handler,
            )
        except OSError:
            self._server = None
            return False

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="litlaunch-shutdown-endpoint",
        )
        self._thread.start()
        return True

    def close_shutdown_endpoint(self) -> None:
        """Stop the local shutdown endpoint if this runtime started one."""

        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None


class ShutdownClient:
    """Request graceful shutdown from a LitLaunch-enabled app process."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        token: str,
        opener: Callable[..., object] = urllib.request.urlopen,
        timeout_seconds: float = 2.0,
    ) -> None:
        if not host or not host.strip():
            raise ConfigurationError("Shutdown host cannot be empty.")
        self.host = host
        self.port = _validate_port(port)
        if not token or not token.strip():
            raise ConfigurationError("Shutdown token cannot be empty.")
        self.token = token
        self.opener = opener
        self.timeout_seconds = timeout_seconds

    def request_shutdown(self) -> ShutdownRequestResult:
        """POST to the app-side shutdown endpoint."""

        request = urllib.request.Request(
            f"http://{_format_host_for_url(self.host)}:{self.port}"
            f"{SHUTDOWN_ENDPOINT_PATH}",
            method="POST",
        )
        request.add_header(SHUTDOWN_TOKEN_HEADER, self.token)
        try:
            response = self.opener(request, timeout=self.timeout_seconds)
            status_code = getattr(response, "status", getattr(response, "code", None))
            payload = _read_shutdown_response_payload(response)
            if hasattr(response, "close"):
                response.close()
        except urllib.error.HTTPError as exc:
            payload = _read_shutdown_response_payload(exc)
            return ShutdownRequestResult(
                ok=False,
                status_code=exc.code,
                message=str(
                    payload.get(
                        "message",
                        f"Shutdown request failed with HTTP {exc.code}.",
                    )
                ),
                hook_results=_hook_results_from_payload(payload),
            )
        except Exception as exc:
            return ShutdownRequestResult(
                ok=False,
                status_code=None,
                message=f"Shutdown request failed: {exc}",
            )

        ok = 200 <= int(status_code or 0) < 300
        return ShutdownRequestResult(
            ok=ok,
            status_code=status_code,
            message=str(
                payload.get(
                    "message",
                    (
                        "Shutdown request accepted."
                        if ok
                        else f"Shutdown request failed with HTTP {status_code}."
                    ),
                )
            ),
            hook_results=_hook_results_from_payload(payload),
        )


def _build_shutdown_handler(runtime: LauncherRuntime) -> type[BaseHTTPRequestHandler]:
    class ShutdownHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path != SHUTDOWN_ENDPOINT_PATH:
                self._write_json(404, {"ok": False, "message": "Not found."})
                return
            if (
                runtime.config is None
                or self.headers.get(SHUTDOWN_TOKEN_HEADER) != runtime.config.token
            ):
                self._write_json(403, {"ok": False, "message": "Forbidden."})
                return

            with runtime._shutdown_lock:
                if runtime._shutdown_result is not None:
                    result = runtime._shutdown_result
                    self._write_json(
                        200 if result.ok else 500,
                        {
                            "ok": result.ok,
                            "message": "Shutdown already requested.",
                            "hook_results": tuple(
                                _hook_result_to_payload(item)
                                for item in result.hook_results
                            ),
                        },
                    )
                    return

                runtime._shutdown_requested = True
                result = runtime.run_shutdown_hooks()
                runtime._mark_shutdown_complete(result)
            self._write_json(
                200 if result.ok else 500,
                {
                    "ok": result.ok,
                    "message": result.message,
                    "hook_results": tuple(
                        _hook_result_to_payload(item) for item in result.hook_results
                    ),
                },
            )
            runtime._schedule_shutdown_completion(result)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _write_json(self, status_code: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()

    return ShutdownHandler


def _validate_port(port: int | str) -> int:
    if isinstance(port, bool):
        raise ConfigurationError("Shutdown port must be an integer.")
    try:
        value = int(port)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError("Shutdown port must be an integer.") from exc
    if value < 1 or value > 65535:
        raise ConfigurationError("Shutdown port must be from 1 to 65535.")
    return value


def _normalize_hook_console_visibility(
    value: HookConsoleVisibility | str,
) -> HookConsoleVisibility:
    if isinstance(value, HookConsoleVisibility):
        return value
    normalized = str(value).strip().lower()
    try:
        return HookConsoleVisibility(normalized)
    except ValueError as exc:
        raise ConfigurationError(
            "Shutdown hook console_visibility must be 'normal' or 'verbose'."
        ) from exc


def _hook_result_to_payload(result: ShutdownHookResult) -> dict[str, object]:
    return {
        "label": result.label,
        "ok": result.ok,
        "message": result.message,
        "error": None,
        "color": result.color,
        "console_visibility": result.console_visibility.value,
        "show_in_quiet": result.show_in_quiet,
        "render": result.render,
    }


def _hook_results_from_payload(
    payload: Mapping[str, object],
) -> tuple[ShutdownHookResult, ...]:
    raw_results = payload.get("hook_results")
    if not isinstance(raw_results, list | tuple):
        return ()
    results: list[ShutdownHookResult] = []
    for raw_item in raw_results:
        if not isinstance(raw_item, Mapping):
            continue
        try:
            results.append(
                ShutdownHookResult(
                    label=str(raw_item.get("label", "")),
                    ok=bool(raw_item.get("ok", False)),
                    message=str(raw_item.get("message", "")),
                    error=(
                        None
                        if raw_item.get("error") is None
                        else str(raw_item.get("error"))
                    ),
                    color=(
                        None
                        if raw_item.get("color") is None
                        else str(raw_item.get("color"))
                    ),
                    console_visibility=str(
                        raw_item.get(
                            "console_visibility",
                            HookConsoleVisibility.NORMAL.value,
                        )
                    ),
                    show_in_quiet=bool(raw_item.get("show_in_quiet", False)),
                    render=bool(raw_item.get("render", True)),
                )
            )
        except ConfigurationError:
            continue
    return tuple(results)


def _normalize_hook_return(value: object) -> ShutdownHookStatus:
    if isinstance(value, ShutdownHookStatus):
        return value
    if isinstance(value, ShutdownHookResult):
        return ShutdownHookStatus(
            message=value.message,
            ok=value.ok,
            color=value.color,
            console_visibility=value.console_visibility,
            show_in_quiet=value.show_in_quiet,
            render=value.render,
        )
    return ShutdownHookStatus()


def _read_shutdown_response_payload(response: object) -> dict[str, object]:
    read = getattr(response, "read", None)
    if not callable(read):
        return {}
    try:
        raw_body = read()
    except Exception:
        return {}
    if not raw_body:
        return {}
    if isinstance(raw_body, bytes):
        text = raw_body.decode("utf-8", errors="replace")
    else:
        text = str(raw_body)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _is_loopback_host(host: str) -> bool:
    return host in {"127.0.0.1", "::1", "localhost"}


def _format_host_for_url(host: str) -> str:
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host
