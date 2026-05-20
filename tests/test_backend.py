from dataclasses import FrozenInstanceError

from litlaunch.backend import (
    BackendCommand,
    BackendCommandContext,
    StreamlitBackendCommandProvider,
)
from litlaunch.config import LauncherConfig
from litlaunch.exceptions import CommandBuildError


def test_backend_command_normalizes_sequence_to_tuple():
    command = BackendCommand(["python", "-m", "streamlit", 123])

    assert command.command == ("python", "-m", "streamlit", "123")
    assert command.description == "backend"
    assert command.backend_kind is None


def test_backend_command_rejects_plain_string_or_bytes_command():
    for value in ("python -m streamlit", b"python"):
        try:
            BackendCommand(value)
        except CommandBuildError as exc:
            assert "sequence of strings" in str(exc)
        else:
            raise AssertionError("expected command validation failure")


def test_backend_command_rejects_empty_command_and_empty_arguments():
    for value in ((), ("python", "")):
        try:
            BackendCommand(value)
        except CommandBuildError as exc:
            assert "empty" in str(exc)
        else:
            raise AssertionError("expected command validation failure")


def test_backend_command_rejects_empty_description():
    try:
        BackendCommand(("python",), description=" ")
    except CommandBuildError as exc:
        assert "description cannot be empty" in str(exc)
    else:
        raise AssertionError("expected description validation failure")


def test_backend_command_context_is_frozen():
    context = BackendCommandContext(
        config=LauncherConfig(app_path="app.py"),
        host="127.0.0.1",
        port=8501,
        app_url="http://127.0.0.1:8501",
        health_url="http://127.0.0.1:8501/_stcore/health",
        headless=False,
    )

    try:
        context.port = 8502
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("expected backend command context to be frozen")


def test_default_streamlit_provider_uses_resolved_port():
    config = LauncherConfig(app_path="app.py")
    context = BackendCommandContext(
        config=config,
        host="127.0.0.1",
        port=8600,
        app_url="http://127.0.0.1:8600",
        health_url="http://127.0.0.1:8600/_stcore/health",
        headless=False,
    )

    backend_command = StreamlitBackendCommandProvider().build_backend_command(context)

    assert backend_command.description == "Streamlit backend"
    assert backend_command.backend_kind == "streamlit"
    assert backend_command.command[1:4] == ("-m", "streamlit", "run")
    assert (
        backend_command.command[backend_command.command.index("--server.port") + 1]
        == "8600"
    )
