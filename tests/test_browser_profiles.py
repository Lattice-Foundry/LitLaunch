from pathlib import Path

from litlaunch.browser_profiles import (
    create_managed_browser_profile,
    has_browser_switch,
    with_managed_browser_profile_args,
)


def test_create_managed_browser_profile_preseeds_chromium_state(tmp_path: Path):
    profile_dir = create_managed_browser_profile(tmp_path)

    assert profile_dir.is_dir()
    assert (profile_dir / "First Run").is_file()
    assert (profile_dir / "Local State").is_file()
    assert "skip_first_run_ui" in (profile_dir / "Local State").read_text(
        encoding="utf-8"
    )


def test_with_managed_browser_profile_args_adds_isolation_switches(tmp_path: Path):
    profile_dir = tmp_path / "profile"

    args = with_managed_browser_profile_args(
        ("--existing",),
        profile_dir=profile_dir,
        title="Example",
        new_window=True,
    )

    assert args[0] == "--existing"
    assert f"--user-data-dir={profile_dir}" in args
    assert "--no-first-run" in args
    assert "--no-default-browser-check" in args
    assert "--disable-sync" in args
    assert "--window-name=LitLaunch - Example" in args
    assert "--new-window" in args


def test_with_managed_browser_profile_args_does_not_override_user_profile(
    tmp_path: Path,
):
    args = with_managed_browser_profile_args(
        ("--user-data-dir=C:/custom-profile",),
        profile_dir=tmp_path / "managed",
    )

    assert args.count("--user-data-dir=C:/custom-profile") == 1
    assert not any(str(arg).endswith("managed") for arg in args)


def test_with_managed_browser_profile_args_merges_disable_features(tmp_path: Path):
    args = with_managed_browser_profile_args(
        ("--disable-features=ExistingFeature",),
        profile_dir=tmp_path / "profile",
    )

    assert "--disable-features=ExistingFeature,msEdgeEnableNurturingFramework" in args


def test_has_browser_switch_matches_key_value_and_bare_forms():
    assert has_browser_switch(("--user-data-dir=C:/profile",), "--user-data-dir")
    assert has_browser_switch(("--no-first-run",), "--no-first-run")
    assert not has_browser_switch(("--not-the-switch",), "--no-first-run")
