# LitLaunch DOMINATE Audit

> INTERNAL / HISTORICAL AUDIT DOCUMENTATION
>
> This document preserves pre-release audit context. It is not part of the
> stable public LitLaunch documentation surface.

## 1. Executive Summary

Yes, LitLaunch is positioned well, but it is not yet inevitable.

The foundation is unusually disciplined for a pre-alpha runtime package: explicit config, owned process boundaries, shell-free commands, platform/browser capability layers, graceful shutdown, console UX, CLI, and tests. The important thing: LitLaunch already has a point of view. It is not “a script that opens Streamlit.” It is a runtime ownership layer.

To dominate, the next phase must prove three things:

1. It wraps Streamlit without reducing Streamlit.
2. It handles ugly real-world desktop/runtime failure modes better than app teams do themselves.
3. It gives developers trust quickly through diagnostics, docs, examples, and predictable behavior.

The biggest missing piece is not another feature. It is the operational contract: what happens when ports collide, Streamlit crashes, browser detection is weird, a packaged app has no repo tree, shutdown hooks fail, a webapp window closes, or support needs a sanitized report.

## 2. What Already Makes LitLaunch Strong

- Strong safety posture: no `shell=True`, owned-process-only termination, no killing by process name/port owner.
- Clean object boundaries:
  - `LauncherConfig`
  - `StreamlitCommandBuilder`
  - `PortManager`
  - `ProcessManager`
  - `HealthChecker`
  - `BrowserRegistry`
  - `RuntimeSession`
  - `LauncherRuntime`
- Good direction on lifecycle ownership: `StreamlitLauncher` creates, `RuntimeSession` owns.
- stdlib-first design is a real advantage. Less installation friction, fewer supply-chain concerns.
- Browser resolution is capability-based instead of “try random paths and hope.”
- Graceful shutdown is opt-in and safe for plain `streamlit run`.
- CLI is thin over the runtime API, which is correct.
- Console renderer is dependency-free and already thinks about redaction.
- Tests are broad and fake-driven, which is exactly right for process/browser/port logic.
- Public API is now more discoverable for dependency-injection users.
- Project philosophy is visible in code. That matters.

## 3. What Is Still Missing From “Runtime Layer” Completeness

Core missing runtime areas:

- Window-close detection for webapp/app-mode.
- A stable long-running CLI lifecycle contract.
- Real runtime diagnostics/reporting.
- Real smoke tests against a live Streamlit app.
- Streamlit compatibility passthrough beyond repeated `--streamlit-flag` / `--app-arg`.
- Better crash/death detection after launch.
- Runtime session status refresh: current session state is mostly event-driven, not an active runtime view.
- Clear packaged-app story.
- Browser launch profiles, especially app-mode isolation choices.
- Config/profile loading from files.
- Support bundles for user issue reports.
- Better health failure explanations: missing Streamlit, bad app import, app crash, port race, health timeout all need distinct diagnostics.

## 4. Hardening Still Needed

Blockers before public alpha:

- Remove `__pycache__` artifacts from `src/litlaunch` if they are present in the working tree or package build inputs. Even if ignored, seeing them in source tree listings is a release hygiene smell.
- Add CI. No public alpha without CI.
- Add live smoke tests for the minimal example app.
- Verify actual wheel contents.
- Verify `py.typed` in built wheel, not only editable install.
- Add `twine check` or equivalent metadata validation.
- Add Windows path-with-spaces smoke coverage.
- Add Streamlit-not-installed failure behavior.
- Add app-import-crash failure behavior.
- Add browser-not-found behavior through CLI.
- Add IPv6 shutdown URL handling. `ShutdownClient` appears to format `http://{host}:{port}` directly; `::1` needs bracket handling like app/health URLs.
- Decide whether `StreamlitLauncher.start()` should catch all exceptions into failure sessions. It is user-friendly, but it can hide programmer errors in library integration.

Medium-priority hardening:

- More exact browser resolution policy for explicit browser requests.
- More robust shutdown endpoint lifecycle cleanup.
- Validate timeout ranges.
- Redact command output if future args may contain secrets.
- Add `cwd` and `env` support deliberately, not accidentally.
- Add type checking with `mypy` or `pyright` before beta.

## 5. Streamlit Compatibility Gaps

LitLaunch must support three layers:

- Typed first-class options for common launch needs.
- Safe pass-through for any Streamlit CLI option.
- App args after `--`.

Current pass-through is good but not complete enough to claim “full Streamlit compatibility.”

Needed:

- Raw passthrough syntax in CLI:
  - `litlaunch run app.py -- --theme.base dark --server.fileWatcherType none`
  - or `litlaunch run app.py --streamlit --server.fileWatcherType none -- --my-app-arg x`
