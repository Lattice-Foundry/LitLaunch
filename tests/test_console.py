from io import StringIO

from litlaunch.console import (
    ANSI_COLORS,
    ConsoleMode,
    ConsoleRenderer,
    ConsoleTheme,
    strip_ansi,
)
from litlaunch.lifecycle import LaunchEvent, LaunchState
from litlaunch.shutdown import ShutdownHookResult


def test_console_theme_defaults_include_streamlit_blue():
    theme = ConsoleTheme(use_color=False)

    assert theme.primary == "streamlit_blue"
    assert theme.accent == "indigo"
    assert ANSI_COLORS["streamlit_blue"]
    assert theme.use_color is False


def test_console_theme_accepts_custom_accent():
    theme = ConsoleTheme(accent="cyan", use_color=False)

    assert theme.accent == "cyan"


def test_console_theme_default_honors_no_color_env(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")

    assert ConsoleTheme().use_color is False


def test_console_renderer_header_and_step_output_without_color():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )

    renderer.header("LitLaunch", "Example / browser")
    renderer.step("Starting backend")

    output = stream.getvalue()
    assert "LitLaunch" in output
    assert "Example / browser" in output
    assert "> Starting backend" in output
    assert "\033[" not in output


def test_console_renderer_status_methods_use_injected_stream():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )

    renderer.success("Ready")
    renderer.warning("Careful")
    renderer.error("Failed")
    renderer.info("Plain")
    renderer.blank()

    output = stream.getvalue()
    assert "ok Ready" in output
    assert "warn Careful" in output
    assert "error Failed" in output
    assert "Plain" in output


def test_console_renderer_quiet_suppresses_normal_output_but_not_errors():
    stream = StringIO()
    renderer = ConsoleRenderer(
        mode=ConsoleMode.QUIET,
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )

    renderer.header("LitLaunch")
    renderer.step("Starting")
    renderer.success("Ready")
    renderer.info("Info")
    renderer.warning("Warning")
    renderer.error("Failure")

    output = stream.getvalue()
    assert "Starting" not in output
    assert "Ready" not in output
    assert "Info" not in output
    assert "warn Warning" in output
    assert "error Failure" in output


def test_console_renderer_verbose_includes_detail_messages():
    stream = StringIO()
    renderer = ConsoleRenderer(
        mode="verbose",
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )

    renderer.detail("Command: python -m streamlit")

    assert "- Command: python -m streamlit" in stream.getvalue()


def test_console_renderer_normal_suppresses_detail_messages():
    stream = StringIO()
    renderer = ConsoleRenderer(
        mode="normal",
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )

    renderer.detail("Command: python -m streamlit")

    assert stream.getvalue() == ""


def test_console_renderer_can_emit_ansi_and_strip_it():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=True),
        stream=stream,
        env={},
    )

    renderer.header("LitLaunch")

    output = stream.getvalue()
    assert "\033[" in output
    assert strip_ansi(output).strip() == "LitLaunch"


def test_console_renderer_lifecycle_event_rendering():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )

    renderer.render_launch_event(LaunchEvent(LaunchState.HEALTHY, "Healthy", 1.0))
    renderer.render_launch_event(LaunchEvent(LaunchState.FAILED, "Failed", 2.0))

    output = stream.getvalue()
    assert "ok Healthy" in output
    assert "error Failed" in output


def test_console_renderer_shutdown_hook_metadata_rendering_is_internal():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )

    assert not hasattr(renderer, "render_shutdown_hook_start")
    assert not hasattr(renderer, "render_shutdown_hook_result")

    renderer._render_shutdown_hook_start("Closing resources", color="cyan")
    renderer._render_shutdown_hook_result(
        ShutdownHookResult(
            label="Closing resources",
            ok=True,
            message="Resources closed",
            color="cyan",
        )
    )
    renderer._render_shutdown_hook_result(
        ShutdownHookResult(
            label="Closing resources",
            ok=False,
            message="Resource close failed",
            error="boom",
            color="red",
        )
    )

    output = stream.getvalue()
    assert "Shutdown hook: Closing resources" in output
    assert "ok Resources closed" in output
    assert "error Resource close failed" in output


def test_console_renderer_redacts_registered_values():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=False),
        stream=stream,
        redacted_values=("secret-token",),
    )

    renderer.error("Token secret-token leaked")

    output = stream.getvalue()
    assert "secret-token" not in output
    assert "[redacted]" in output
