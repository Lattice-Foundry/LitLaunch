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
    ShortcutKind,
    ShortcutRequest,
    build_shortcut_plan,
    write_shortcut,
)
from litlaunch.windows_shortcut import windows_app_user_model_id


@pytest.fixture
def tmp_path():
    with tempfile.TemporaryDirectory(prefix="litlaunch-shortcut-") as path:
        yield Path(path)


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


def test_shortcut_plan_windows_lnk_uses_app_parent_and_python(tmp_path: Path):
    app = tmp_path / "app.py"
    app.write_text("print('hi')\n", encoding="utf-8")
    profile = LaunchProfile("my-webapp", LauncherConfig(app_path=app))

    plan = build_shortcut_plan(
        ShortcutRequest(
            profile=profile,
            platform=platform_info(OperatingSystem.WINDOWS),
        )
    )

    assert plan.kind == ShortcutKind.NATIVE
    assert plan.output_path == tmp_path / ".litlaunch" / "shortcuts" / "my-webapp.lnk"
    assert f"Start in: {tmp_path}" in plan.content
    assert plan.command[:5] == (
        "X:/Python/python.exe",
        "-m",
        "litlaunch.cli",
        "--profile",
        "my-webapp",
    )
    assert plan.executable is False


def test_shortcut_plan_windows_lnk_includes_app_icon(tmp_path: Path):
    app = tmp_path / "app.py"
    icon = tmp_path / "app.ico"
    app.write_text("print('hi')\n", encoding="utf-8")
    icon.write_bytes(b"icon")
    profile = LaunchProfile("my-webapp", LauncherConfig(app_path=app, app_icon=icon))

    plan = build_shortcut_plan(
        ShortcutRequest(
            profile=profile,
            platform=platform_info(OperatingSystem.WINDOWS),
        )
    )

    assert plan.app_icon == icon
    assert f"Icon: {icon}" in plan.content


def test_shortcut_plan_windows_script_bat_uses_app_parent(tmp_path: Path):
    app = tmp_path / "app.py"
    app.write_text("print('hi')\n", encoding="utf-8")
    profile = LaunchProfile("my-webapp", LauncherConfig(app_path=app))

    plan = build_shortcut_plan(
        ShortcutRequest(
            profile=profile,
            platform=platform_info(OperatingSystem.WINDOWS),
            kind=ShortcutKind.SCRIPT,
        )
    )

    assert plan.output_path == tmp_path / ".litlaunch" / "shortcuts" / "my-webapp.bat"
    assert f'cd /d "{tmp_path}"' in plan.content
    assert '"X:/Python/python.exe" "-m" "litlaunch.cli"' in plan.content
    assert '"--profile" "my-webapp"' in plan.content
    assert plan.executable is False


def test_shortcut_plan_linux_desktop_quotes_paths_and_config(tmp_path: Path):
    app = tmp_path / "app.py"
    config = tmp_path / "litlaunch.toml"
    app.write_text("print('hi')\n", encoding="utf-8")
    profile = LaunchProfile("my-webapp", LauncherConfig(app_path=app))

    plan = build_shortcut_plan(
        ShortcutRequest(
            profile=profile,
            platform=platform_info(OperatingSystem.LINUX),
            config_path=config,
        )
    )

    assert plan.output_path == (
        tmp_path / ".litlaunch" / "shortcuts" / "my-webapp.desktop"
    )
    assert plan.content.startswith("[Desktop Entry]\n")
    assert "Type=Application" in plan.content
    assert "Terminal=true" in plan.content
    assert (
        "Exec=X:/Python/python.exe -m litlaunch.cli --profile my-webapp --config"
        in (plan.content)
    )
    assert plan.executable is True


def test_shortcut_plan_linux_desktop_includes_app_icon(tmp_path: Path):
    app = tmp_path / "app.py"
    icon = tmp_path / "assets" / "app.svg"
    app.write_text("print('hi')\n", encoding="utf-8")
    icon.parent.mkdir()
    icon.write_text("<svg />", encoding="utf-8")
    profile = LaunchProfile("my-webapp", LauncherConfig(app_path=app, app_icon=icon))

    plan = build_shortcut_plan(
        ShortcutRequest(
            profile=profile,
            platform=platform_info(OperatingSystem.LINUX),
        )
    )

    assert "Icon=" in plan.content
    assert "app.svg" in plan.content


