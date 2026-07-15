"""Unsupported LL-HS0 Windows geometry and authority measurement harness."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import tempfile
import threading
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from litlaunch._host_sizing_geometry import (
    GeometryApplyResult,
    HeightResizePlan,
    WindowAuthorityProbe,
    WindowAuthorityStatus,
    WindowGeometry,
    WindowsGeometryBackend,
    plan_height_resize,
    wait_for_exact_window_authority,
)
from litlaunch._host_sizing_policy import (
    HostSizingAction,
    HostSizingAuthorityStatus,
    HostSizingPolicy,
    HostSizingPolicyConfig,
    HostSizingPolicyState,
)
from litlaunch._host_sizing_transport import HostSizingReport, SurfaceDimensions
from litlaunch._host_sizing_window import (
    TrustedWindowsWindowSizer,
    WindowsWindowAuthorityVerifier,
    create_window_sizing_authority,
)
from litlaunch.browser_profiles import (
    create_managed_browser_profile,
    with_managed_browser_profile_args,
)
from litlaunch.browsers import BrowserKind, create_default_browser_registry
from litlaunch.config import BrowserChoice
from litlaunch.platforms import PlatformDetector
from litlaunch.windowing import WindowInfo, WindowsWindowProvider, WindowTarget

_TITLE_PATTERN = re.compile(
    r"^(?P<token>LL-HS0-[A-Za-z0-9]+)\|"
    r"vh=(?P<height>\d+)\|vw=(?P<width>\d+)\|dpr=(?P<dpr>[0-9.]+)"
)
_PROBE_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LL-HS0</title>
  <style>
    html, body { margin: 0; min-height: 100%; font-family: system-ui, sans-serif; }
    main { box-sizing: border-box; min-height: 100vh; padding: 24px; }
  </style>
</head>
<body>
  <main><h1>LitLaunch LL-HS0</h1><p>Temporary viewport measurement page.</p></main>
  <script>
    const token = __TOKEN__;
    let pending = false;
    function report() {
      pending = false;
      document.title = `${token}|vh=${window.innerHeight}`
        + `|vw=${window.innerWidth}|dpr=${window.devicePixelRatio}`;
    }
    function schedule() {
      if (!pending) { pending = true; requestAnimationFrame(report); }
    }
    addEventListener("resize", schedule);
    addEventListener("load", schedule);
    schedule();
  </script>
</body>
</html>
"""


@dataclass(frozen=True)
class ViewportObservation:
    """Viewport dimensions reported by the isolated measurement page title."""

    height: int
    width: int
    device_pixel_ratio: float
    title: str


@dataclass(frozen=True)
class SpikeRunResult:
    """Structured result emitted by the unsupported LL-HS0 harness."""

    ok: bool
    browser: str
    browser_executable: str | None
    authority: WindowAuthorityProbe
    viewport_before: ViewportObservation | None
    geometry_before: WindowGeometry | None
    plan: HeightResizePlan | None
    apply_result: GeometryApplyResult | None
    viewport_after: ViewportObservation | None
    measured_error_css: float | None
    dry_run: bool
    reason: str


class ProbePageServer:
    """Short-lived loopback page used only to expose browser viewport evidence."""

    def __init__(self, token: str) -> None:
        self.token = token
        handler = _probe_handler(token)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )

    @property
    def url(self) -> str:
        host, port = self.server.server_address[:2]
        normalized_host = host.decode("ascii") if isinstance(host, bytes) else host
        return f"http://{normalized_host}:{port}/"

    def __enter__(self) -> ProbePageServer:
        self.thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2.0)


