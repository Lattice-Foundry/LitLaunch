"""Managed Chromium profile helpers for LitLaunch browser launches."""

from __future__ import annotations

import json
from pathlib import Path

from litlaunch.artifacts import create_managed_browser_profile_dir


def create_managed_browser_profile(root: Path) -> Path:
    """Create a temporary Chromium profile preseeded for app-style launch UX."""

    profile_path = create_managed_browser_profile_dir(root)
    (profile_path / "First Run").touch()
    local_state = {
        "distribution": {
            "import_bookmarks": False,
            "import_history": False,
            "import_home_page": False,
            "import_search_engine": False,
            "make_chrome_default": False,
            "make_chrome_default_for_user": False,
            "show_welcome_page": False,
            "skip_first_run_ui": True,
        },
        "sync": {
            "suppress_start": True,
        },
    }
    (profile_path / "Local State").write_text(
        json.dumps(local_state, sort_keys=True),
        encoding="utf-8",
    )
    return profile_path


def with_managed_browser_profile_args(
    args: tuple[str, ...],
    *,
    profile_dir: str | Path,
    title: str | None = None,
    new_window: bool = False,
) -> tuple[str, ...]:
    """Return Chromium args that use a LitLaunch-managed browser profile."""

    result = list(args)
    append_switch_once(result, f"--user-data-dir={profile_dir}", "--user-data-dir")
    append_switch_once(result, "--no-first-run", "--no-first-run")
    append_switch_once(result, "--disable-first-run-ui", "--disable-first-run-ui")
    append_switch_once(
        result,
        "--no-default-browser-check",
        "--no-default-browser-check",
    )
    append_switch_once(
        result,
        "--disable-default-browser-promo",
        "--disable-default-browser-promo",
    )
    append_switch_once(result, "--disable-default-apps", "--disable-default-apps")
    append_switch_once(result, "--disable-sync", "--disable-sync")
    append_switch_once(
        result,
        "--disable-background-networking",
        "--disable-background-networking",
    )
    append_switch_once(
        result,
        "--disable-component-update",
        "--disable-component-update",
    )
    append_comma_switch_values_once(
        result,
        "--disable-features",
        ("msEdgeEnableNurturingFramework",),
    )
    if title:
        append_switch_once(
            result,
            f"--window-name=LitLaunch - {title}",
            "--window-name",
        )
    if new_window:
        append_switch_once(result, "--new-window", "--new-window")
    return tuple(result)


def has_browser_switch(args: tuple[str, ...], switch: str) -> bool:
    """Return whether args already include a Chromium switch."""

    normalized = switch.strip().lower()
    prefix = f"{normalized}="
    return any(
        str(arg).strip().lower() == normalized
        or str(arg).strip().lower().startswith(prefix)
        for arg in args
    )


def append_switch_once(args: list[str], value: str, switch: str) -> None:
    """Append a switch unless an exact or key=value form already exists."""

    if has_browser_switch(tuple(args), switch):
        return
    args.append(value)


def append_comma_switch_values_once(
    args: list[str],
    switch: str,
    values: tuple[str, ...],
) -> None:
    """Append or merge a comma-valued Chromium switch."""

    normalized = f"{switch.lower()}="
    existing_index = next(
        (
            index
            for index, arg in enumerate(args)
            if str(arg).strip().lower().startswith(normalized)
        ),
        None,
    )
    if existing_index is None:
        args.append(f"{switch}={','.join(values)}")
        return

    existing = str(args[existing_index]).split("=", 1)[1]
    merged = [item for item in existing.split(",") if item]
    for value in values:
        if value not in merged:
            merged.append(value)
    args[existing_index] = f"{switch}={','.join(merged)}"
