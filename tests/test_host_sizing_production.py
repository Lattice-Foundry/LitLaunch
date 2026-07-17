from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path

import pytest

import litlaunch
from litlaunch._browser_authority import (
    BrowserLaunchAuthority,
    BrowserLaunchStrategy,
)
from litlaunch._host_sizing_authority import (
    PrivateHostSizingEligibility,
    PrivateHostSizingEligibilityStatus,
)
from litlaunch._host_sizing_geometry import (
    NativeRect,
    WindowGeometry,
    WindowGeometryState,
)
from litlaunch._host_sizing_policy import HostSizingPolicyConfig
from litlaunch._host_sizing_production import (
    PrivateHostSizingProductionStatus,
    _PrivateHostSizingActivation,
)
from litlaunch._host_sizing_transport import (
    HOST_SIZING_ENV_KEYS,
    HOST_SIZING_TOKEN_HEADER,
    LITLAUNCH_HOST_SIZING_ENDPOINT,
    LITLAUNCH_HOST_SIZING_LAUNCH_ID,
    LITLAUNCH_HOST_SIZING_ORIGIN,
    LITLAUNCH_HOST_SIZING_SOURCE_ID,
    LITLAUNCH_HOST_SIZING_TOKEN,
    parse_host_sizing_report,
)
from litlaunch._host_sizing_window import (
    HostSizingMutationResult,
    HostSizingMutationStatus,
    WindowSizingAuthority,
)
from litlaunch.artifacts import mark_litlaunch_owned
from litlaunch.browsers import BrowserKind
from litlaunch.config import BrowserChoice, HostSizingPolicy, LauncherConfig, LaunchMode
from litlaunch.events import RuntimeEvent, RuntimeEventEmitter

ALLOWED_ORIGIN = "http://127.0.0.1:8501"


def geometry() -> WindowGeometry:
    return WindowGeometry(
        handle=100,
        outer=NativeRect(100, 100, 1100, 900),
        client_width=984,
        client_height=761,
        dpi=96,
        monitor_handle=1,
        monitor=NativeRect(0, 0, 1920, 1080),
        work_area=NativeRect(0, 0, 1920, 1040),
        show_command=1,
        state=WindowGeometryState.NORMAL,
    )


def window_authority(
    *,
    browser_kind: BrowserKind = BrowserKind.EDGE,
) -> WindowSizingAuthority:
    return WindowSizingAuthority(
        authority_id="placeholder",
        handle=100,
        browser_kind=browser_kind,
        process_id=400,
        launch_process_ids=frozenset({400, 401}),
        stable_polls=3,
        baseline=geometry(),
        managed_profile=True,
        app_mode=True,
    )


def browser_authority(
    tmp_path: Path,
    launch_id: str,
    *,
    browser_kind: BrowserKind = BrowserKind.EDGE,
    strategy: BrowserLaunchStrategy = BrowserLaunchStrategy.DIRECT,
) -> BrowserLaunchAuthority:
    profile = tmp_path / f"profile-{browser_kind.value}-{strategy.value}"
    profile.mkdir(parents=True)
    mark_litlaunch_owned(profile)
    executable = (
        Path("C:/Edge/msedge.exe")
        if browser_kind == BrowserKind.EDGE
        else Path("C:/Chrome/chrome.exe")
    )
    return BrowserLaunchAuthority(
        launch_id=launch_id,
        root_process_id=400,
        root_creation_time_100ns=123456,
        browser_kind=browser_kind,
        executable_path=executable,
        managed_profile_dir=profile,
        launch_strategy=strategy,
        launched_at_monotonic=1.0,
    )


class FakeGate:
    is_windows = True

    def __init__(self, *, eligible: bool = True) -> None:
        self.eligible = eligible
        self.process_tracker = object()
        self.window_provider = object()
        self.geometry_backend = object()
        self.baseline_calls = 0
        self.collect_calls = []

    def capture_baseline_handles(self):
        self.baseline_calls += 1
        return ("10", "20")

    def collect(self, authority, **kwargs):
        self.collect_calls.append((authority, kwargs))
        if not self.eligible:
            return PrivateHostSizingEligibility(
                PrivateHostSizingEligibilityStatus.AMBIGUOUS,
                "Multiple exact windows were observed.",
                authority,
            )
        exact = replace(
            window_authority(browser_kind=authority.browser_kind),
            authority_id=authority.launch_id,
        )
        return PrivateHostSizingEligibility(
            PrivateHostSizingEligibilityStatus.ELIGIBLE,
            "Exact authority established.",
            authority,
            window_authority=exact,
        )