- Explicit split between Streamlit args and app args.
- Preserve exact ordering.
- Support flags with repeated keys.
- Support flags with no values.
- Support `--flag=value` and `--flag value`.
- Document LitLaunch defaults and override rules.
- Test against actual Streamlit invocation behavior.

Do not try to model every Streamlit option as typed config. That becomes a maintenance trap.

## 6. Developer Experience Gaps

Developers need to trust it in five minutes.

Missing DX pieces:

- A “why LitLaunch?” page with concrete pain points:
  - no shell strings
  - safe process ownership
  - app-mode
  - graceful shutdown
  - diagnostics
  - CLI/runtime parity
- A “first app” tutorial.
- A “retrofit existing app” tutorial.
- A “serious app structure” guide.
- A clear failure-mode guide.
- A CLI command that explains environment readiness.
- Copy-paste examples for:
  - browser mode
  - webapp mode
  - graceful shutdown
  - custom flags
  - profiles
  - packaged-ish usage
- A compatibility statement: “If it runs with `streamlit run`, LitLaunch should be able to run it.”

## 7. CLI Experience Review

Before alpha, add:

- `litlaunch inspect` or `litlaunch report`
  - local environment, platform, browser capability, Streamlit availability, example app status.
- `litlaunch command app.py ...`
  - print the exact Streamlit command without launching.
- `litlaunch run app.py --dry-run`
  - show backend/browser plan.
- `litlaunch run app.py --no-open`
  - start backend only.
- `litlaunch run app.py --wait/--no-wait`
  - explicit lifecycle mode.
- `litlaunch browsers --verbose`
  - include detection paths and fallback chain.
- `litlaunch example --run`
  - optional, only if source fixture exists.

Wait until later:

- `init`
- `profile create`
- `package`
- dashboard server
- shortcut generation
- installer helpers

CLI naming suggestion:

- Avoid `doctor`; it is overused.
- Good names:
  - `litlaunch inspect`
  - `litlaunch report`
  - `litlaunch trace`
  - `litlaunch readiness`
- Best fit: `litlaunch inspect`
  - It sounds local, factual, non-magical, and not cutesy.

## 8. Console UX Review

The current console layer is good enough as a foundation. To feel premium:

- Use phase grouping:
  - Configure
  - Backend
  - Health
  - Browser
  - Runtime
  - Shutdown
- Include elapsed time per phase in verbose mode.
- Show resolved URL clearly.
- Show browser selection and fallback chain.
- Show shutdown hook progress.
- Show “owned process PID” but never imply browser ownership.
- Add `--quiet`, `--verbose`, `--no-color` consistently across all commands.
- Add `--json` later for automation.
- In failure output, give next action:
  - “Streamlit did not become healthy. Run with `--verbose` or `litlaunch inspect`.”
- Keep color restrained. The premium feel is clarity, not confetti.

Do not add Rich yet. The stdlib renderer is a product advantage.

## 9. Diagnostics / Inspector Strategy

The local-only diagnostics dashboard idea is strong if it stays boring, secure, and support-focused.

Recommended command:

- `litlaunch inspect`
  - terminal report by default
- `litlaunch inspect --html`
  - writes/serves local HTML report
- `litlaunch inspect --serve`
  - local-only browser view

Alternative names:

- `litlaunch lens`
- `litlaunch trace`
- `litlaunch report`

Best: `inspect`.

What it should include:

- LitLaunch version.
- Python version/executable.
- OS/architecture.
- Streamlit import/version.
- PATH browser detection results.
- Browser fallback chain.
- Port availability check.
- Example app availability.
- Config validation summary.
- Built Streamlit command with redaction.
- App path/cwd status.
- Health endpoint plan.
- Shutdown endpoint capability.
- Recent launch events if run from a session.
- Copyable sanitized bundle.

What it should avoid:

- Raw environment dump.
- Tokens.
- Full PATH by default.
- Cookies/browser profile paths unless sanitized.
- Network exposure beyond loopback.
- JavaScript-heavy UI.
- Persistent server unless explicitly requested.
- “Fix it for me” actions in early versions.

Architecture:

- `DiagnosticsReport` dataclass.
- `DiagnosticCollector`.
- Renderers:
  - text
  - JSON
  - HTML
- Local server only for viewing the static/sanitized report.

This could become a killer differentiator.

## 10. Window Monitoring Strategy

This is the big runtime differentiator.

Goal: app-mode window closes -> graceful shutdown request -> wait -> terminate owned backend fallback.

Clean architecture:

- `WindowMonitor` protocol.
- `WindowMonitorResult`.
- `WindowIdentity` / `BrowserWindowTarget`.
- Windows implementation first.
- No browser process ownership.
- Monitor should produce events, not kill anything.
- `RuntimeSession` consumes events and decides whether to stop backend.
- CLI `run` can choose:
  - wait for backend
  - wait for app window
  - wait for either

Windows strategy:

