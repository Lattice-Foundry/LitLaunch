from io import StringIO

from litlaunch.browsers import BrowserCapability, BrowserKind, BrowserResolution
from litlaunch.colors import (
    THEME_COLORS,
    help_magenta,
    hook_orange,
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
    ConsoleMode,
    ConsolePhase,
    ConsoleRenderer,
    ConsoleTheme,
    format_elapsed,
    strip_ansi,
)
from litlaunch.console_style import ANSI_COLORS, status_prefix, style_text
from litlaunch.lifecycle import LaunchEvent, LaunchState
from litlaunch.shutdown import HookConsoleVisibility, ShutdownHookResult
from litlaunch.windowing import WindowMonitorResult, WindowMonitorStatus


def test_named_theme_colors_exist_and_are_hex():
    expected_names = {
        streamlit_blue,
        streamlit_blue_light,
        terminal_green,
        powershell_red,
        muted_amber,
        hook_orange,
        help_magenta,
        muted_gray,
        success_green,
    }

    assert expected_names <= set(THEME_COLORS)
    for color in THEME_COLORS.values():
        assert is_hex_color(color.hex)


def test_console_theme_defaults_use_litlaunch_color_roles():
    theme = ConsoleTheme(use_color=False)

    assert theme.prefix == "LitLaunch"
    assert theme.primary == terminal_green
    assert theme.brand == terminal_green
    assert theme.accent == streamlit_blue
    assert theme.label == streamlit_blue
    assert theme.error == powershell_red
    assert theme.warning == muted_amber
    assert theme.muted == muted_gray
    assert theme.success == success_green
    assert THEME_COLORS[powershell_red].hex == "#E74856"
    assert THEME_COLORS[muted_amber].hex == "#F9F1A5"
    assert THEME_COLORS[help_magenta].hex == "#FF00FF"
    assert ANSI_COLORS[streamlit_blue]
    assert "indigo" not in ANSI_COLORS
    assert "cyan" not in ANSI_COLORS
    assert theme.use_color is False


def test_shared_console_style_status_prefix_and_no_color():
    assert status_prefix("warn", muted_amber, use_color=False) == "[  warn  ]"
    assert style_text("hello", streamlit_blue, use_color=False) == "hello"


def test_shared_console_style_applies_theme_color():
    styled = style_text("hello", streamlit_blue, use_color=True)

    assert THEME_COLORS[streamlit_blue].ansi in styled
    assert strip_ansi(styled) == "hello"


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
    assert "[   ok   ] Ready." in output
    assert "[  warn  ] Careful." in output
    assert "[ error  ] Failed." in output
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
    assert "[   ok   ] LitLaunch Starting runtime..." in output
    assert "[LitLaunch]" not in output
    assert "[   ok   ] Backend: Starting Streamlit..." in output
    assert "[   ok   ] Health: Ready in 1.2s." in output
    assert "[   ok   ] Runtime: Ready locally at http://127.0.0.1:8501." in output
    assert format_elapsed(0.04) == "0.0s"


def test_console_renderer_color_roles_for_runtime_header_status_and_phase():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=True),
        stream=stream,
        env={},
    )

    renderer.runtime_start()
    renderer.phase_start(ConsolePhase.BACKEND, "starting Streamlit")
    renderer.phase_success(ConsolePhase.HEALTH, "ready")
    renderer.error("Failed")

    output = stream.getvalue()
    assert THEME_COLORS[success_green].ansi in output
    assert THEME_COLORS[streamlit_blue].ansi in output
    assert THEME_COLORS[powershell_red].ansi in output
    assert THEME_COLORS[streamlit_blue_light].ansi not in output
    assert output.count(THEME_COLORS[streamlit_blue].ansi) == 3
    assert f"{THEME_COLORS[streamlit_blue].ansi}starting Streamlit" not in output
    assert f"{THEME_COLORS[streamlit_blue].ansi}ready" not in output
    assert strip_ansi(output).splitlines() == [
        "[   ok   ] LitLaunch Starting runtime...",
        "[   ok   ] Backend: Starting Streamlit...",
        "[   ok   ] Health: Ready.",
        "[ error  ] Failed.",
    ]


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
    renderer.info_status("Metadata")
    renderer.warning("Warning")
    renderer.error("Failure")

    output = stream.getvalue()
    assert "Starting" not in output
    assert "Ready" not in output
    assert "opening" not in output
    assert "Info" not in output
    assert "Metadata" not in output
    assert "[  warn  ] Warning." in output
    assert "[ error  ] Failure." in output


