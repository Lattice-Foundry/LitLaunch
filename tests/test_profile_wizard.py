from __future__ import annotations

import tempfile
from collections.abc import Iterable
from io import StringIO
from pathlib import Path

import pytest

from litlaunch.config import BrowserChoice, LaunchMode
from litlaunch.console import strip_ansi
from litlaunch.platforms import Architecture, OperatingSystem, PlatformInfo
from litlaunch.profile_wizard import (
    ProfileWizardCancelled,
    ProfileWizardOptions,
    run_profile_wizard,
)
from litlaunch.profiles import load_profile


@pytest.fixture
def tmp_path():
    with tempfile.TemporaryDirectory(prefix="litlaunch-wizard-") as path:
        yield Path(path)


def platform_info() -> PlatformInfo:
    return PlatformInfo(
        os=OperatingSystem.WINDOWS,
        architecture=Architecture.X64,
        python_version="3.14.5",
        python_executable="X:/Python/python.exe",
        machine="AMD64",
        system="Windows",
        release="11",
        is_windows=True,
        is_macos=False,
        is_linux=False,
        supports_chromium_app_mode=True,
        supports_window_monitoring=True,
        supports_default_browser_open=True,
        notes=(),
    )


def run_wizard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    answers: Iterable[str],
    *,
    dry_run: bool = False,
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app.py").write_text("print('hello')\n", encoding="utf-8")
    answer_iter = iter(answers)
    stream = StringIO()
    result = run_profile_wizard(
        ProfileWizardOptions(dry_run=dry_run, use_color=False),
        stream=stream,
        platform_is_windows=True,
        platform_info=platform_info(),
        input_func=lambda: next(answer_iter),
    )
    return result, stream.getvalue()


def test_profile_wizard_simple_mode_happy_path_declines_shortcut(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    result, output = run_wizard(
        tmp_path,
        monkeypatch,
        ["", "web", "", "Example App", "", "", "", "", "", "n"],
    )

    assert result is not None
    profile = load_profile("web", tmp_path / "litlaunch.toml")
    assert profile.config.mode == LaunchMode.WEBAPP
    assert profile.config.title == "Example App"
    assert profile.monitor_window is True
    assert "Profile preview" in output
    assert not (tmp_path / "web.bat").exists()


def test_profile_wizard_advanced_mode_writes_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    result, _output = run_wizard(
        tmp_path,
        monkeypatch,
        [
            "2",
            "advanced",
            "",
            "Advanced App",
            "",
            "chrome",
            "0.0.0.0",
            "y",
            "8502",
            "n",
            "n",
            "true",
            "",
            "y",
            "20",
            "70",
            "2",
            "3",
            "",
            "",
            "",
            ".",
            "",
            "",
            "",
            "n",
        ],
    )

    assert result is not None
    profile = load_profile("advanced", tmp_path / "litlaunch.toml")
    assert profile.config.browser == BrowserChoice.CHROME
    assert profile.config.host == "0.0.0.0"
    assert profile.config.port == 8502
    assert profile.config.auto_port is False
    assert profile.graceful_timeout_seconds == 20
    assert profile.window_monitor_config.stable_poll_count == 3


def test_profile_wizard_quit_cancels_cleanly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app.py").write_text("print('hello')\n", encoding="utf-8")
    stream = StringIO()

    with pytest.raises(ProfileWizardCancelled):
        run_profile_wizard(
            ProfileWizardOptions(use_color=False),
            stream=stream,
            platform_is_windows=True,
            platform_info=platform_info(),
            input_func=lambda: "quit",
        )

    assert "Profile creation cancelled." in stream.getvalue()
    assert not (tmp_path / "litlaunch.toml").exists()


def test_profile_wizard_warning_status_uses_shared_colored_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app.py").write_text("print('hello')\n", encoding="utf-8")
    stream = StringIO()

    with pytest.raises(ProfileWizardCancelled):
        run_profile_wizard(
            ProfileWizardOptions(use_color=True),
            stream=stream,
            platform_is_windows=True,
            platform_info=platform_info(),
            input_func=lambda: "quit",
        )

    output = stream.getvalue()
    assert "\033[" in output
    assert "[  warn  ] Profile creation cancelled." in strip_ansi(output)


def test_profile_wizard_back_navigation_preserves_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    result, _output = run_wizard(
        tmp_path,
        monkeypatch,
        [
            "",
            "first-name",
            "back",
            "second-name",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "n",
        ],
    )

    assert result is not None
    assert (
        load_profile("second-name", tmp_path / "litlaunch.toml").name == "second-name"
    )


def test_profile_wizard_dry_run_previews_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    result, output = run_wizard(
        tmp_path,
        monkeypatch,
        ["", "preview", "", "", "", "", "", "", ""],
        dry_run=True,
    )

    assert result is not None
    assert '[profiles."preview"]' in output
    assert "Shortcut creation would be offered" in output
    assert not (tmp_path / "litlaunch.toml").exists()


def test_profile_wizard_shortcut_prompt_defaults_to_no(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    result, output = run_wizard(
        tmp_path,
        monkeypatch,
        ["", "shortcut-default", "", "", "", "", "", "", "", ""],
    )

    assert result is not None
    assert "Create a shortcut for this profile now" in output
    assert not (tmp_path / "shortcut-default.bat").exists()
