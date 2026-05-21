from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from litlaunch.config import LauncherConfig
from litlaunch.exceptions import ConfigurationError
from litlaunch.platforms import Architecture, OperatingSystem, PlatformInfo
from litlaunch.profiles import LaunchProfile
from litlaunch.shortcut_writer import (
    ShortcutRequest,
    build_shortcut_plan,
    write_shortcut,
)


def platform_info(os_name: OperatingSystem) -> PlatformInfo:
    return PlatformInfo(
        os=os_name,
        architecture=Architecture.X64,
        python_version="3.14.5",
        python_executable="X:/Python/python.exe",
        machine="AMD64",
        system=os_name.value,
        release="1",
        is_windows=os_name == OperatingSystem.WINDOWS,
        is_macos=os_name == OperatingSystem.MACOS,
        is_linux=os_name == OperatingSystem.LINUX,
        supports_chromium_app_mode=True,
        supports_window_monitoring=os_name == OperatingSystem.WINDOWS,
        supports_default_browser_open=True,
        notes=(),
    )


def test_shortcut_plan_windows_bat_uses_app_parent():
    with tempfile.TemporaryDirectory(prefix="litlaunch-shortcut-", dir=Path.cwd()) as d:
        root = Path(d)
        app = root / "app.py"
        app.write_text("print('hi')\n", encoding="utf-8")
        profile = LaunchProfile("my-webapp", LauncherConfig(app_path=app))

        plan = build_shortcut_plan(
            ShortcutRequest(
                profile=profile,
                platform=platform_info(OperatingSystem.WINDOWS),
            )
        )

        assert plan.output_path == root / "my-webapp.bat"
        assert f'cd /d "{root}"' in plan.content
        assert '"litlaunch" "--profile" "my-webapp"' in plan.content
        assert plan.executable is False


def test_shortcut_plan_linux_shell_quotes_paths_and_config():
    with tempfile.TemporaryDirectory(prefix="litlaunch shortcut-", dir=Path.cwd()) as d:
        root = Path(d)
        app = root / "app.py"
        config = root / "litlaunch.toml"
        app.write_text("print('hi')\n", encoding="utf-8")
        profile = LaunchProfile("my-webapp", LauncherConfig(app_path=app))

        plan = build_shortcut_plan(
            ShortcutRequest(
                profile=profile,
                platform=platform_info(OperatingSystem.LINUX),
                config_path=config,
            )
        )

        assert plan.output_path == root / "my-webapp.sh"
        assert plan.content.startswith("#!/usr/bin/env sh\n")
        assert f"cd '{root}'" in plan.content
        assert "'litlaunch' '--profile' 'my-webapp' '--config'" in plan.content
        assert plan.executable is True


def test_shortcut_plan_macos_command_uses_cwd_and_custom_output():
    with tempfile.TemporaryDirectory(prefix="litlaunch-shortcut-", dir=Path.cwd()) as d:
        root = Path(d)
        app_root = root / "app"
        app_root.mkdir()
        app = app_root / "app.py"
        app.write_text("print('hi')\n", encoding="utf-8")
        output = root / "Launch.command"
        profile = LaunchProfile(
            "web",
            LauncherConfig(app_path=app, cwd=app_root),
        )

        plan = build_shortcut_plan(
            ShortcutRequest(
                profile=profile,
                platform=platform_info(OperatingSystem.MACOS),
                output_path=output,
                name="Ignored",
            )
        )

        assert plan.app_root == app_root
        assert plan.output_path == output
        assert plan.content.startswith("#!/usr/bin/env sh\n")


def test_write_shortcut_force_and_executable_mode():
    with tempfile.TemporaryDirectory(prefix="litlaunch-shortcut-", dir=Path.cwd()) as d:
        root = Path(d)
        app = root / "app.py"
        app.write_text("print('hi')\n", encoding="utf-8")
        profile = LaunchProfile("web", LauncherConfig(app_path=app))
        plan = build_shortcut_plan(
            ShortcutRequest(
                profile=profile,
                platform=platform_info(OperatingSystem.LINUX),
            )
        )

        write_shortcut(plan)
        assert plan.output_path.is_file()
        if os.name != "nt":
            assert plan.output_path.stat().st_mode & 0o111
        with pytest.raises(ConfigurationError):
            write_shortcut(plan)
        write_shortcut(plan, force=True)