- For Chromium app-mode, launch with a distinctive title and/or app URL.
- Detect top-level windows associated with browser executable/class/title.
- Track window creation after launch time.
- Do not assume browser PID ownership.
- When all matching windows close, request graceful shutdown.

Hard part:

- Existing browser processes can host app-mode windows.
- Titles can change.
- Multiple windows can match.
- Chromium may reuse process trees.
- Browser profile behavior differs.

Future macOS/Linux:

- macOS likely needs AppleScript/accessibility or `osascript`-style discovery, which raises permission complexity.
- Linux varies wildly: X11 vs Wayland. Keep later/provisional.
- Design the protocol now; implement Windows first.

Do not bolt this into `BrowserLauncher`. It belongs beside `RuntimeSession` as an optional observer.

## 11. Shutdown Runtime Strategy

Current framework is good.

Later support:

- Hook timeouts.
- Async hook support? Maybe, but do not rush.
- Hook phases:
  - pre_shutdown
  - cleanup
  - final
- Hook result serialization.
- Hook output captured in diagnostics.
- “Shutdown requested” state exposed to the app.
- Optional Streamlit UI indicator.
- Endpoint close after first valid request.
- Configurable graceful timeout.
- App-triggered self-shutdown helper.
- Idempotent hook registry with run-once semantics, already started.

Keep out of scope:

- Killing browser processes.
- Remote shutdown.
- Non-loopback shutdown by default.
- Secret-bearing logs.
- Full lifecycle framework inside app code.
- Replacing Streamlit state management.

Concern:

- The endpoint currently runs hooks but does not itself exit the app. That is okay for now because the launcher fallback terminates the backend, but docs should be very clear: hooks prepare shutdown; LitLaunch still owns final process stop.

## 12. Runtime Profiles / Config Strategy

Yes, support profiles, but keep them tiny.

Representation:

```python
LaunchProfile(
    name="webapp",
    mode=LaunchMode.WEBAPP,
    browser=BrowserChoice.AUTO,
    streamlit_flags={...},
    extra_browser_args=(...),
)
```

Rules:

- Profiles are data, not behavior.
- Profile + override -> `LauncherConfig`.
- Built-in profiles should be minimal:
  - `dev`
  - `browser`
  - `webapp`
  - `local_app`
- Avoid `kiosk-ish` until you know what “kiosk” means operationally.
- `packaged` should be docs/example first, not built-in behavior yet.

Config file:

- Later: `litlaunch.toml`
- Do not require it.
- CLI should support `--profile NAME`.
- Python API should remain first-class.

## 13. App Architecture Guidance

LitLaunch should bless a standard without requiring it.

Minimum:

```text
my_app/
  app.py
  requirements.txt
```

Better:

```text
my_app/
  app.py
  pyproject.toml
  src/
    my_app/
      __init__.py
      pages/
      services/
      settings.py
```

Best:

```text
my_app/
  pyproject.toml
  litlaunch.toml
  src/
    my_app/
      __init__.py
      streamlit_app.py
      runtime.py
      config.py
      services/
      resources/
      ui/
  tests/
  README.md
```

Best-practice app code:

```python
from litlaunch import LauncherRuntime

runtime = LauncherRuntime.from_env()

@runtime.shutdown_hook(label="Closing resources")
def close_resources():
    ...

runtime.enable_shutdown_endpoint()
```

Guidance should say:

- Keep Streamlit UI thin.
- Put resources behind cleanup functions.
- Avoid global side effects where possible.
- Make app startup import-safe.
- Keep secrets out of CLI flags.

## 14. Packaging Strategy

LitLaunch should not own packaging. It should provide recipes.

Docs/examples needed:

- PyInstaller:
  - launching bundled Streamlit app
  - resolving app path in frozen mode
  - browser mode vs app-mode
  - shutdown hooks
- Nuitka:
  - same shape, less emphasis initially.
- uv:
  - dev workflow
  - `uv run litlaunch run app.py`
- pipx:
  - installing CLI tools.
- Windows shortcuts:
  - `.lnk` to `litlaunch run ...`
  - working directory concerns.
- Desktop-style distribution:
  - “what LitLaunch does”
  - “what your packager does”
  - “what your installer does”

Do not add package-builder commands yet.

## 15. PyPI / Public Alpha Readiness

Blocking before TestPyPI:

- Clean source tree of `__pycache__`.
- CI passing on Windows/Linux/macOS.
- Build wheel/sdist validation.
- Metadata validation.
- Basic docs site or at least polished README.
- License verified.
- Version policy documented.
- Install from built wheel and run CLI.
- `litlaunch inspect` or at least `platform`/`browsers` reliable.
- Live minimal Streamlit smoke test in CI somewhere.

Nice-to-have:

- `litlaunch run --dry-run`.
- JSON diagnostics.
- Basic `litlaunch.toml`.
- More examples.

Blocking before PyPI public alpha:

- TestPyPI install verified.
- Windows app-mode manual verification.
- Browser fallback manual matrix.
- Security note for shutdown endpoint.
- Troubleshooting guide.
- Streamlit version compatibility note.

## 16. Testing / CI Strategy

Before alpha:

OS matrix:

- Windows latest
- Ubuntu latest
- macOS latest

Python matrix:

- 3.10
- 3.12
- 3.14 if available in CI
- Maybe 3.11/3.13 later

Fake/injected tests should remain for:

- process lifecycle
- browser launch
- browser detection
- shutdown client
- window monitoring
- port conflicts

Real smoke tests should cover:

- package import from wheel
- CLI version
- CLI platform
- CLI browsers
- Streamlit command build
- minimal Streamlit app launch
- health endpoint becomes healthy
- graceful shutdown fallback

Manual/optional tests:

- Edge app-mode on Windows
- Chrome app-mode on macOS/Linux
- packaged app recipes
- actual window-close monitoring once implemented

## 17. Security Review

Current security posture is good, but the next features increase risk.

Shutdown token:

- Good: unguessable token, loopback endpoint, no logging.
- Improve: ensure token redaction covers all diagnostics.
- Improve: do not expose `_shutdown_client` in normal reports.
- Improve: bracket IPv6 shutdown client URLs.

Loopback endpoint:

- Good: loopback-only.
- Improve: reject non-loopback in `ShutdownConfig` or separate “config can represent” from “server may bind.”
- Consider endpoint shutdown after first successful request.

Browser commands:

- Good: argument tuples, `shell=False`.
- Risk: `extra_browser_args` are passed through. That is okay, but docs should say these are powerful local browser flags.
- Never interpolate browser args into display strings without quoting/redaction strategy.

User Streamlit flags:

- They may contain secrets.
- Diagnostic command rendering needs redaction hooks.
- Consider known secret-ish patterns: token, key, password, secret.

Diagnostics dashboard:

- Biggest future risk.
- Must be local-only.
- Must not dump env.
- Must not include tokens.
- Must have explicit “copy sanitized report” model.

## 18. Performance / Optimization Review

No obvious performance problem yet.

Potential concerns:

- Browser detection scans PATH and common paths repeatedly. Cheap enough now.
- Platform detection cheap.
- Health polling fine.
- No caching needed yet except maybe within one launcher run.

Do not over-optimize.

Potential improvement:

- `BrowserRegistry.detect_all()` could cache per process only if detection becomes expensive.
- Console output should stay minimal by default.
- Window monitoring must be event/poll balanced; avoid hot polling.

## 19. API Stability Review

Stable enough to keep public:

- `LauncherConfig`
- `LaunchMode`
- `BrowserChoice`
- `StreamlitLauncher`
- `RuntimeSession`
- `LauncherRuntime`
- `ShutdownHook`
- `ShutdownHookRegistry`
- `ShutdownResult`
- `PortManager`
- `ProcessManager`
- `ManagedProcess`
- `HealthChecker`
- `StreamlitCommandBuilder`
- core exceptions

Mark provisional:

- `Diagnostics`
- browser adapter internals
- `BrowserResolution` policy details
- console theme internals
- lifecycle event enum completeness
- shutdown endpoint internals
- platform capability flags

Consider hiding before alpha:

- low-level browser adapter classes unless you want third-party adapters early.
- internal protocols from top-level, currently not exported, good.
- anything token-bearing.

## 20. Documentation Strategy

Priority docs:

1. README: concise, already decent.
2. Quickstart.
3. CLI reference.
4. Python API guide.
5. Graceful shutdown guide.
6. Streamlit compatibility and passthrough guide.
7. Troubleshooting guide.
8. Security model.
9. Packaging recipes.
10. Architecture notes.

Do not build giant docs too early.

The key is trust. Every doc should answer: “What does LitLaunch own, and what does it refuse to own?”

## 21. Naming / Positioning

LitLaunch is a good package name.

Positioning should be:

> LitLaunch is a lightweight runtime layer for serious Streamlit applications.

Not:

> A launcher for Streamlit.

“Launcher” sounds like a script. “Runtime layer” correctly implies lifecycle, process ownership, diagnostics, shutdown, browser orchestration, and packaging-adjacent support.

Tagline options:

- “The dependable runtime layer for Streamlit apps.”
- “Launch, observe, and shut down Streamlit apps cleanly.”
- “A small runtime spine for serious Streamlit projects.”

## 22. DOMINATE Roadmap

### Must Do Before Public Alpha

- Remove source-tree cache artifacts.
- Add CI.
- Add wheel/sdist build verification.
- Add real minimal Streamlit smoke test.
- Add `litlaunch run --dry-run`.
- Add `litlaunch command`.
- Add better Streamlit passthrough.
- Add `litlaunch inspect` text report.
- Add security/troubleshooting docs.
- Add Streamlit-not-installed and app-crash diagnostics.
- Fix IPv6 shutdown client URL formatting.
- Clarify explicit browser fallback policy.
- Verify TestPyPI install.