class FakeMutation:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = []

    def apply(self, *, decision, authority):
        self.calls.append((decision, authority))
        if self.fail:
            raise RuntimeError("fake native mutation failure")
        return HostSizingMutationResult(
            status=HostSizingMutationStatus.APPLIED,
            reason="fake height-only mutation applied",
            decision=decision,
            authority_id=authority.authority_id,
            baseline=authority.baseline,
            pre_apply=authority.baseline,
            after=authority.baseline,
            plan=None,
            mutation_attempted=True,
        )


def start_runtime(
    *,
    gate: FakeGate | None = None,
    mutation: FakeMutation | None = None,
    mode: LaunchMode = LaunchMode.WEBAPP,
    quiet_period_seconds: float = 0.0,
    timeout_seconds: float = 1.0,
    channel_starter=None,
    events: list[RuntimeEvent] | None = None,
    host_sizing: HostSizingPolicy = HostSizingPolicy.INITIAL,
):
    resolved_gate = gate or FakeGate()
    resolved_mutation = mutation or FakeMutation()
    kwargs = {}
    if channel_starter is not None:
        kwargs["channel_starter"] = channel_starter
    activation = _PrivateHostSizingActivation(
        activation_gate_factory=lambda: resolved_gate,
        mutation_factory=lambda _authority, _gate: resolved_mutation,
        policy_config=HostSizingPolicyConfig(
            quiet_period_seconds=quiet_period_seconds,
            timeout_seconds=timeout_seconds,
        ),
        event_emitter=RuntimeEventEmitter(
            events.append if events is not None else None
        ),
        **kwargs,
    )
    runtime = activation.begin(
        LauncherConfig(
            "app.py",
            mode=mode,
            browser=BrowserChoice.EDGE,
            host_sizing=host_sizing,
        )
    )
    assert runtime is not None
    return runtime, resolved_gate, resolved_mutation


def payload(
    env: dict[str, str],
    *,
    source_id: str = "primary-surface",
    sequence: int = 1,
):
    return {
        "protocol": 1,
        "launch_id": env[LITLAUNCH_HOST_SIZING_LAUNCH_ID],
        "source_id": source_id,
        "sequence": sequence,
        "device_pixel_ratio": 1.25,
        "content": {"height": 742, "width": 1180},
        "host_viewport": {"height": 812, "width": 1280},
        "desired_host_viewport": {"height": 900},
    }


def send(env: dict[str, str], body: dict[str, object]) -> int:
    request = urllib.request.Request(
        env[LITLAUNCH_HOST_SIZING_ENDPOINT],
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Origin": env[LITLAUNCH_HOST_SIZING_ORIGIN],
            HOST_SIZING_TOKEN_HEADER: env[LITLAUNCH_HOST_SIZING_TOKEN],
            "Content-Type": "application/json",
        },
    )
    try:
        response = urllib.request.urlopen(request, timeout=2.0)
    except urllib.error.HTTPError as exc:
        exc.read()
        status = exc.code
        exc.close()
        return status
    response.read()
    status = response.status
    response.close()
    return status


def wait_for_terminal(runtime, timeout: float = 2.0):
    deadline = time.monotonic() + timeout
    snapshot = runtime.snapshot()
    while not snapshot.closed and time.monotonic() < deadline:
        time.sleep(0.01)
        snapshot = runtime.snapshot()
    return snapshot