def test_console_renderer_info_status_uses_fixed_width_warning_label():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=True),
        stream=stream,
        env={},
    )

    renderer.info_status("OS: windows")

    output = stream.getvalue()
    assert THEME_COLORS[muted_amber].ansi in output
    assert strip_ansi(output) == "[  info  ] OS: windows.\n"


def test_failure_guidance_respects_quiet_normal_and_verbose_modes():
    quiet_stream = StringIO()
    ConsoleRenderer(
        mode="quiet",
        theme=ConsoleTheme(use_color=False),
        stream=quiet_stream,
    ).failure_guidance(
        "Backend failed.",
        likely_cause="secret-token cause",
        next_steps=("Run a check.",),
    )

    assert "Backend failed." in quiet_stream.getvalue()
    assert "Likely cause" not in quiet_stream.getvalue()

    normal_stream = StringIO()
    ConsoleRenderer(
        theme=ConsoleTheme(use_color=False),
        stream=normal_stream,
    ).failure_guidance(
        "Backend failed.",
        likely_cause="Streamlit exited.",
        next_steps=("Run Streamlit directly.",),
        suggest_inspect=True,
        detail="hidden in normal mode",
    )

    normal_output = normal_stream.getvalue()
    assert "Likely cause" not in normal_output
    assert "[ cause  ] Streamlit exited." in normal_output
    assert "[  next  ] Use verbose mode for more runtime details." in (normal_output)
    assert "Run Streamlit directly." not in normal_output
    assert 'Run "litlaunch inspect" for local diagnostics.' not in normal_output
    assert normal_output.count("[ cause  ]") == 1
    assert normal_output.count("[  next  ]") == 1
    assert "[   ok   ] cause" not in normal_output
    assert "[   ok   ] next" not in normal_output
    assert "cause:" not in normal_output
    assert "next:" not in normal_output
    assert "hidden in normal mode" not in normal_output

    verbose_stream = StringIO()
    ConsoleRenderer(
        mode="verbose",
        theme=ConsoleTheme(use_color=False),
        stream=verbose_stream,
        redacted_values=("secret-token",),
    ).failure_guidance(
        "Backend failed.",
        likely_cause="secret-token cause",
        next_steps=("Run a verbose-only check.",),
        suggest_inspect=True,
        detail="detail includes secret-token",
    )

    verbose_output = verbose_stream.getvalue()
    assert "Failure detail:" in verbose_output
    assert "[  next  ] Run a verbose-only check." in verbose_output
    assert '[  next  ] Run "litlaunch inspect" for local diagnostics.' in verbose_output
    assert "secret-token" not in verbose_output
    assert "[redacted]" in verbose_output


def test_failure_guidance_can_render_warning_level():
    stream = StringIO()
    renderer = ConsoleRenderer(theme=ConsoleTheme(use_color=False), stream=stream)

    renderer.failure_guidance(
        "Shutdown: Using backend termination fallback.",
        likely_cause="The backend did not stop through graceful shutdown.",
        level="warning",
    )

    output = stream.getvalue()
    assert "[  warn  ] Shutdown: Using backend termination fallback." in output
    assert "[ cause  ] The backend did not stop through graceful shutdown." in output
    assert output.count("[  next  ]") == 1


def test_failure_guidance_does_not_duplicate_verbose_next_step():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )

    renderer.failure_guidance(
        "Monitor failed.",
        next_steps=("Use verbose mode to inspect monitor setup details.",),
    )

    assert stream.getvalue().count("verbose") == 1


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
    assert "[   ok   ] Healthy." in output
    assert "[ error  ] Failed." in output


def test_console_renderer_has_shutdown_hook_render_surface():
    renderer = ConsoleRenderer(theme=ConsoleTheme(use_color=False))

    assert hasattr(renderer, "render_shutdown_hook_result")
    assert not hasattr(renderer, "render_shutdown_hook_start")
    assert not hasattr(renderer, "_render_shutdown_hook_start")
    assert not hasattr(renderer, "_render_shutdown_hook_result")