### Should Do Before Beta

- `litlaunch.toml`.
- Profiles.
- JSON diagnostics output.
- HTML diagnostics report.
- More examples.
- Windows app-mode manual test matrix.
- Browser fallback docs.
- Packaged app recipes.
- Type checking in CI.
- Coverage thresholds or at least coverage reporting.

### Killer Differentiators

- Window-close monitoring for Chromium app-mode on Windows.
- Local-only diagnostics inspector.
- Copyable sanitized support bundle.
- First-class graceful shutdown patterns.
- Serious-app structure guide.
- Packaged desktop recipe that actually works.
- “If it runs with Streamlit, LitLaunch can run it” compatibility contract.

### Later / Not Yet

- Packaging commands.
- Installer generation.
- Rich/Textual console.
- Remote dashboards.
- Browser automation.
- macOS/Linux window monitoring.
- Plugin architecture.
- Full Streamlit config parser.
- Deep app introspection.

## 23. Brutal Truths

- The package is good, but the ecosystem will not care until the first failure-mode story is excellent.
- “Runtime layer” means support burden. Diagnostics are not optional; they are the product.
- Window monitoring will be harder than it looks. Do it carefully or it will become the first brittle subsystem.
- Packaging will tempt scope creep. Resist. Provide recipes, not ownership.
- Streamlit passthrough must become more complete before making strong compatibility claims.
- Public API is already a little wide for pre-alpha. Mark provisional surfaces clearly.
- The current CLI is useful but not yet delightful.
- The example app is fine as a fixture, but not enough as a sales/demo story.
- The shutdown framework is promising, but until app exit behavior is documented precisely, users may misunderstand what it guarantees.
- The codebase has a strong philosophy. The risk now is not bad code. The risk is adding good ideas too fast without turning them into clean contracts.

**Concrete Next Passes**

1. **Pass 12: Compatibility Contract**
   - Raw Streamlit passthrough.
   - `--dry-run`.
   - `litlaunch command`.
   - Better failure messages for missing Streamlit/app crash.

2. **Pass 13: Inspect Report**
   - Text diagnostics.
   - Sanitized report dataclass.
   - JSON output.
   - No dashboard yet.

3. **Pass 14: CI + Build Release Hygiene**
   - GitHub Actions.
   - wheel/sdist validation.
   - TestPyPI rehearsal.
   - remove cache artifacts.

4. **Pass 15: Real Smoke Harness**
   - live minimal Streamlit launch.
   - health check.
   - graceful stop.
   - Windows-first, then OS matrix.

5. **Pass 16: Window Monitor Design Spike**
   - design only first.
   - Windows proof-of-concept second.
   - no browser ownership, no killing.
   
   
Window-Monitoring
# LitLaunch Window Monitor Recon Report

## 1. Executive Summary

Yes, window monitoring is feasible and worth designing now, but I would not make it default in the first implementation. The safest first shape is **Windows-only, Chromium app-mode-only, opt-in, fake-tested, observation-only**.

The proven RoleThread lesson is sharp: **browser process ownership is the wrong abstraction**. Edge/Chrome may reuse processes, share PIDs across normal and app-mode windows, or detach from the launcher process. The reliable desktop signal is the disappearance of a specific observed app-window handle.

Recommended first implementation shape:

- Add a `litlaunch.windowing` subsystem with protocols/data types.
- Implement `NoopWindowMonitor` and a Windows Chromium HWND monitor.
- Attach monitoring to `RuntimeSession`, not to `BrowserLauncher`.
- Let monitor emit “window closed” and let `RuntimeSession.stop()` handle graceful shutdown and fallback.
- Keep browser processes completely outside ownership.

## 2. RoleThread Behavior Observed

RoleThread currently does several things well:

- Launches Edge app-mode with Chromium-style `--app=<url>`.
- Waits for Streamlit health before launching/monitoring the browser window.
- Treats browser/window readiness as separate from backend readiness.
- Captures visible Windows HWND metadata instead of trusting browser PIDs.
- Filters windows by:
  - title containing the app title
  - title excluding normal Edge browser chrome
  - class name starting with `Chrome_WidgetWin`
  - process image name matching Edge where available
- Supports a native Win32 path through `ctypes`.
- Has a PowerShell fallback probe for tests/fallback behavior.
- Captures baseline window handles and tracks only new handles after launch.
- Rejects transient handles by requiring the candidate to still exist after another poll.
- Tracks the exact selected handle until it disappears.
- Handles normal browser mode as unsupported for close detection.
- On observed close, requests tokened graceful shutdown.
- If graceful shutdown times out, falls back to terminating only the owned backend process.
- If webapp window never appears, terminates only the owned backend process.
- Tests many important edge cases: baseline handles, newest handle preference, transient handle rejection, unsupported mode, health failure, shutdown timeout, no-window timeout.

