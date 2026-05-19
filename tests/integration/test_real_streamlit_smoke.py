from __future__ import annotations

from pathlib import Path

import pytest

from litlaunch import LauncherConfig, StreamlitLauncher

REPO_ROOT = Path(__file__).parents[2]


def test_real_streamlit_backend_smoke_without_browser():
    pytest.importorskip("streamlit")

    app_path = REPO_ROOT / "examples" / "minimal_app" / "app.py"
    config = LauncherConfig(
        app_path=app_path,
        title="LitLaunch Smoke App",
        browser="default",
        streamlit_args=(
            "--server.fileWatcherType",
            "none",
            "--global.developmentMode",
            "false",
        ),
    )
    launcher = StreamlitLauncher(config)
    session = launcher.start_backend(
        wait_for_health=True,
        health_timeout_seconds=30.0,
        health_interval_seconds=0.25,
    )

    try:
        assert session.ok, session.result.message
        assert session.url is not None
        assert session.is_running() is True
    finally:
        session.stop(timeout_seconds=5.0, graceful_timeout_seconds=3.0)

    assert session.is_running() is False