def test_console_renderer_shutdown_hook_result_uses_hook_category():
    stream = StringIO()
    renderer = ConsoleRenderer(theme=ConsoleTheme(use_color=False), stream=stream)

    renderer.render_shutdown_hook_result(
        ShutdownHookResult(
            label="Closing database connections",
            ok=True,
            message="Closed database connections",
            color=success_green,
        )
    )

    output = stream.getvalue()
    assert "[   ok   ] Hook: Closed database connections." in output
    assert "Shutdown: Closed database connections" not in output


def test_console_renderer_suppresses_verbose_only_success_hooks_in_normal_mode():
    stream = StringIO()
    renderer = ConsoleRenderer(theme=ConsoleTheme(use_color=False), stream=stream)

    renderer.render_shutdown_hook_result(
        ShutdownHookResult(
            label="Cloud sync",
            ok=True,
            message="Cloud sync completed",
            console_visibility=HookConsoleVisibility.VERBOSE,
        )
    )

    assert stream.getvalue() == ""


def test_console_renderer_suppresses_success_hooks_in_quiet_by_default():
    stream = StringIO()
    renderer = ConsoleRenderer(
        mode=ConsoleMode.QUIET,
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )

    renderer.render_shutdown_hook_result(
        ShutdownHookResult(
            label="Cleanup",
            ok=True,
            message="Cleanup complete",
        )
    )

    assert stream.getvalue() == ""


def test_console_renderer_can_show_success_hooks_in_quiet_mode():
    stream = StringIO()
    renderer = ConsoleRenderer(
        mode=ConsoleMode.QUIET,
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )

    renderer.render_shutdown_hook_result(
        ShutdownHookResult(
            label="Cleanup",
            ok=True,
            message="Cleanup complete",
            show_in_quiet=True,
        )
    )

    assert "[   ok   ] Hook: Cleanup complete." in stream.getvalue()


def test_console_renderer_can_show_verbose_hooks_in_quiet_mode():
    stream = StringIO()
    renderer = ConsoleRenderer(
        mode=ConsoleMode.QUIET,
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )

    renderer.render_shutdown_hook_result(
        ShutdownHookResult(
            label="Cleanup",
            ok=True,
            message="Cleanup complete",
            console_visibility=HookConsoleVisibility.VERBOSE,
            show_in_quiet=True,
        )
    )

    assert "[   ok   ] Hook: Cleanup complete." in stream.getvalue()


def test_console_renderer_shows_verbose_only_success_hooks_in_verbose_mode():
    stream = StringIO()
    renderer = ConsoleRenderer(
        mode=ConsoleMode.VERBOSE,
        theme=ConsoleTheme(use_color=False),
        stream=stream,
    )

    renderer.render_shutdown_hook_result(
        ShutdownHookResult(
            label="Cloud sync",
            ok=True,
            message="Cloud sync completed",
            console_visibility="verbose",
        )
    )

    assert "[   ok   ] Hook: Cloud sync completed." in stream.getvalue()


def test_console_renderer_always_shows_verbose_only_hook_failures_in_normal_mode():
    stream = StringIO()
    renderer = ConsoleRenderer(theme=ConsoleTheme(use_color=False), stream=stream)

    renderer.render_shutdown_hook_result(
        ShutdownHookResult(
            label="Cloud sync",
            ok=False,
            message="Cloud sync failed",
            error="full traceback hidden in normal",
            console_visibility=HookConsoleVisibility.VERBOSE,
        )
    )

    output = stream.getvalue()
    assert "[ error  ] Hook: Cloud sync failed." in output
    assert "[ cause  ] The shutdown hook raised an exception." in output
    assert "[  next  ] Use verbose mode for more runtime details." in output
    assert output.count("[ error  ]") == 1
    assert output.count("[ cause  ]") == 1
    assert output.count("[  next  ]") == 1
    assert "full traceback hidden in normal" not in output


def test_console_renderer_suppresses_success_hooks_marked_not_rendered():
    stream = StringIO()
    renderer = ConsoleRenderer(theme=ConsoleTheme(use_color=False), stream=stream)

    renderer.render_shutdown_hook_result(
        ShutdownHookResult(
            label="No-op cleanup",
            ok=True,
            message="No-op cleanup complete",
            render=False,
        )
    )

    assert stream.getvalue() == ""