The best idea to generalize: **detect the desktop window, not the browser process**.

## 3. RoleThread Coupling to Avoid

Do not carry these into LitLaunch:

- RoleThread names, titles, strings:
  - `RoleThread`
  - `RoleThread Lite`
  - `APP_DATA_DIR_NAME`
  - `--rolethread-run-streamlit`
  - RoleThread preference/log/app-root assumptions
- Edge-only naming in generic API.
- Packaged launcher assumptions.
- Inno/PyInstaller logic.
- RoleThread-specific cloud sync shutdown messaging.
- App-specific log format like `lifecycle=cloud_sync_shutdown_timeout`.
- Assumption that Edge is always the adapter.
- Hardcoded app title matching.
- Shutdown behavior that is coupled to RoleThread’s cleanup operations.
- Any port-owner cleanup logic.
- Any process-name killing.
- PowerShell string copied from RoleThread.

RoleThread’s behavior should inform the design, not become the code.

## 4. Browser/App-Mode Observations

Chromium app-mode gives us:

- A standalone-looking window for a URL.
- A predictable `--app=<url>` launch style.
- Window classes on Windows that commonly look like `Chrome_WidgetWin_*`.
- A title surface that often reflects the web app/page title.

Things not to over-trust:

- Browser process IDs.
- Browser subprocess lifetimes.
- The `Popen` object returned from launching Edge/Chrome.
- Window title being immediately available.
- Window title remaining stable forever.
- Exact browser executable process name in all installs/channels.
- A one-to-one relationship between command launch and a new browser process.
- App-mode always creating a detectable native window in headless/RDP/locked sessions.

Practical contract: **app-mode improves observability but does not create ownership**.

## 5. Ownership Contract

**BrowserLauncher owns:**
- Building browser launch commands.
- Starting browser/app-mode launch command.
- Returning `BrowserLaunchResult`.
- Never storing, killing, or managing browser process handles.

**WindowMonitor observes:**
- Existing windows before launch, if asked.
- Candidate app-mode windows after launch.
- A selected target window handle.
- Close/disappearance of that handle.
- Backend process exit as a competing lifecycle signal.
- It does not request shutdown directly in early phases.

**RuntimeSession owns:**
- The Streamlit backend `ManagedProcess`.
- Graceful shutdown request through `_shutdown_client`.
- Terminate/kill fallback for the owned backend only.
- Lifecycle events.

**Who triggers graceful shutdown:**
- The component coordinating session wait behavior should call `session.stop()` when monitor reports window closed.
- I would implement that as `RuntimeSession.monitor_window(...)` or a helper function using the session, not inside `WindowMonitor`.

**Must never happen:**
- No browser kill.
- No kill by process name.
- No kill by browser PID.
- No kill by port owner.
- No assuming Edge/Chrome child process is owned.
- No shutdown-token logging.
- No window monitoring in normal browser mode by default.

## 6. Proposed Architecture

Suggested package:

```text
src/litlaunch/windowing/
  __init__.py
  base.py
  noop.py
  windows.py
```

Core types:

```python
WindowMonitorStatus
- UNSUPPORTED
- WAITING_FOR_WINDOW
- WINDOW_OBSERVED
- WINDOW_CLOSED
- BACKEND_EXITED
- TIMEOUT
- UNAVAILABLE
- ERROR

WindowInfo
- handle: str
- pid: int | None
- title: str
- class_name: str
- process_name: str | None

WindowTarget
- title: str
- url: str | None
- browser_kind: BrowserKind | None
- app_mode: bool = True
- baseline_handles: tuple[str, ...] = ()

WindowMonitorConfig
- appear_timeout_seconds: float = 60.0
- poll_interval_seconds: float = 1.0 or 2.0
- stable_poll_count: int = 2
- title_match: literal/exact/contains maybe later
- require_chromium_class: bool = True

WindowMonitorEvent
- status: WindowMonitorStatus
- message: str
- timestamp: float
- window: WindowInfo | None

WindowMonitorResult
- supported: bool
- observed: bool
- closed: bool
- status: WindowMonitorStatus
- message: str
- target: WindowInfo | None
- events: tuple[WindowMonitorEvent, ...]
```

Monitor boundary:

```python
class WindowMonitor(Protocol):
    def capture(self, target: WindowTarget) -> tuple[WindowInfo, ...] | None: ...
    def wait_for_close(
        self,
        target: WindowTarget,
        *,
        backend_is_running: Callable[[], bool],
        config: WindowMonitorConfig,
    ) -> WindowMonitorResult: ...
```

Implementations:

- `NoopWindowMonitor`: returns unsupported cleanly.
- `WindowsChromiumWindowMonitor`: native `ctypes` HWND enumeration.
- Optional later: `WindowsPowerShellWindowProbe`, but I would avoid PowerShell in Pass 2 unless native APIs are blocked.

