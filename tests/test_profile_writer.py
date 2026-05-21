from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from litlaunch import profile_writer
from litlaunch.config import BrowserChoice, LauncherConfig, LaunchMode, TrustMode
from litlaunch.exceptions import ConfigurationError
from litlaunch.profile_writer import write_litlaunch_profile
from litlaunch.profiles import LaunchProfile, load_profile
from litlaunch.windowing import WindowMonitorConfig


@pytest.fixture
def tmp_path():
    with tempfile.TemporaryDirectory(prefix="litlaunch-writer-") as path:
        yield Path(path)


def make_profile(root: Path, name: str = "web") -> LaunchProfile:
    app = root / "app.py"
    app.write_text("print('hello')\n", encoding="utf-8")
    return LaunchProfile(
        name=name,
        config=LauncherConfig(
            app_path=app,
            title="My App",
            mode=LaunchMode.WEBAPP,
            browser=BrowserChoice.EDGE,
            port=8501,
            auto_port=False,
        ),
        monitor_window=True,
        graceful_timeout_seconds=15,
        window_monitor_config=WindowMonitorConfig(
            appear_timeout_seconds=60,
            poll_interval_seconds=1,
            stable_poll_count=2,
        ),
    )


def test_profile_writer_dry_run_does_not_write(tmp_path: Path):
    profile = make_profile(tmp_path)
    config_path = tmp_path / "litlaunch.toml"

    result = write_litlaunch_profile(profile, config_path, dry_run=True)

    assert result.path == config_path
    assert '[profiles."web"]' in result.toml
    assert not config_path.exists()


def test_profile_writer_creates_loadable_litlaunch_toml(tmp_path: Path):
    profile = make_profile(tmp_path)
    config_path = tmp_path / "litlaunch.toml"

    result = write_litlaunch_profile(profile, config_path)
    loaded = load_profile("web", config_path)

    assert config_path.read_text(encoding="utf-8") == result.toml
    assert loaded.name == "web"
    assert loaded.config.app_path == tmp_path / "app.py"
    assert loaded.window_monitor_config.stable_poll_count == 2


def test_profile_writer_refuses_overwrite_without_force(tmp_path: Path):
    config_path = tmp_path / "litlaunch.toml"
    write_litlaunch_profile(make_profile(tmp_path, "web"), config_path)

    with pytest.raises(ConfigurationError, match="already exists"):
        write_litlaunch_profile(make_profile(tmp_path, "web"), config_path)


def test_profile_writer_overwrites_with_force(tmp_path: Path):
    config_path = tmp_path / "litlaunch.toml"
    write_litlaunch_profile(make_profile(tmp_path, "web"), config_path)
    app = tmp_path / "app.py"
    replacement = LaunchProfile(
        name="web",
        config=LauncherConfig(app_path=app, title="Replacement"),
    )

    write_litlaunch_profile(replacement, config_path, force=True)

    assert load_profile("web", config_path).config.title == "Replacement"


def test_profile_writer_refuses_non_profile_content(tmp_path: Path):
    config_path = tmp_path / "litlaunch.toml"
    config_path.write_text(
        """
[project]
name = "not-just-litlaunch"
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="non-profile TOML content"):
        write_litlaunch_profile(make_profile(tmp_path), config_path)


def test_profile_writer_preserves_other_profiles(tmp_path: Path):
    config_path = tmp_path / "litlaunch.toml"
    write_litlaunch_profile(make_profile(tmp_path, "web"), config_path)
    write_litlaunch_profile(make_profile(tmp_path, "browser"), config_path)

    assert load_profile("web", config_path).name == "web"
    assert load_profile("browser", config_path).name == "browser"


def test_profile_writer_escapes_control_characters_and_quotes(tmp_path: Path):
    app = tmp_path / "app.py"
    app.write_text("print('hello')\n", encoding="utf-8")
    profile = LaunchProfile(
        name="web",
        config=LauncherConfig(
            app_path=app,
            title='Line 1\nLine "2"\tTabbed\\Path',
            extra_env={"TOKEN": "first\r\nsecond"},
            allow_network_exposure=True,
        ),
    )
    config_path = tmp_path / "litlaunch.toml"

    result = write_litlaunch_profile(profile, config_path)
    loaded = load_profile("web", config_path)

    assert '\\nLine \\"2\\"\\tTabbed\\\\Path' in result.toml
    assert "first\\r\\nsecond" in result.toml
    assert "allow_network_exposure = true" in result.toml
    assert loaded.config.title == 'Line 1\nLine "2"\tTabbed\\Path'
    assert loaded.config.extra_env["TOKEN"] == "first\r\nsecond"
    assert loaded.config.allow_network_exposure is True


def test_profile_writer_round_trips_non_default_trust_mode(tmp_path: Path):
    app = tmp_path / "app.py"
    app.write_text("print('hello')\n", encoding="utf-8")
    profile = LaunchProfile(
        name="web",
        config=LauncherConfig(app_path=app, trust_mode=TrustMode.STRICT_LOCAL),
    )
    config_path = tmp_path / "litlaunch.toml"

    result = write_litlaunch_profile(profile, config_path)
    loaded = load_profile("web", config_path)

    assert 'trust_mode = "strict_local"' in result.toml
    assert loaded.config.trust_mode == TrustMode.STRICT_LOCAL


def test_profile_writer_omits_default_trust_mode(tmp_path: Path):
    profile = make_profile(tmp_path)

    result = write_litlaunch_profile(profile, tmp_path / "litlaunch.toml", dry_run=True)

    assert "trust_mode" not in result.toml


def test_profile_writer_keeps_existing_file_when_atomic_write_fails(
    tmp_path: Path,
    monkeypatch,
):
    config_path = tmp_path / "litlaunch.toml"
    write_litlaunch_profile(make_profile(tmp_path, "web"), config_path)
    original = config_path.read_text(encoding="utf-8")

    def fail_write(path: Path, content: str) -> None:
        raise OSError("simulated write failure")

    monkeypatch.setattr(profile_writer, "_atomic_write_text", fail_write)

    with pytest.raises(OSError, match="simulated write failure"):
        write_litlaunch_profile(make_profile(tmp_path, "other"), config_path)

    assert config_path.read_text(encoding="utf-8") == original
