from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

import litlaunch
import litlaunch.planning as planning_module
from litlaunch._host_sizing_config import (
    HostSizingEligibilityStatus,
    evaluate_host_sizing_eligibility,
)
from litlaunch._host_sizing_transport import (
    HOST_SIZING_ENV_KEYS,
    HOST_SIZING_TOKEN_HEADER,
    LITLAUNCH_HOST_SIZING_ENABLED,
    LITLAUNCH_HOST_SIZING_ENDPOINT,
    LITLAUNCH_HOST_SIZING_LAUNCH_ID,
    LITLAUNCH_HOST_SIZING_ORIGIN,
    LITLAUNCH_HOST_SIZING_PROTOCOL,
    LITLAUNCH_HOST_SIZING_SOURCE_ID,
    LITLAUNCH_HOST_SIZING_TOKEN,
)
from litlaunch.config import HostSizingPolicy, LauncherConfig
from litlaunch.host_sizing import _handoff_from_env
from litlaunch.launcher import StreamlitLauncher

_TOKEN = "public-handoff-test-token-1234567890abcdef"


def valid_handoff_env() -> dict[str, str]:
    return {
        LITLAUNCH_HOST_SIZING_ENABLED: "1",
        LITLAUNCH_HOST_SIZING_ENDPOINT: ("http://127.0.0.1:49152/host-sizing/report"),
        LITLAUNCH_HOST_SIZING_TOKEN: _TOKEN,
        LITLAUNCH_HOST_SIZING_LAUNCH_ID: "launch_id_12345678",
        LITLAUNCH_HOST_SIZING_ORIGIN: "http://127.0.0.1:8501",
        LITLAUNCH_HOST_SIZING_PROTOCOL: "1",
        LITLAUNCH_HOST_SIZING_SOURCE_ID: "primary-surface",
    }


@pytest.mark.parametrize("browser", ["edge", "chrome"])
def test_initial_policy_is_statically_eligible_for_supported_windows_webapp(browser):
    config = LauncherConfig(
        "app.py",
        mode="webapp",
        browser=browser,
        host_sizing="initial",
    )

    eligibility = evaluate_host_sizing_eligibility(config, is_windows=True)

    assert eligibility.eligible is True
    assert eligibility.status == HostSizingEligibilityStatus.ELIGIBLE
    assert "runtime window authority" in eligibility.reason


@pytest.mark.parametrize(
    ("kwargs", "status"),
    [
        ({"host_sizing": "off"}, HostSizingEligibilityStatus.DISABLED),
        (
            {"mode": "browser", "browser": "edge", "host_sizing": "initial"},
            HostSizingEligibilityStatus.UNSUPPORTED_MODE,
        ),
        (
            {"mode": "webapp", "browser": "auto", "host_sizing": "initial"},
            HostSizingEligibilityStatus.UNSUPPORTED_BROWSER,
        ),
        (
            {
                "mode": "webapp",
                "browser": "edge",
                "host_sizing": "initial",
                "extra_browser_args": ("--user-data-dir=C:/external",),
            },
            HostSizingEligibilityStatus.REQUIRES_MANAGED_PROFILE,
        ),
        (
            {
                "mode": "webapp",
                "browser": "edge",
                "host": "0.0.0.0",
                "host_sizing": "initial",
            },
            HostSizingEligibilityStatus.REQUIRES_LOOPBACK,
        ),
    ],
)
def test_public_eligibility_rejects_unsupported_launch_shapes(kwargs, status):
    eligibility = evaluate_host_sizing_eligibility(
        LauncherConfig("app.py", **kwargs),
        is_windows=True,
    )

    assert eligibility.status == status
    assert eligibility.eligible is False


def test_public_eligibility_is_windows_only():
    config = LauncherConfig(
        "app.py",
        mode="webapp",
        browser="edge",
        host_sizing="initial",
    )

    eligibility = evaluate_host_sizing_eligibility(config, is_windows=False)

    assert eligibility.status == HostSizingEligibilityStatus.UNSUPPORTED_PLATFORM


def test_handoff_accessor_is_immutable_and_redacts_capability_token(monkeypatch):
    environment = valid_handoff_env()
    for key in HOST_SIZING_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)

    handoff = litlaunch.get_host_sizing_handoff()

    assert isinstance(handoff, litlaunch.HostSizingHandoff)
    assert handoff.endpoint == environment[LITLAUNCH_HOST_SIZING_ENDPOINT]
    assert handoff.launch_id == environment[LITLAUNCH_HOST_SIZING_LAUNCH_ID]
    assert handoff.protocol == 1
    assert handoff.source_id == "primary-surface"
    assert handoff.token_header == HOST_SIZING_TOKEN_HEADER
    assert handoff.capability_token == _TOKEN
    assert _TOKEN not in repr(handoff)
    assert "<redacted>" in repr(handoff)
    with pytest.raises(FrozenInstanceError):
        handoff.protocol = 2  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (LITLAUNCH_HOST_SIZING_ENABLED, "0"),
        (LITLAUNCH_HOST_SIZING_ENDPOINT, "http://localhost:49152/host-sizing/report"),
        (LITLAUNCH_HOST_SIZING_ENDPOINT, "http://127.0.0.1:49152/wrong"),
        (
            LITLAUNCH_HOST_SIZING_ENDPOINT,
            "http://127.0.0.1:49152/host-sizing/report/",
        ),
        (LITLAUNCH_HOST_SIZING_TOKEN, "too-short"),
        (LITLAUNCH_HOST_SIZING_LAUNCH_ID, "short"),
        (LITLAUNCH_HOST_SIZING_LAUNCH_ID, "launch.id.123456789"),
        (LITLAUNCH_HOST_SIZING_ORIGIN, "http://example.com:8501"),
        (LITLAUNCH_HOST_SIZING_PROTOCOL, "2"),
        (LITLAUNCH_HOST_SIZING_SOURCE_ID, "bad source"),
    ],
)
def test_handoff_accessor_fails_closed_for_invalid_child_metadata(field, value):
    environment = valid_handoff_env()
    environment[field] = value

    assert _handoff_from_env(environment) is None


def test_handoff_accessor_is_unavailable_without_managed_child_metadata(monkeypatch):
    for key in HOST_SIZING_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    assert litlaunch.get_host_sizing_handoff() is None


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:8501",
        "http://127.0.0.2:8501",
        "http://[::1]:8501",
        "https://127.0.0.1:8501",
    ],
)
def test_handoff_accepts_runtime_supported_exact_loopback_origins(origin):
    environment = valid_handoff_env()
    environment[LITLAUNCH_HOST_SIZING_ORIGIN] = origin

    assert _handoff_from_env(environment) is not None


class FixedPortManager:
    def resolve_port(self, _config):
        return 8501


def test_launch_plan_reports_credential_free_public_policy_state(monkeypatch):
    monkeypatch.setattr(
        planning_module,
        "evaluate_host_sizing_eligibility",
        lambda config: evaluate_host_sizing_eligibility(config, is_windows=True),
    )
    config = LauncherConfig(
        "app.py",
        mode="webapp",
        browser="edge",
        host_sizing=HostSizingPolicy.INITIAL,
    )
    plan = StreamlitLauncher(
        config,
        port_manager=FixedPortManager(),  # type: ignore[arg-type]
    ).build_launch_plan(include_browser_resolution=False)
    rendered = repr(plan)

    assert plan.host_sizing_policy == "initial"
    assert plan.host_sizing_experimental is True
    assert plan.host_sizing_eligibility == "eligible"
    assert _TOKEN not in rendered
    assert "host-sizing/report" not in rendered