Important design note: make capture/poll providers injectable so most tests do not need Windows.

## 7. RuntimeSession Integration Plan

Do not put monitor logic into `BrowserLauncher`. Browser launch has already done its job after the command starts.

Recommended phases:

1. `RuntimeSession.monitor_window(monitor, target, config) -> WindowMonitorResult`
   - Blocking method.
   - Observes window.
   - If closed, calls `self.stop()`.
   - If backend exits first, returns `BACKEND_EXITED`.
   - If unsupported/timeout, returns result; caller decides whether to stop.

2. `StreamlitLauncher.start(monitor_window=False, window_monitor=None)`.
   - Default false initially.
   - If true, attach monitor info to returned session but do not necessarily block.

3. Later CLI integration:
   - `litlaunch run --mode webapp --monitor-window`
   - CLI waits on window close and calls `session.stop()`.

I would avoid background threads at first. A blocking monitor is easier to test and reason about.

## 8. CLI Behavior Plan

Eventually, webapp mode probably should monitor by default, but not in the first pass. Make it opt-in until proven across real desktops.

Future CLI shape:

```text
litlaunch run app.py --mode webapp --monitor-window
litlaunch run app.py --mode webapp --no-monitor-window
litlaunch run app.py --mode webapp --wait-for backend
litlaunch run app.py --mode webapp --wait-for window
litlaunch run app.py --mode webapp --wait-for either
```

Recommended staged behavior:

- Pass 2: no CLI changes except maybe hidden/internal tests.
- Pass 3: add `--monitor-window`, default false.
- Later beta: consider default true for `--mode webapp` on Windows only.

`--wait-for` is powerful but can wait. It needs sharper semantics:
- `backend`: current behavior.
- `window`: monitor window; if closed, stop backend.
- `either`: exit if backend exits or window closes.
- `none`: launch and return? Useful for API, less useful for CLI.

## 9. Windows-First Implementation Strategy

Pass 2 should implement the foundation and fake-driven monitor, not full CLI.

Best Windows implementation:

- Use `ctypes` direct Win32 APIs first:
  - `EnumWindows`
  - `IsWindowVisible`
  - `GetWindowTextW`
  - `GetClassNameW`
  - `GetWindowThreadProcessId`
  - optionally `OpenProcess` / `QueryFullProcessImageNameW`
- Match:
  - visible windows only
  - `Chrome_WidgetWin*` class
  - title contains configured app title
  - title does not look like browser chrome if detectable
  - process name is accepted if in allowed browser names, but missing process name should not always reject
- Capture baseline handles before browser launch if possible.
- After browser launch, wait for a candidate not in baseline.
- Require stability across a second capture or `stable_poll_count`.
- Track exact handle until it disappears.
- If backend exits first, return backend-exited, do not shutdown.
- If no window appears by timeout, return timeout. For CLI webapp mode, likely stop backend.

Pure stdlib is enough on Windows if using `ctypes`. That is better than PowerShell for the primary implementation: lower overhead, no script quoting hazards, fewer host policy issues. PowerShell can remain a fallback later, but it should be deliberate.

## 10. Cross-Platform Strategy

macOS/Linux should initially use `NoopWindowMonitor`.

Behavior:
- Return `supported=False`.
- Include a clear message:
  - “Window monitoring is currently implemented for Windows Chromium app-mode only.”
- Diagnostics should report:
  - platform supports window monitoring false
  - webapp launch still possible
  - window close detection unavailable

Do not fake support on macOS/Linux.

Future:
- macOS might use Accessibility APIs, AppleScript, or `Quartz` APIs. These likely require permissions or non-stdlib packages.
- Linux splits into X11 and Wayland. X11 might be possible with tools/APIs, Wayland is intentionally restrictive. Expect non-stdlib or compositor-specific behavior.

## 11. Failure Modes and Edge Cases

Likely issues:

- Browser reuses an existing process.
- App-mode command returns before window exists.
- Window appears briefly then disappears.
- Multiple app-mode windows match the same title.
- Existing matching windows are open before launch.
- Title is empty at first.
- Title changes after app load.
- Browser chrome title includes app title.
- Edge/Chrome profile restore creates extra windows.
- Browser launch succeeds but no window is detected.
- User closes tab vs window. App-mode usually no tab, but browser behavior can vary.
- Backend exits before window appears.
- Backend crashes while window remains open.
- Monitor loses API access after initially seeing handle.
- Windows desktop is locked, RDP disconnected, or session is non-interactive.
- Headless CI environment.
- Different Edge/Chrome channels: beta/dev/canary process names.
- Kiosk-ish flags alter window classes or titles.
- Multiple monitors/virtual desktops should not matter to EnumWindows, but visibility can be tricky.
- Security software blocks process image queries.
- Localization/browser title suffix differences.

