"""Private production-lifecycle activation for one initial host-sizing attempt."""

from __future__ import annotations

import re
import secrets
import threading
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from litlaunch._browser_authority import BrowserLaunchAuthority
from litlaunch._host_sizing_authority import (
    PrivateHostSizingActivationGate,
    ProcessBoundWindowsWindowAuthorityVerifier,
)
from litlaunch._host_sizing_policy import HostSizingPolicy, HostSizingPolicyConfig
from litlaunch._host_sizing_runtime import (
    HostSizingMutationCapability,
    HostSizingRuntimeCoordinator,
    HostSizingRuntimeSnapshot,
)
from litlaunch._host_sizing_transport import (
    LITLAUNCH_HOST_SIZING_SOURCE_ID,
    HostSizingChannel,
    HostSizingReport,
    start_host_sizing_channel,
)
from litlaunch._host_sizing_window import (
    TrustedWindowsWindowSizer,
    WindowSizingAuthority,
)
from litlaunch.config import LauncherConfig, LaunchMode
from litlaunch.console import ConsoleRenderer

PRIVATE_HOST_SIZING_SOURCE_ID = "primary-surface"
_SOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class PrivateHostSizingProductionStatus(str, Enum):
    """Credential-free internal production activation states."""

    CREATED = "created"
    INELIGIBLE = "ineligible"
    CHANNEL_READY = "channel_ready"
    BASELINE_READY = "baseline_ready"
    ACTIVE = "active"
    TERMINAL = "terminal"
    FAILED = "failed"


@dataclass(frozen=True)
class PrivateHostSizingProductionSnapshot:
    """Bounded internal lifecycle evidence with no endpoint credentials."""

    enabled: bool
    status: PrivateHostSizingProductionStatus
    reason: str
    closed: bool
    channel_active: bool
    pending_report: bool
    accepted_reports: int
    mutation_calls: int
    acknowledgements: int
    policy_state: str | None


class PrivateHostSizingRuntime(Protocol):
    """Narrow lifecycle shape consumed by the production launcher and session."""

    def prepare_backend(
        self,
        app_url: str,
        console_renderer: ConsoleRenderer | None,
    ) -> Mapping[str, str]:
        """Start private transport and return the backend-only environment."""

    def capture_window_baseline(self) -> bool:
        """Capture pre-browser HWNDs for exact authority collection."""

    def authority_launch_id(self) -> str | None:
        """Return the current credential-free launch binding."""

    def activate_after_browser(
        self,
        authority: BrowserLaunchAuthority | None,
        *,
        backend_is_running: Callable[[], bool],
    ) -> bool:
        """Attach exact authority and start the existing coordinator."""

    def close(self) -> None:
        """Invalidate transport, policy, reports, and credentials idempotently."""

    def snapshot(self) -> PrivateHostSizingProductionSnapshot:
        """Return credential-free internal lifecycle evidence."""


RuntimeFactory = Callable[..., PrivateHostSizingRuntime]
ChannelStarter = Callable[..., HostSizingChannel]
MutationFactory = Callable[
    [BrowserLaunchAuthority, PrivateHostSizingActivationGate],
    HostSizingMutationCapability,
]
CoordinatorFactory = Callable[
    [HostSizingPolicyConfig, HostSizingMutationCapability, WindowSizingAuthority],
    HostSizingRuntimeCoordinator,
]