@pytest.mark.parametrize("browser_kind", [BrowserKind.EDGE, BrowserKind.CHROME])
@pytest.mark.parametrize(
    "strategy",
    [BrowserLaunchStrategy.DIRECT, BrowserLaunchStrategy.WINDOWS_SHORTCUT],
)
def test_private_production_path_applies_once_for_all_authority_shapes(
    tmp_path: Path,
    browser_kind: BrowserKind,
    strategy: BrowserLaunchStrategy,
):
    runtime, gate, mutation = start_runtime()
    env = dict(runtime.prepare_backend(ALLOWED_ORIGIN, None))

    assert set(env) == HOST_SIZING_ENV_KEYS
    assert env[LITLAUNCH_HOST_SIZING_SOURCE_ID] == "primary-surface"
    assert runtime.capture_window_baseline() is True
    authority = browser_authority(
        tmp_path,
        env[LITLAUNCH_HOST_SIZING_LAUNCH_ID],
        browser_kind=browser_kind,
        strategy=strategy,
    )
    assert runtime.activate_after_browser(
        authority,
        backend_is_running=lambda: True,
    )
    assert send(env, payload(env)) == 202

    snapshot = wait_for_terminal(runtime)

    assert snapshot.status == PrivateHostSizingProductionStatus.TERMINAL
    assert snapshot.channel_active is False
    assert snapshot.accepted_reports == 1
    assert snapshot.mutation_calls == 1
    assert snapshot.acknowledgements == 1
    assert snapshot.policy_state == "complete"
    assert len(mutation.calls) == 1
    assert gate.collect_calls[0][1]["baseline_handles"] == ("10", "20")
    assert env[LITLAUNCH_HOST_SIZING_TOKEN] not in repr(snapshot)
    with pytest.raises(urllib.error.URLError):
        send(env, payload(env))


def test_private_production_buffers_early_report_until_authority_exists(tmp_path: Path):
    runtime, _gate, mutation = start_runtime()
    env = dict(runtime.prepare_backend(ALLOWED_ORIGIN, None))

    assert send(env, payload(env)) == 202
    assert runtime.snapshot().pending_report is True
    assert runtime.capture_window_baseline() is True
    assert runtime.activate_after_browser(
        browser_authority(tmp_path, env[LITLAUNCH_HOST_SIZING_LAUNCH_ID]),
        backend_is_running=lambda: True,
    )

    snapshot = wait_for_terminal(runtime)
    assert snapshot.status == PrivateHostSizingProductionStatus.TERMINAL
    assert len(mutation.calls) == 1


def test_public_production_events_are_bounded_and_credential_free(tmp_path: Path):
    events: list[RuntimeEvent] = []
    runtime, _gate, _mutation = start_runtime(events=events)
    env = dict(runtime.prepare_backend(ALLOWED_ORIGIN, None))
    assert runtime.capture_window_baseline() is True
    assert runtime.activate_after_browser(
        browser_authority(tmp_path, env[LITLAUNCH_HOST_SIZING_LAUNCH_ID]),
        backend_is_running=lambda: True,
    )
    assert send(env, payload(env)) == 202

    wait_for_terminal(runtime)

    assert [event.name for event in events] == [
        "host_sizing_channel_ready",
        "host_sizing_eligible",
        "host_sizing_report_accepted",
        "host_sizing_applied",
    ]
    rendered = repr(events)
    assert env[LITLAUNCH_HOST_SIZING_TOKEN] not in rendered
    assert env[LITLAUNCH_HOST_SIZING_ENDPOINT] not in rendered
    assert env[LITLAUNCH_HOST_SIZING_LAUNCH_ID] not in rendered


def test_private_production_pending_buffer_keeps_highest_callback_sequence(
    tmp_path: Path,
):
    runtime, _gate, mutation = start_runtime()
    env = dict(runtime.prepare_backend(ALLOWED_ORIGIN, None))
    newer = parse_host_sizing_report(
        json.dumps(payload(env, sequence=2)).encode("utf-8")
    )
    older = parse_host_sizing_report(
        json.dumps(payload(env, sequence=1)).encode("utf-8")
    )

    runtime._accept_report(newer)
    runtime._accept_report(older)
    assert runtime.capture_window_baseline() is True
    assert runtime.activate_after_browser(
        browser_authority(tmp_path, env[LITLAUNCH_HOST_SIZING_LAUNCH_ID]),
        backend_is_running=lambda: True,
    )

    snapshot = wait_for_terminal(runtime)
    assert snapshot.status == PrivateHostSizingProductionStatus.TERMINAL
    assert mutation.calls[0][0].sequence == 2


def test_private_production_rejects_wrong_source_before_policy(tmp_path: Path):
    runtime, _gate, mutation = start_runtime()
    env = dict(runtime.prepare_backend(ALLOWED_ORIGIN, None))
    assert runtime.capture_window_baseline() is True
    assert runtime.activate_after_browser(
        browser_authority(tmp_path, env[LITLAUNCH_HOST_SIZING_LAUNCH_ID]),
        backend_is_running=lambda: True,
    )

    assert send(env, payload(env, source_id="secondary-surface")) == 403
    runtime.close()
    assert mutation.calls == []