def test_console_renderer_still_shows_failures_marked_not_rendered():
    stream = StringIO()
    renderer = ConsoleRenderer(theme=ConsoleTheme(use_color=False), stream=stream)

    renderer.render_shutdown_hook_result(
        ShutdownHookResult(
            label="Cleanup",
            ok=False,
            message="Cleanup failed",
            render=False,
        )
    )

    assert "[ error  ] Hook: Cleanup failed." in stream.getvalue()


def test_console_renderer_shutdown_hook_failure_is_redacted():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=False),
        stream=stream,
        redacted_values=("secret-token",),
    )

    renderer.render_shutdown_hook_result(
        ShutdownHookResult(
            label="Saving app state",
            ok=False,
            message="Saving secret-token app state failed",
            error="secret-token raised",
        )
    )

    output = stream.getvalue()
    assert "[ error  ] Hook: Saving [redacted] app state failed." in output
    assert "[ cause  ] The shutdown hook raised an exception." in output
    assert "[  next  ] Use verbose mode for more runtime details." in output
    assert "secret-token" not in output


def test_console_renderer_shutdown_hook_color_metadata_does_not_style_message():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=True),
        stream=stream,
        env={},
    )

    renderer.render_shutdown_hook_result(
        ShutdownHookResult(
            label="Cleanup",
            ok=True,
            message="Cleanup complete",
            color=success_green,
        )
    )

    output = stream.getvalue()
    assert THEME_COLORS[hook_orange].ansi in output
    assert THEME_COLORS[streamlit_blue].ansi not in output
    assert strip_ansi(output) == "[   ok   ] Hook: Cleanup complete.\n"


def test_console_renderer_shutdown_hook_uses_default_orange_message_color():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=True),
        stream=stream,
        env={},
    )

    renderer.render_shutdown_hook_result(
        ShutdownHookResult(
            label="Cleanup",
            ok=True,
            message="Cleanup complete",
        )
    )

    output = stream.getvalue()
    assert THEME_COLORS[hook_orange].ansi in output
    assert strip_ansi(output) == "[   ok   ] Hook: Cleanup complete.\n"


def test_console_renderer_unknown_hook_color_falls_back_safely():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=True),
        stream=stream,
        env={},
    )

    renderer.render_shutdown_hook_result(
        ShutdownHookResult(
            label="Cleanup",
            ok=True,
            message="Cleanup complete",
            color="project_custom_color",
        )
    )

    output = stream.getvalue()
    assert "project_custom_color" not in output
    assert strip_ansi(output) == "[   ok   ] Hook: Cleanup complete.\n"


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
    assert "[  warn  ] Browser: Microsoft Edge unavailable." in output
    assert "[  next  ] Using Chrome app-mode instead." in output
    assert "[  next  ] Use --browser to select a different browser." in output
    assert "app-mode" in output
    assert "[   ok   ] Using Chrome" not in output


def test_browser_strategy_uses_full_browser_when_not_preferring_app_mode():
    stream = StringIO()
    renderer = ConsoleRenderer(
        theme=ConsoleTheme(use_color=False),
        mode=ConsoleMode.VERBOSE,
        stream=stream,
    )

    renderer.render_browser_resolution(
        BrowserResolution(
            requested=BrowserChoice.EDGE,
            selected=BrowserCapability(
                kind=BrowserKind.EDGE,
                name="Microsoft Edge",
                executable_path="C:/Edge/msedge.exe",
                available=True,
                supports_app_mode=True,
                supports_full_browser=True,
            ),
            fallback_chain=(),
            message="Selected Microsoft Edge.",
        ),
        prefer_app_mode=False,
    )

    output = strip_ansi(stream.getvalue())
    assert "Browser strategy: Microsoft Edge (full-browser)." in output
    assert "app-mode" not in output


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
    assert "[   ok   ] Monitor: Window closed; requesting shutdown." in output
    assert "Monitor: Window monitoring is unavailable." in output
    assert "[ cause  ] Unsupported." in output
    assert "Likely cause" not in output


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