class _PrivateHostSizingActivation:
    """Internal constructor-only activation gate; disabled unless injected."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        source_id: str = PRIVATE_HOST_SIZING_SOURCE_ID,
        policy_config: HostSizingPolicyConfig | None = None,
        activation_gate_factory: Callable[
            [], PrivateHostSizingActivationGate
        ] = PrivateHostSizingActivationGate,
        channel_starter: ChannelStarter = start_host_sizing_channel,
        mutation_factory: MutationFactory | None = None,
        coordinator_factory: CoordinatorFactory | None = None,
        runtime_factory: RuntimeFactory | None = None,
    ) -> None:
        normalized_source = str(source_id).strip()
        if not _SOURCE_ID_PATTERN.fullmatch(normalized_source):
            raise ValueError("Private host-sizing source ID is invalid.")
        self.enabled = enabled is True
        self.source_id = normalized_source
        self.policy_config = policy_config or HostSizingPolicyConfig()
        self.activation_gate_factory = activation_gate_factory
        self.channel_starter = channel_starter
        self.mutation_factory = mutation_factory or _default_mutation_factory
        self.coordinator_factory = coordinator_factory or _default_coordinator_factory
        self.runtime_factory = runtime_factory or _PrivateHostSizingProductionRuntime

    def begin(
        self,
        config: LauncherConfig,
    ) -> PrivateHostSizingRuntime | None:
        """Create one private per-launch runtime only when explicitly enabled."""

        if not self.enabled:
            return None
        return self.runtime_factory(
            config=config,
            source_id=self.source_id,
            policy_config=self.policy_config,
            activation_gate=self.activation_gate_factory(),
            channel_starter=self.channel_starter,
            mutation_factory=self.mutation_factory,
            coordinator_factory=self.coordinator_factory,
        )


class _PrivateHostSizingProductionRuntime:
    """Bridge backend startup, browser authority, coordinator, and session cleanup."""

    def __init__(
        self,
        *,
        config: LauncherConfig,
        source_id: str,
        policy_config: HostSizingPolicyConfig,
        activation_gate: PrivateHostSizingActivationGate,
        channel_starter: ChannelStarter,
        mutation_factory: MutationFactory,
        coordinator_factory: CoordinatorFactory,
    ) -> None:
        self.config = config
        self.source_id = source_id
        self.policy_config = policy_config
        self.activation_gate = activation_gate
        self.channel_starter = channel_starter
        self.mutation_factory = mutation_factory
        self.coordinator_factory = coordinator_factory
        self._lock = threading.RLock()
        self._launch_id = secrets.token_urlsafe(18)
        self._status = PrivateHostSizingProductionStatus.CREATED
        self._reason = "Private host-sizing activation created."
        self._closed = False
        self._channel: HostSizingChannel | None = None
        self._coordinator: HostSizingRuntimeCoordinator | None = None
        self._watcher: threading.Thread | None = None
        self._pending_report: HostSizingReport | None = None
        self._baseline_handles: tuple[str, ...] | None = None
        self._terminal_snapshot: HostSizingRuntimeSnapshot | None = None
        if config.mode != LaunchMode.WEBAPP:
            self._mark_ineligible("Private host sizing requires webapp mode.")
        elif not activation_gate.is_windows:
            self._mark_ineligible("Private host sizing requires Windows.")

    def prepare_backend(
        self,
        app_url: str,
        console_renderer: ConsoleRenderer | None,
    ) -> Mapping[str, str]:
        """Start LL-HS1 before backend startup and return its private handoff."""

        with self._lock:
            if self._closed:
                return {}
            if self._channel is not None:
                return self._backend_env_locked()
        try:
            channel = self.channel_starter(
                allowed_origin=app_url,
                console_renderer=console_renderer,
                launch_id=self._launch_id,
                expected_source_id=self.source_id,
                accepted_report_callback=self._accept_report,
            )
        except Exception:
            self._fail("Private host-sizing channel startup failed.")
            return {}
        with self._lock:
            if self._closed:
                close_after = True
            else:
                self._channel = channel
                self._status = PrivateHostSizingProductionStatus.CHANNEL_READY
                self._reason = "Private host-sizing channel is ready."
                close_after = False
                environment = self._backend_env_locked()
        if close_after:
            channel.close()
            return {}
        return environment

    def capture_window_baseline(self) -> bool:
        """Capture immutable pre-browser HWND exclusions through the LL-HS5 gate."""

        with self._lock:
            if self._closed or self._channel is None or not self._channel.active:
                return False
        try:
            baseline = self.activation_gate.capture_baseline_handles()
        except Exception:
            self._fail("Private host-sizing window baseline capture failed.")
            return False
        with self._lock:
            if self._closed:
                return False
            self._baseline_handles = baseline
            self._status = PrivateHostSizingProductionStatus.BASELINE_READY
            self._reason = "Private host-sizing window baseline is ready."
        return True

    def authority_launch_id(self) -> str | None:
        """Return the channel-bound launch ID only while authority may be created."""

        with self._lock:
            if self._closed or self._channel is None or not self._channel.active:
                return None
            return self._launch_id

    def activate_after_browser(
        self,
        authority: BrowserLaunchAuthority | None,
        *,
        backend_is_running: Callable[[], bool],
    ) -> bool:
        """Establish exact HWND authority and attach LL-HS4 to the early channel."""

        with self._lock:
            if self._closed or self._channel is None:
                return False
            baseline = self._baseline_handles
        if baseline is None:
            self._mark_ineligible("Private host-sizing window baseline is unavailable.")
            return False
        if authority is None or authority.launch_id != self._launch_id:
            self._mark_ineligible(
                "Exact channel-bound browser launch authority is unavailable."
            )
            return False
        try:
            eligibility = self.activation_gate.collect(
                authority,
                private_enabled=True,
                mode=self.config.mode,
                baseline_handles=baseline,
                shutdown_requested=lambda: (
                    self._shutdown_requested() or not _safe_running(backend_is_running)
                ),
            )
        except Exception:
            self._fail("Private host-sizing authority collection failed.")
            return False
        if not eligibility.eligible or eligibility.window_authority is None:
            self._mark_ineligible(eligibility.reason)
            return False
        try:
            mutation = self.mutation_factory(authority, self.activation_gate)
            coordinator = self.coordinator_factory(
                self.policy_config,
                mutation,
                eligibility.window_authority,
            )
            with self._lock:
                channel = self._channel
            if channel is None or not channel.active:
                raise RuntimeError("Private host-sizing channel is no longer active.")
            coordinator.attach_channel(channel)
            coordinator.start()
        except Exception:
            self._fail("Private host-sizing coordinator startup failed.")
            return False

        with self._lock:
            if self._closed:
                close_after = True
                pending = None
            else:
                self._coordinator = coordinator
                self._status = PrivateHostSizingProductionStatus.ACTIVE
                self._reason = "Private host-sizing coordinator is active."
                pending = self._pending_report
                self._pending_report = None
                close_after = False
                watcher = threading.Thread(
                    target=self._watch_terminal,
                    args=(coordinator,),
                    daemon=True,
                    name="litlaunch-host-sizing-production",
                )
                self._watcher = watcher
                watcher.start()
        if close_after:
            coordinator.shutdown()
            return False
        if pending is not None:
            self._deliver_report(coordinator, pending)
        return True

    def close(self) -> None:
        """Stop policy and transport before backend and artifact cleanup."""

        with self._lock:
            if self._closed:
                return
            self._closed = True
            coordinator = self._coordinator
            channel = self._channel
            watcher = self._watcher
            self._coordinator = None
            self._channel = None
            self._watcher = None
            self._pending_report = None
            self._baseline_handles = None
            if self._status not in {
                PrivateHostSizingProductionStatus.FAILED,
                PrivateHostSizingProductionStatus.INELIGIBLE,
                PrivateHostSizingProductionStatus.TERMINAL,
            }:
                self._reason = "Private host-sizing lifecycle closed."
        if coordinator is not None:
            with suppress(Exception):
                coordinator.shutdown()
        if channel is not None and channel.active:
            channel.close()
        if watcher is not None and watcher is not threading.current_thread():
            watcher.join(timeout=2.0)

    def snapshot(self) -> PrivateHostSizingProductionSnapshot:
        """Return one credential-free internal production lifecycle snapshot."""

        with self._lock:
            runtime_snapshot = self._terminal_snapshot
            coordinator = self._coordinator
            channel = self._channel
            status = self._status
            reason = self._reason
            closed = self._closed
            pending = self._pending_report is not None
        if coordinator is not None:
            try:
                runtime_snapshot = coordinator.snapshot()
            except Exception:
                runtime_snapshot = None
        return PrivateHostSizingProductionSnapshot(
            enabled=True,
            status=status,
            reason=reason,
            closed=closed,
            channel_active=bool(channel is not None and channel.active),
            pending_report=pending,
            accepted_reports=(
                runtime_snapshot.accepted_reports if runtime_snapshot is not None else 0
            ),
            mutation_calls=(
                runtime_snapshot.mutation_calls if runtime_snapshot is not None else 0
            ),
            acknowledgements=(
                runtime_snapshot.acknowledgements if runtime_snapshot is not None else 0
            ),
            policy_state=(
                runtime_snapshot.policy_state.value
                if runtime_snapshot is not None
                else None
            ),
        )

    def _accept_report(self, report: HostSizingReport) -> None:
        if report.source_id != self.source_id:
            return
        with self._lock:
            if self._closed:
                return
            coordinator = self._coordinator
            if coordinator is None:
                pending = self._pending_report
                if pending is None or report.sequence > pending.sequence:
                    self._pending_report = report
                return
        self._deliver_report(coordinator, report)

    def _deliver_report(
        self,
        coordinator: HostSizingRuntimeCoordinator,
        report: HostSizingReport,
    ) -> None:
        try:
            coordinator.consume_accepted_report(report)
        except Exception:
            self._fail("Private host-sizing report delivery failed.")

    def _watch_terminal(self, coordinator: HostSizingRuntimeCoordinator) -> None:
        completed = coordinator.wait()
        if not completed:
            with suppress(Exception):
                coordinator.shutdown()
        try:
            snapshot = coordinator.snapshot()
        except Exception:
            snapshot = None
        with self._lock:
            if self._coordinator is not coordinator:
                return
            self._terminal_snapshot = snapshot
            self._coordinator = None
            self._channel = None
            self._watcher = None
            self._pending_report = None
            self._baseline_handles = None
            self._closed = True
            if completed and snapshot is not None:
                self._status = PrivateHostSizingProductionStatus.TERMINAL
                self._reason = snapshot.last_decision.reason
            else:
                self._status = PrivateHostSizingProductionStatus.FAILED
                self._reason = "Private host-sizing terminal cleanup failed."

    def _backend_env_locked(self) -> dict[str, str]:
        assert self._channel is not None
        return {
            **self._channel.config.as_env(),
            LITLAUNCH_HOST_SIZING_SOURCE_ID: self.source_id,
        }

    def _shutdown_requested(self) -> bool:
        with self._lock:
            return self._closed

    def _mark_ineligible(self, reason: str) -> None:
        self._terminate(PrivateHostSizingProductionStatus.INELIGIBLE, reason)

    def _fail(self, reason: str) -> None:
        self._terminate(PrivateHostSizingProductionStatus.FAILED, reason)

    def _terminate(
        self,
        status: PrivateHostSizingProductionStatus,
        reason: str,
    ) -> None:
        with self._lock:
            if self._closed:
                return
            self._status = status
            self._reason = reason
        self.close()


def _default_mutation_factory(
    authority: BrowserLaunchAuthority,
    gate: PrivateHostSizingActivationGate,
) -> HostSizingMutationCapability:
    verifier = ProcessBoundWindowsWindowAuthorityVerifier(
        authority,
        process_tracker=gate.process_tracker,
        window_provider=gate.window_provider,
    )
    return TrustedWindowsWindowSizer(
        backend=gate.geometry_backend,
        authority_verifier=verifier,
    )


def _default_coordinator_factory(
    policy_config: HostSizingPolicyConfig,
    mutation: HostSizingMutationCapability,
    authority: WindowSizingAuthority,
) -> HostSizingRuntimeCoordinator:
    return HostSizingRuntimeCoordinator(
        policy=HostSizingPolicy(config=policy_config),
        mutation=mutation,
        authority=authority,
    )


def _safe_running(callback: Callable[[], bool]) -> bool:
    try:
        return bool(callback())
    except Exception:
        return False