def run_spike(
    *,
    browser: BrowserChoice,
    desired_viewport_height: int,
    apply: bool,
    authority_timeout_seconds: float = 10.0,
    viewport_timeout_seconds: float = 5.0,
    pre_apply_delay_seconds: float = 0.0,
    hold_seconds: float = 0.0,
    initial_window_width: int = 1200,
    initial_window_height: int = 800,
    initial_window_left: int | None = None,
    initial_window_top: int | None = None,
    initial_window_state: str = "normal",
    simulate_pre_apply_height_delta: int = 0,
) -> SpikeRunResult:
    """Launch an isolated app window and measure one bounded height plan."""

    platform_info = PlatformDetector().detect()
    if not platform_info.is_windows:
        return _failed_result(browser, "LL-HS0 is available only on Windows.")
    if browser not in {BrowserChoice.EDGE, BrowserChoice.CHROME}:
        return _failed_result(browser, "LL-HS0 requires edge or chrome explicitly.")
    if initial_window_width <= 0 or initial_window_height <= 0:
        return _failed_result(browser, "Initial window dimensions must be positive.")
    if (initial_window_left is None) != (initial_window_top is None):
        return _failed_result(
            browser,
            "Initial window left and top must be supplied together.",
        )
    if initial_window_state not in {
        "normal",
        "minimized",
        "maximized",
        "fullscreen",
    }:
        return _failed_result(browser, "Unsupported initial window state.")

    registry = create_default_browser_registry()
    resolution = registry.resolve(
        browser,
        platform_info,
        prefer_app_mode=True,
        allow_fallback=False,
    )
    capability = resolution.selected
    if capability is None or capability.executable_path is None:
        return _failed_result(browser, resolution.message)

    browser_kind = BrowserKind(browser.value)
    provider = WindowsWindowProvider()
    token = f"LL-HS0-{secrets.token_hex(6)}"
    baseline = provider.capture(WindowTarget(token))
    process: subprocess.Popen[bytes] | None = None
    launched_pids: set[int] = set()

    with tempfile.TemporaryDirectory(
        prefix="litlaunch-hs0-",
        ignore_cleanup_errors=True,
    ) as temporary_root:
        profile = create_managed_browser_profile(Path(temporary_root))
        with ProbePageServer(token) as page:
            adapter = registry.get(browser.value).with_executable_path(
                capability.executable_path
            )
            launch_args = ["--disable-background-mode"]
            if initial_window_state == "normal":
                launch_args.append(
                    f"--window-size={initial_window_width},{initial_window_height}"
                )
                if initial_window_left is not None and initial_window_top is not None:
                    launch_args.append(
                        f"--window-position={initial_window_left},{initial_window_top}"
                    )
            else:
                launch_args.append(f"--start-{initial_window_state}")
            extra_args = with_managed_browser_profile_args(
                tuple(launch_args),
                profile_dir=profile,
                title=token,
            )
            command = adapter.build_launch_command(page.url, extra_args=extra_args)
            try:
                process = subprocess.Popen(
                    command,
                    shell=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                launched_pids.add(process.pid)
                authority = wait_for_exact_window_authority(
                    provider,
                    baseline_handles=(window.handle for window in baseline),
                    browser_kind=browser_kind,
                    title_token=token,
                    launch_pid_provider=lambda: _refresh_process_tree(
                        process.pid,
                        launched_pids,
                    ),
                    timeout_seconds=authority_timeout_seconds,
                )
                if (
                    authority.status != WindowAuthorityStatus.EXACT
                    or authority.window is None
                ):
                    return SpikeRunResult(
                        False,
                        browser.value,
                        capability.executable_path,
                        authority,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        not apply,
                        authority.reason,
                    )

                handle = int(authority.window.handle)
                viewport_before = _wait_for_viewport(
                    provider,
                    authority.window,
                    token=token,
                    timeout_seconds=viewport_timeout_seconds,
                )
                backend = WindowsGeometryBackend()
                geometry_before = backend.capture(handle)
                plan = plan_height_resize(
                    geometry_before,
                    current_viewport_height_css=viewport_before.height,
                    desired_viewport_height_css=desired_viewport_height,
                    device_pixel_ratio=viewport_before.device_pixel_ratio,
                )
                if not apply:
                    return SpikeRunResult(
                        plan.safe,
                        browser.value,
                        capability.executable_path,
                        authority,
                        viewport_before,
                        geometry_before,
                        plan,
                        None,
                        None,
                        None,
                        True,
                        plan.reason,
                    )
                if pre_apply_delay_seconds > 0:
                    time.sleep(pre_apply_delay_seconds)
                if simulate_pre_apply_height_delta:
                    backend.set_outer_size(
                        handle,
                        width=geometry_before.outer.width,
                        height=(
                            geometry_before.outer.height
                            + simulate_pre_apply_height_delta
                        ),
                    )
                    time.sleep(0.2)
                policy = HostSizingPolicy(
                    config=HostSizingPolicyConfig(quiet_period_seconds=0)
                )
                policy.observe_authority(
                    HostSizingAuthorityStatus.EXACT,
                    authority_id=token,
                )
                decision = policy.observe_report(
                    HostSizingReport(
                        protocol=1,
                        launch_id=token,
                        source_id="ll-hs0-owned-probe",
                        sequence=1,
                        device_pixel_ratio=viewport_before.device_pixel_ratio,
                        content=SurfaceDimensions(
                            viewport_before.height,
                            viewport_before.width,
                        ),
                        host_viewport=SurfaceDimensions(
                            viewport_before.height,
                            viewport_before.width,
                        ),
                        desired_host_viewport=SurfaceDimensions(
                            desired_viewport_height
                        ),
                    )
                )
                if decision.action != HostSizingAction.APPLY:
                    return SpikeRunResult(
                        decision.state == HostSizingPolicyState.COMPLETE,
                        browser.value,
                        capability.executable_path,
                        authority,
                        viewport_before,
                        geometry_before,
                        plan,
                        None,
                        viewport_before,
                        0.0,
                        False,
                        decision.reason,
                    )
                window_authority = create_window_sizing_authority(
                    authority_id=token,
                    probe=authority,
                    browser_kind=browser_kind,
                    launch_process_ids=_refresh_process_tree(
                        process.pid,
                        launched_pids,
                    ),
                    baseline=geometry_before,
                    managed_profile=True,
                    app_mode=True,
                )
                mutation_result = TrustedWindowsWindowSizer(
                    backend=backend,
                    authority_verifier=WindowsWindowAuthorityVerifier(provider),
                ).apply(
                    decision=decision,
                    authority=window_authority,
                )
                acknowledgement = policy.acknowledge_apply(
                    applied=mutation_result.acknowledgement_succeeded,
                    reason=mutation_result.reason,
                )
                mutation_plan = mutation_result.plan or plan
                apply_result = GeometryApplyResult(
                    applied=mutation_result.acknowledgement_succeeded,
                    reason=mutation_result.reason,
                    baseline=mutation_result.baseline,
                    pre_apply=mutation_result.pre_apply or geometry_before,
                    after=mutation_result.after,
                    plan=mutation_plan,
                )
                if acknowledgement.state != HostSizingPolicyState.COMPLETE:
                    return SpikeRunResult(
                        False,
                        browser.value,
                        capability.executable_path,
                        authority,
                        viewport_before,
                        geometry_before,
                        plan,
                        apply_result,
                        None,
                        None,
                        False,
                        apply_result.reason,
                    )
                viewport_after = _wait_for_viewport(
                    provider,
                    authority.window,
                    token=token,
                    timeout_seconds=viewport_timeout_seconds,
                    minimum_height_change_from=viewport_before.height,
                )
                measured_error = abs(
                    viewport_after.height - plan.expected_viewport_height_css
                )
                ok = measured_error <= 1.0
                if hold_seconds > 0:
                    time.sleep(hold_seconds)
                return SpikeRunResult(
                    ok,
                    browser.value,
                    capability.executable_path,
                    authority,
                    viewport_before,
                    geometry_before,
                    plan,
                    apply_result,
                    viewport_after,
                    measured_error,
                    False,
                    (
                        "Measured viewport matched the bounded native geometry plan."
                        if ok
                        else "Measured viewport did not match the native geometry plan."
                    ),
                )
            except Exception as exc:
                return _failed_result(
                    browser,
                    f"LL-HS0 probe failed: {type(exc).__name__}: {exc}",
                    browser_executable=capability.executable_path,
                )
            finally:
                if process is not None:
                    _stop_owned_browser_process(process)


def result_as_dict(result: SpikeRunResult) -> dict[str, Any]:
    """Return deterministic JSON-safe spike evidence."""

    value = asdict(result)
    value["authority"]["status"] = result.authority.status.value
    if value["geometry_before"] is not None:
        geometry_before = result.geometry_before
        if geometry_before is not None:
            value["geometry_before"]["state"] = geometry_before.state.value
    apply_result = result.apply_result
    if apply_result is not None:
        for name in ("baseline", "pre_apply", "after"):
            geometry = getattr(apply_result, name)
            if geometry is not None:
                value["apply_result"][name]["state"] = geometry.state.value
    return value


def build_parser() -> argparse.ArgumentParser:
    """Build the unsupported spike parser without touching public CLI help."""

    parser = argparse.ArgumentParser(
        prog="python -m litlaunch._host_sizing_spike",
        description=(
            "Unsupported LL-HS0 Windows app-window authority and geometry probe. "
            "Dry-run is the default; --apply performs one guarded resize."
        ),
    )
    parser.add_argument("--browser", choices=("edge", "chrome"), required=True)
    parser.add_argument(
        "--desired-viewport-height",
        type=int,
        required=True,
        metavar="CSS_PX",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--authority-timeout", type=float, default=10.0)
    parser.add_argument("--viewport-timeout", type=float, default=5.0)
    parser.add_argument("--pre-apply-delay", type=float, default=0.0)
    parser.add_argument("--hold-seconds", type=float, default=0.0)
    parser.add_argument("--initial-window-width", type=int, default=1200)
    parser.add_argument("--initial-window-height", type=int, default=800)
    parser.add_argument("--initial-window-left", type=int)
    parser.add_argument("--initial-window-top", type=int)
    parser.add_argument(
        "--initial-window-state",
        choices=("normal", "minimized", "maximized", "fullscreen"),
        default="normal",
    )
    parser.add_argument(
        "--simulate-pre-apply-height-delta",
        type=int,
        default=0,
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the unsupported harness and emit one JSON evidence object."""

    args = build_parser().parse_args(argv)
    result = run_spike(
        browser=BrowserChoice(args.browser),
        desired_viewport_height=args.desired_viewport_height,
        apply=args.apply,
        authority_timeout_seconds=args.authority_timeout,
        viewport_timeout_seconds=args.viewport_timeout,
        pre_apply_delay_seconds=args.pre_apply_delay,
        hold_seconds=args.hold_seconds,
        initial_window_width=args.initial_window_width,
        initial_window_height=args.initial_window_height,
        initial_window_left=args.initial_window_left,
        initial_window_top=args.initial_window_top,
        initial_window_state=args.initial_window_state,
        simulate_pre_apply_height_delta=args.simulate_pre_apply_height_delta,
    )
    print(json.dumps(result_as_dict(result), indent=2, sort_keys=True))
    return 0 if result.ok else 1


def _probe_handler(token: str) -> type[BaseHTTPRequestHandler]:
    page = _PROBE_HTML.replace("__TOKEN__", json.dumps(token)).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract.
            if self.path != "/":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def _parse_viewport(title: str, *, token: str) -> ViewportObservation | None:
    match = _TITLE_PATTERN.match(title.strip())
    if match is None or match.group("token") != token:
        return None
    return ViewportObservation(
        height=int(match.group("height")),
        width=int(match.group("width")),
        device_pixel_ratio=float(match.group("dpr")),
        title=title,
    )


def _wait_for_viewport(
    provider: WindowsWindowProvider,
    window: WindowInfo,
    *,
    token: str,
    timeout_seconds: float,
    minimum_height_change_from: int | None = None,
) -> ViewportObservation:
    deadline = time.monotonic() + timeout_seconds
    target = WindowTarget(token)
    last: ViewportObservation | None = None
    while time.monotonic() <= deadline:
        for observed in provider.capture(target):
            if observed.handle != window.handle:
                continue
            parsed = _parse_viewport(observed.title, token=token)
            if parsed is None:
                continue
            last = parsed
            if (
                minimum_height_change_from is None
                or parsed.height != minimum_height_change_from
            ):
                return parsed
        time.sleep(0.05)
    if last is not None:
        return last
    raise RuntimeError("Timed out waiting for browser viewport measurement.")


def _refresh_process_tree(root_pid: int, known: set[int]) -> tuple[int, ...]:
    known.update(_process_tree_pids(root_pid))
    return tuple(sorted(known))


def _process_tree_pids(root_pid: int) -> set[int]:
    """Return the launched browser process tree through a bounded PowerShell query."""

    if os.name != "nt":
        return {root_pid}
    script = (
        "$items = Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,ParentProcessId; "
        f"$owned = [System.Collections.Generic.HashSet[uint32]]::new(); "
        f"[void]$owned.Add([uint32]{root_pid}); "
        "do { $changed = $false; foreach ($item in $items) { "
        "if ($owned.Contains([uint32]$item.ParentProcessId) -and "
        "-not $owned.Contains([uint32]$item.ProcessId)) { "
        "[void]$owned.Add([uint32]$item.ProcessId); $changed = $true } } "
        "} while ($changed); $owned | Sort-Object"
    )
    try:
        completed = subprocess.run(
            ("powershell.exe", "-NoProfile", "-Command", script),
            check=True,
            capture_output=True,
            text=True,
            timeout=3.0,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return {root_pid}
    pids = {
        int(line.strip())
        for line in completed.stdout.splitlines()
        if line.strip().isdigit()
    }
    pids.add(root_pid)
    return pids


def _stop_owned_browser_process(
    process: subprocess.Popen[bytes],
) -> None:
    if os.name == "nt":
        subprocess.run(
            ("taskkill.exe", "/PID", str(process.pid), "/T", "/F"),
            check=False,
            capture_output=True,
            text=True,
        )
        try:
            process.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3.0)
        return

    process.terminate()
    try:
        process.wait(timeout=3.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3.0)


def _failed_result(
    browser: BrowserChoice,
    reason: str,
    *,
    browser_executable: str | None = None,
) -> SpikeRunResult:
    return SpikeRunResult(
        False,
        browser.value,
        browser_executable,
        WindowAuthorityProbe(
            WindowAuthorityStatus.UNSUPPORTED,
            None,
            (),
            reason,
        ),
        None,
        None,
        None,
        None,
        None,
        None,
        True,
        reason,
    )


if __name__ == "__main__":  # pragma: no cover - exercised manually.
    raise SystemExit(main())