def test_private_production_timeout_without_adapter_is_terminal(tmp_path: Path):
    runtime, _gate, mutation = start_runtime(timeout_seconds=0.05)
    env = dict(runtime.prepare_backend(ALLOWED_ORIGIN, None))
    assert runtime.capture_window_baseline() is True
    assert runtime.activate_after_browser(
        browser_authority(tmp_path, env[LITLAUNCH_HOST_SIZING_LAUNCH_ID]),
        backend_is_running=lambda: True,
    )

    snapshot = wait_for_terminal(runtime)
    assert snapshot.status == PrivateHostSizingProductionStatus.TERMINAL
    assert snapshot.policy_state == "timed_out"
    assert mutation.calls == []


def test_continuous_production_retains_channel_for_growth_and_shrink(
    tmp_path: Path,
):
    events: list[RuntimeEvent] = []
    runtime, _gate, mutation = start_runtime(
        host_sizing=HostSizingPolicy.CONTINUOUS,
        events=events,
    )
    env = dict(runtime.prepare_backend(ALLOWED_ORIGIN, None))
    assert runtime.capture_window_baseline() is True
    assert runtime.activate_after_browser(
        browser_authority(tmp_path, env[LITLAUNCH_HOST_SIZING_LAUNCH_ID]),
        backend_is_running=lambda: True,
    )
    assert send(env, payload(env, sequence=1)) == 202
    second = payload(env, sequence=2)
    second["content"] = {"height": 600, "width": 1180}
    second["host_viewport"] = {"height": 900, "width": 1280}
    second["desired_host_viewport"] = {"height": 700}
    assert send(env, second) == 202

    deadline = time.monotonic() + 2.0
    snapshot = runtime.snapshot()
    while snapshot.mutation_calls < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
        snapshot = runtime.snapshot()

    assert snapshot.continuous_active is True
    assert snapshot.channel_active is True
    assert snapshot.mutation_calls == 2
    assert snapshot.last_accepted_sequence == 2
    assert snapshot.last_target_height == 700
    assert len(mutation.calls) == 2

    runtime.close()
    closed = runtime.snapshot()
    assert closed.closed is True
    assert closed.status == PrivateHostSizingProductionStatus.TERMINAL
    assert closed.channel_active is False
    assert closed.continuous_active is False
    assert [event.name for event in events].count("host_sizing_report_accepted") == 1
    assert [event.name for event in events].count("host_sizing_channel_closed") == 1
    with pytest.raises(urllib.error.URLError):
        send(env, payload(env, sequence=3))


def test_continuous_production_does_not_use_initial_report_timeout(tmp_path: Path):
    runtime, _gate, mutation = start_runtime(
        host_sizing=HostSizingPolicy.CONTINUOUS,
        timeout_seconds=0.05,
    )
    env = dict(runtime.prepare_backend(ALLOWED_ORIGIN, None))
    assert runtime.capture_window_baseline() is True
    assert runtime.activate_after_browser(
        browser_authority(tmp_path, env[LITLAUNCH_HOST_SIZING_LAUNCH_ID]),
        backend_is_running=lambda: True,
    )
    time.sleep(0.1)

    snapshot = runtime.snapshot()
    assert snapshot.closed is False
    assert snapshot.continuous_active is True
    assert mutation.calls == []
    runtime.close()


def test_continuous_production_channels_are_launch_isolated(tmp_path: Path):
    first, _first_gate, first_mutation = start_runtime(
        host_sizing=HostSizingPolicy.CONTINUOUS
    )
    second, _second_gate, second_mutation = start_runtime(
        host_sizing=HostSizingPolicy.CONTINUOUS
    )
    first_env = dict(first.prepare_backend(ALLOWED_ORIGIN, None))
    second_env = dict(second.prepare_backend(ALLOWED_ORIGIN, None))
    assert first.capture_window_baseline() is True
    assert second.capture_window_baseline() is True
    assert first.activate_after_browser(
        browser_authority(
            tmp_path / "first",
            first_env[LITLAUNCH_HOST_SIZING_LAUNCH_ID],
        ),
        backend_is_running=lambda: True,
    )
    assert second.activate_after_browser(
        browser_authority(
            tmp_path / "second",
            second_env[LITLAUNCH_HOST_SIZING_LAUNCH_ID],
        ),
        backend_is_running=lambda: True,
    )

    assert send(first_env, payload(second_env)) == 403
    assert first_mutation.calls == []
    assert second_mutation.calls == []
    assert send(first_env, payload(first_env)) == 202
    assert send(second_env, payload(second_env)) == 202

    deadline = time.monotonic() + 2.0
    while (
        len(first_mutation.calls) < 1 or len(second_mutation.calls) < 1
    ) and time.monotonic() < deadline:
        time.sleep(0.01)

    assert len(first_mutation.calls) == 1
    assert len(second_mutation.calls) == 1
    first.close()
    second.close()