## 12. Test Strategy

Fake-driven tests first. No real browser automation yet.

Tests for core monitor logic:

- `NoopWindowMonitor` returns unsupported.
- Non-webapp/browser mode monitoring returns unsupported or skipped.
- Baseline handles excluded.
- New handle after baseline is selected.
- Newer handle preference when no baseline exists.
- Transient handle rejected.
- Stable candidate selected after second capture.
- Exact handle close detected.
- Capture unavailable before observation.
- Capture unavailable after observation.
- Timeout waiting for window.
- Backend exits before window appears.
- Backend exits after window observed.
- Multiple candidates deterministic selection.
- Title matching rejects browser chrome.
- Process name filtering accepts Edge/Chrome/Chromium names.
- Missing process name does not crash.
- No browser process kill surface exists.

Runtime/session tests:

- `RuntimeSession.monitor_window()` calls `session.stop()` when result is closed.
- It does not call `stop()` on unsupported result.
- It does not call `stop()` if backend already exited.
- It records lifecycle events.
- It does not expose browser process ownership.
- It redacts tokens if messages ever include them, though monitor messages should not.

CLI tests later:

- `--monitor-window` wires fake monitor.
- Closing window triggers `session.stop()`.
- Unsupported monitor returns clear output.
- `--mode browser --monitor-window` fails or warns clearly.

## 13. Security / Reliability Considerations

Guardrails:

- HWND observation only; no control messages sent to browser windows.
- No `CloseWindow`, no `PostMessage(WM_CLOSE)`, no browser termination.
- Never trust or log shutdown tokens.
- Never dump full process lists in diagnostics.
- Do not log full command lines for unrelated browser processes.
- Restrict process-name resolution to the window PID only.
- Treat unavailable Win32 APIs as unsupported, not fatal.
- Ensure PowerShell fallback, if ever added, has no shell-string execution from user input.
- Keep polling interval conservative; do not spin.
- Avoid background threads until lifecycle semantics are clear.

The reliability risk is not the Win32 enumeration itself; it is acting too confidently on weak matches. Bias toward “unsupported/no target found” over stopping a backend because some unrelated browser window closed.

## 14. Recommended Pass Plan

**Pass 2: Windowing Foundation**
- Add `litlaunch.windowing` package.
- Add data types/protocols/config/result.
- Add `NoopWindowMonitor`.
- Add generic polling/target-selection algorithm using injected `capture_windows`.
- Add fake-driven tests for baseline, stability, close, timeout, backend exit.
- No CLI. No real Win32 yet unless small and isolated.

**Pass 3: Windows Chromium Monitor**
- Add `WindowsChromiumWindowMonitor` with `ctypes`.
- Filter by title/class/process name.
- Add unit tests with fake native provider boundaries.
- Add platform factory:
  - Windows -> Windows monitor
  - others -> Noop
- Add diagnostics/inspect summary for monitor availability.

**Pass 4: Runtime/CLI Integration**
- Add `RuntimeSession.monitor_window(...)`.
- Add `litlaunch run --monitor-window`.
- CLI behavior: if window closes, call `session.stop()`.
- Unsupported platforms print clear message and continue/wait for backend depending on selected wait policy.
- Keep default off.

**Pass 5: Hardening**
- Manual Windows app-mode smoke test with Edge and Chrome.
- RDP/locked-session note.
- Tune default poll intervals/timeouts.
- Add docs.
- Consider whether webapp mode should default to monitoring on Windows.

## 15. Decisions Needed

1. Should first user-facing CLI monitoring be opt-in only?  
   My recommendation: yes.

2. Should `--mode webapp` eventually default to monitor-on-close on Windows?  
   My recommendation: eventually yes, but only after real smoke testing.

3. What title should LitLaunch match by default?  
   Recommendation: `LauncherConfig.title`, with clear docs that reliable window monitoring needs a stable page/window title.

4. Should monitor timeout stop the backend in CLI webapp mode?  
   Recommendation: if the user explicitly asked `--monitor-window`, yes, stop owned backend on “window never appeared” because the webapp launch failed as a desktop experience. For API, return result and let caller decide.

5. Should PowerShell fallback exist?  
   Recommendation: not in first implementation. Native `ctypes` first. Add PowerShell only if real Windows testing proves native path insufficient.

6. Should monitor run in a background thread?  
   Recommendation: not initially. Blocking is clearer. Add background/session-managed monitor later only if needed.

7. Should browser mode support monitoring?  
   Recommendation: no. Normal browser mode has too many tabs/windows and weak ownership semantics.

No files were modified in this pass.


Theme:

[LitLaunch]      → phosphor/terminal green
Labels           → Streamlit darker blue
Warnings          → muted amber/yellow
Errors            → PowerShell-style muted red
Muted/detail      → gray
Success           → soft green