def test_shortcut_plan_linux_script_quotes_paths_and_config(tmp_path: Path):
    app = tmp_path / "app.py"
    config = tmp_path / "litlaunch.toml"
    app.write_text("print('hi')\n", encoding="utf-8")
    profile = LaunchProfile("my-webapp", LauncherConfig(app_path=app))

    plan = build_shortcut_plan(
        ShortcutRequest(
            profile=profile,
            platform=platform_info(OperatingSystem.LINUX),
            config_path=config,
            kind=ShortcutKind.SCRIPT,
        )
    )

    assert plan.output_path == tmp_path / ".litlaunch" / "shortcuts" / "my-webapp.sh"
    assert plan.content.startswith("#!/usr/bin/env sh\n")
    assert f"cd '{tmp_path}'" in plan.content
    assert "'X:/Python/python.exe' '-m' 'litlaunch.cli' '--profile'" in plan.content
    assert "'--config'" in plan.content
    assert plan.executable is True


def test_shortcut_plan_macos_command_uses_cwd_and_custom_output(tmp_path: Path):
    app_root = tmp_path / "app"
    app_root.mkdir()
    app = app_root / "app.py"
    app.write_text("print('hi')\n", encoding="utf-8")
    output = tmp_path / "Launch.command"
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
            kind=ShortcutKind.SCRIPT,
        )
    )

    assert plan.app_root == app_root
    assert plan.output_path == output
    assert plan.content.startswith("#!/usr/bin/env sh\n")


def test_write_shortcut_force_and_executable_mode(tmp_path: Path):
    app = tmp_path / "app.py"
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


def test_windows_shortcut_escapes_cmd_sensitive_characters(tmp_path: Path):
    app = tmp_path / "app.py"
    app.write_text("print('hi')\n", encoding="utf-8")
    app_root = tmp_path / 'App & Data % "Carets^"'
    profile = LaunchProfile(
        "web-profile",
        LauncherConfig(app_path=app, cwd=app_root),
    )
    config = app_root / "litlaunch & config.toml"

    plan = build_shortcut_plan(
        ShortcutRequest(
            profile=profile,
            platform=platform_info(OperatingSystem.WINDOWS),
            config_path=config,
            kind=ShortcutKind.SCRIPT,
        )
    )

    assert "%%" in plan.content
    assert "^&" in plan.content
    assert "^^" in plan.content
    assert '^"' in plan.content
    assert '"X:/Python/python.exe" "-m" "litlaunch.cli"' in plan.content
    assert '"--profile" "web-profile"' in plan.content
    assert "litlaunch ^& config.toml" in plan.content


def test_windows_app_user_model_id_is_stable_and_labelled(tmp_path: Path):
    icon = tmp_path / "studio.ico"
    icon.write_bytes(b"icon")

    first = windows_app_user_model_id(tmp_path, "LitPack Studio", icon)
    second = windows_app_user_model_id(tmp_path, "LitPack Studio", icon)

    assert first == second
    assert first.startswith("LatticeFoundry.LitLaunch.LitPack.Studio.")
    assert len(first) <= 128


def test_shortcut_plan_macos_native_app_bundle(tmp_path: Path):
    app = tmp_path / "app.py"
    app.write_text("print('hi')\n", encoding="utf-8")
    profile = LaunchProfile("my-webapp", LauncherConfig(app_path=app))

    plan = build_shortcut_plan(
        ShortcutRequest(
            profile=profile,
            platform=platform_info(OperatingSystem.MACOS),
        )
    )

    assert plan.output_path == tmp_path / ".litlaunch" / "shortcuts" / "my-webapp.app"
    assert {file.relative_path.as_posix() for file in plan.files} == {
        "Contents/Info.plist",
        "Contents/MacOS/launch",
    }
    assert "CFBundlePackageType" in plan.content
