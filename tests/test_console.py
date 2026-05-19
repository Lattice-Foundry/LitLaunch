from io import StringIO

from litlaunch.browsers import BrowserCapability, BrowserKind, BrowserResolution
from litlaunch.colors import (
    THEME_COLORS,
    is_hex_color,
    muted_amber,
    muted_gray,
    powershell_red,
    streamlit_blue,
    streamlit_blue_light,
    success_green,
    terminal_green,
)
from litlaunch.config import BrowserChoice
from litlaunch.console import (
    ANSI_COLORS,
    ConsoleMode,
    ConsolePhase,
    ConsoleRenderer,
    ConsoleTheme,
    format_elapsed,
    strip_ansi,
)
from litlaunch.lifecycle import LaunchEvent, LaunchState
from litlaunch.shutdown import ShutdownHookResult
from litlaunch.windowing import WindowMonitorResult, WindowMonitorStatus


def test_named_theme_colors_exist_and_are_hex():
    expected_names = {
        streamlit_blue,
        streamlit_blue_light,
        terminal_green,
        powershell_red,
        muted_amber,
        muted_gray,
        success_green,
    }

    assert expected_names <= set(THEME_COLORS)
    for color in THEME_COLORS.values():
        assert is_hex_color(color.hex)


def test_console_theme_defaults_use_litlaunch_color_roles():
    theme = ConsoleTheme(use_color=False)

    assert theme.prefix == "[LitLaunch]"
    assert theme.primary == terminal_green
    assert theme.brand == terminal_green
    assert theme.accent == streamlit_blue
    assert theme.label == streamlit_blue
    assert theme.error == powershell_red
    assert theme.warning == muted_amber
    assert theme.muted == muted_gray
    assert theme.success == success_green
    assert ANSI_COLORS[streamlit_blue]
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


def test_console_renderer_phase_and_elapsed_shape():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )

    renderer.runtime_start()
    renderer.phase_start(ConsolePhase.BACKEND, "starting Streamlit")
    renderer.phase_success(ConsolePhase.HEALTH, "ready", elapsed_seconds=1.234)
    renderer.runtime_ready("http://127.0.0.1:8501")

    output = stream.getvalue()
    assert "[LitLaunch] Starting runtime" in output
    assert "[LitLaunch]   Backend: starting Streamlit" in output
    assert "Health: ready in 1.2s" in output
    assert "[LitLaunch] Runtime ready at http://127.0.0.1:8501" in output
    assert format_elapsed(0.04) == "0.0s"


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
    renderer.phase_start(ConsolePhase.BROWSER, "opening")
    renderer.info("Info")
    renderer.warning("Warning")
    renderer.error("Failure")

    output = stream.getvalue()
    assert "Starting" not in output
    assert "Ready" not in output
    assert "opening" not in output
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


def test_unknown_custom_color_is_unstyled_but_allowed():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(primary="custom_brand", use_color=True),
        stream=stream,
        env={},
    )

    renderer.header("LitLaunch")

    assert stream.getvalue() == "LitLaunch\n"


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
    assert "Hook: Closing resources" in output
    assert "Hook: Closing resources: Resources closed" in output
    assert "Hook: Closing resources: Resource close failed" in output


def test_console_renderer_browser_fallback_summary():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )
    edge = BrowserCapability(
        kind=BrowserKind.EDGE,
        name="Microsoft Edge",
        executable_path=None,
        available=False,
        supports_app_mode=True,
        supports_full_browser=True,
    )
    chrome = BrowserCapability(
        kind=BrowserKind.CHROME,
        name="Chrome",
        executable_path="chrome.exe",
        available=True,
        supports_app_mode=True,
        supports_full_browser=True,
    )

    renderer.render_browser_resolution(
        BrowserResolution(
            requested=BrowserChoice.EDGE,
            selected=chrome,
            fallback_chain=(edge, chrome),
            message="Selected Chrome.",
        ),
        prefer_app_mode=True,
    )

    output = stream.getvalue()
    assert "Microsoft Edge unavailable; using Chrome" in output
    assert "app-mode" in output


def test_console_renderer_monitor_status_rendering():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )

    renderer.render_window_monitor_result(
        WindowMonitorResult(
            supported=True,
            observed=True,
            closed=True,
            status=WindowMonitorStatus.WINDOW_CLOSED,
            message="Window closed.",
        )
    )
    renderer.render_window_monitor_result(
        WindowMonitorResult(
            supported=False,
            observed=False,
            closed=False,
            status=WindowMonitorStatus.UNSUPPORTED,
            message="Unsupported.",
        )
    )

    output = stream.getvalue()
    assert "Monitor: Window closed." in output
    assert "Monitor: Unsupported." in output


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