def test_private_production_shutdown_before_quiet_period_prevents_mutation(
    tmp_path: Path,
):
    runtime, _gate, mutation = start_runtime(quiet_period_seconds=1.0)
    env = dict(runtime.prepare_backend(ALLOWED_ORIGIN, None))
    assert runtime.capture_window_baseline() is True
    assert runtime.activate_after_browser(
        browser_authority(tmp_path, env[LITLAUNCH_HOST_SIZING_LAUNCH_ID]),
        backend_is_running=lambda: True,
    )
    assert send(env, payload(env)) == 202

    runtime.close()
    time.sleep(0.05)

    assert runtime.snapshot().closed is True
    assert mutation.calls == []


def test_private_production_mutation_failure_aborts_without_retry(tmp_path: Path):
    mutation = FakeMutation(fail=True)
    runtime, _gate, _mutation = start_runtime(mutation=mutation)
    env = dict(runtime.prepare_backend(ALLOWED_ORIGIN, None))
    assert runtime.capture_window_baseline() is True
    assert runtime.activate_after_browser(
        browser_authority(tmp_path, env[LITLAUNCH_HOST_SIZING_LAUNCH_ID]),
        backend_is_running=lambda: True,
    )
    assert send(env, payload(env)) == 202

    snapshot = wait_for_terminal(runtime)
    assert snapshot.policy_state == "aborted"
    assert snapshot.mutation_calls == 1
    assert snapshot.acknowledgements == 1
    assert len(mutation.calls) == 1


def test_private_production_failures_disable_sizing_without_raising(tmp_path: Path):
    runtime, _gate, mutation = start_runtime(gate=FakeGate(eligible=False))
    env = dict(runtime.prepare_backend(ALLOWED_ORIGIN, None))
    assert runtime.capture_window_baseline() is True

    assert not runtime.activate_after_browser(
        browser_authority(tmp_path, env[LITLAUNCH_HOST_SIZING_LAUNCH_ID]),
        backend_is_running=lambda: True,
    )
    snapshot = runtime.snapshot()
    assert snapshot.status == PrivateHostSizingProductionStatus.INELIGIBLE
    assert snapshot.closed is True
    assert mutation.calls == []

    def fail_channel(**_kwargs):
        raise OSError("private bind failed")

    failed, _gate, _mutation = start_runtime(channel_starter=fail_channel)
    assert failed.prepare_backend(ALLOWED_ORIGIN, None) == {}
    assert failed.snapshot().status == PrivateHostSizingProductionStatus.FAILED


def test_private_activation_is_default_off_and_non_webapp_is_ineligible():
    activation = _PrivateHostSizingActivation()
    assert activation.begin(LauncherConfig("app.py")) is None

    runtime, _gate, _mutation = start_runtime(mode=LaunchMode.BROWSER)
    assert runtime.prepare_backend(ALLOWED_ORIGIN, None) == {}
    assert runtime.snapshot().status == PrivateHostSizingProductionStatus.INELIGIBLE


def test_private_production_exposes_only_the_approved_public_surface():
    config = LauncherConfig("app.py")

    assert not hasattr(litlaunch, "PrivateHostSizingActivation")
    assert not hasattr(litlaunch, "HostSizingRuntimeCoordinator")
    assert litlaunch.HostSizingPolicy is HostSizingPolicy
    assert config.host_sizing is HostSizingPolicy.OFF
    assert not hasattr(config, "host_sizing_enabled")


def test_continuous_report_store_has_no_lifetime_cap_but_initial_does():
    from litlaunch._host_sizing_production import _report_store_for_policy

    continuous = _report_store_for_policy(HostSizingPolicy.CONTINUOUS)
    initial = _report_store_for_policy(HostSizingPolicy.INITIAL)

    # Continuous sizing must keep tracking content for the whole session, so its
    # store carries no one-shot lifetime ceiling; initial keeps the 1024 ceiling.
    assert continuous._max_accepted_reports is None
    assert initial._max_accepted_reports == 1024
