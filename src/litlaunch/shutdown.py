"""Opt-in graceful shutdown support for LitLaunch apps."""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from litlaunch.exceptions import ConfigurationError

LITLAUNCH_SHUTDOWN_HOST = "LITLAUNCH_SHUTDOWN_HOST"
LITLAUNCH_SHUTDOWN_PORT = "LITLAUNCH_SHUTDOWN_PORT"
LITLAUNCH_SHUTDOWN_TOKEN = "LITLAUNCH_SHUTDOWN_TOKEN"
LITLAUNCH_SHUTDOWN_ENABLED = "LITLAUNCH_SHUTDOWN_ENABLED"

SHUTDOWN_TOKEN_HEADER = "X-LitLaunch-Token"
SHUTDOWN_ENDPOINT_PATH = "/shutdown"
DEFAULT_SHUTDOWN_HOST = "127.0.0.1"


@dataclass(frozen=True)
class ShutdownHook:
    """A cleanup hook registered by a Streamlit app."""

    func: Callable[[], object]
    label: str
    success_message: str | None = None
    failure_message: str | None = None
    color: str | None = None
    continue_on_error: bool = True

    def __post_init__(self) -> None:
        if not callable(self.func):
            raise ConfigurationError("Shutdown hook func must be callable.")
        if not self.label or not self.label.strip():
            raise ConfigurationError("Shutdown hook label cannot be empty.")


@dataclass(frozen=True)
class ShutdownHookResult:
    """Result from one shutdown hook."""

    label: str
    ok: bool
    message: str
    error: str | None = None
    color: str | None = None


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
                hook.func()
            except Exception as exc:
                results.append(
                    ShutdownHookResult(
                        label=hook.label,
                        ok=False,
                        message=hook.failure_message
                        or f"Shutdown hook failed: {hook.label}",
                        error=str(exc),
                        color=hook.color,
                    )
                )
                if not hook.continue_on_error:
                    break
            else:
                results.append(
                    ShutdownHookResult(
                        label=hook.label,
                        ok=True,
                        message=hook.success_message
                        or f"Shutdown hook completed: {hook.label}",
                        color=hook.color,
                    )
                )

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
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._shutdown_requested = False

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

    def shutdown_hook(
        self,
        *,
        label: str,
        success_message: str | None = None,
        failure_message: str | None = None,
        color: str | None = None,
        continue_on_error: bool = True,
    ) -> Callable[[Callable[[], object]], Callable[[], object]]:
        """Return a decorator for registering an app shutdown hook."""

        return self.registry.hook(
            label=label,
            success_message=success_message,
            failure_message=failure_message,
            color=color,
            continue_on_error=continue_on_error,
        )

    def on_shutdown(
        self,
        func: Callable[[], object],
        **metadata: object,
    ) -> Callable[[], object]:
        """Register a shutdown hook."""

        return self.register_shutdown_hook(func, **metadata)

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
            f"http://{self.host}:{self.port}{SHUTDOWN_ENDPOINT_PATH}",
            method="POST",
        )
        request.add_header(SHUTDOWN_TOKEN_HEADER, self.token)
        try:
            response = self.opener(request, timeout=self.timeout_seconds)
            status_code = getattr(response, "status", getattr(response, "code", None))
            if hasattr(response, "close"):
                response.close()
        except urllib.error.HTTPError as exc:
            return ShutdownRequestResult(
                ok=False,
                status_code=exc.code,
                message=f"Shutdown request failed with HTTP {exc.code}.",
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
            message=(
                "Shutdown request accepted."
                if ok
                else f"Shutdown request failed with HTTP {status_code}."
            ),
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

            runtime._shutdown_requested = True
            result = runtime.run_shutdown_hooks()
            self._write_json(
                200 if result.ok else 500,
                {"ok": result.ok, "message": result.message},
            )

        def log_message(self, format: str, *args: object) -> None:
            return

        def _write_json(self, status_code: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

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


def _is_loopback_host(host: str) -> bool:
    return host in {"127.0.0.1", "localhost"}
