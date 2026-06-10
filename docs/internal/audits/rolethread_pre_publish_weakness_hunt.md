# RoleThread LitLaunch Pre-Publish Weakness Hunt

> INTERNAL / HISTORICAL AUDIT DOCUMENTATION
>
> This document preserves pre-release integration review context. It is not part
> of the stable public LitLaunch documentation surface.

## Executive Summary

LitLaunch 0.26.0 covers the big shutdown parity issue from Pass 2: app-side completion callbacks, idempotent shutdown, and configurable monitor-window graceful timeout are in the local `X:\dev\litlaunch` tree.

The remaining likely pre-publish blockers are not RoleThread-specific. They are generic platform/API gaps exposed by RoleThread’s migration shape:

1. `StreamlitLauncher` has no first-class `cwd`, `extra_env`, or backend command override.
2. Long shutdown work can still block the shutdown HTTP response if implemented as a shutdown hook.
3. CLI cannot express fixed-port hard-fail behavior because there is no `--no-auto-port`.
4. API lacks a public “launch plan” / resolved command object equivalent to CLI dry-run.
5. Packaged/frozen Streamlit bootstrap is not yet a clean LitLaunch extension point.

RoleThread can work around some of these, but those workarounds would become exactly the kind of temporary scaffolding we want to avoid.

## Findings by Classification

**Generic LitLaunch platform gaps**

- Missing `cwd` support at `LauncherConfig` / `StreamlitLauncher` level.
- Missing `extra_env` support for launched backend processes.
- Missing custom backend command / backend runner abstraction for packaged apps.
- Shutdown hook vs completion-callback semantics are easy to misuse for long cleanup.
- Shutdown request timeout is not configurable from `LauncherConfig` / `StreamlitLauncher`.
- CLI lacks `--no-auto-port`.
- API lacks public launch-plan / resolved-command preview.
- Console verbose command output does not use the stronger inspect redaction path.
- Launch-time browser fallback only resolves before launch; it does not retry another browser if the selected browser executable exists but launch fails.

**RoleThread-specific adapter/config concerns**

- RoleThread should set `title="RoleThread Lite"`, `browser="edge"`, `allow_browser_fallback=False`, `host="127.0.0.1"`, `port=8501`, `auto_port=False`, `headless=True`.
- RoleThread cloud sync remains a product hook.
- RoleThread launcher log path and cloud sync status styling remain product concerns.
- RoleThread should decide whether source `launch.py --webapp` stays temporarily or is later replaced by a LitLaunch-recommended entry pattern.

**Obsolete RoleThread launcher residue**

- `core.launcher_runtime`
- `core.launcher_lifecycle`
- `core.browser_adapter`
- `core.shutdown_control`
- most runtime orchestration inside `installer/windows/launcher/rolethread_launcher.py`
- launcher tests that assert custom internals instead of LitLaunch bridge behavior
- `enable_webapp_launch_mode` preference residue

**Docs/test cleanup only**

- Current tests still verify old custom lifecycle ordering.
- Docs cleanup should wait until after runtime replacement, as planned.

**Non-issues**

- RoleThread source webapp config is expressible through `LauncherConfig`.
- Edge app-mode, fallback disabling, title, host, port, headless, and app args are configurable in Python API.
- Window monitoring baseline handle support exists.
- LitLaunch does not own or kill browser processes, which matches the desired model.
- Token redaction is good for shutdown tokens and inspect reports.

## Generic LitLaunch Platform Gaps

The largest gap is backend launch configurability.

LitLaunch currently assumes backend command construction is:

```text
sys.executable -m streamlit run app.py ...
```

That is fine for normal source apps, but RoleThread packaged mode currently uses:

```text
RoleThreadLauncher.exe --rolethread-run-streamlit app.py ...
```

That is not RoleThread weirdness. Any PyInstaller, frozen, embedded, or managed runtime app may need a custom backend invocation while still wanting LitLaunch to own port resolution, health checks, browser launch, shutdown env, and session lifecycle.

Recommended generic capability:

- `LauncherConfig.cwd: Path | None`
- `LauncherConfig.extra_env: Mapping[str, str]`
- `LauncherConfig.python_executable: str | Path | None`
- Either `backend_command: Sequence[str] | None` or a `BackendCommandBuilder` protocol
- Longer-term: `BackendRunner` / `BackendProcessFactory` abstraction for frozen runtimes

Without at least `cwd` and `extra_env`, RoleThread has to keep awkward wrapper code just to start the backend correctly.

## RoleThread Adapter/Config Concerns

`core.litlaunch_adapter` is currently clean and thin. It proves the intended source config:

- app path: `app.py`
- title: `RoleThread Lite`
- mode: `webapp`
- browser: `edge`
- host: `127.0.0.1`
- port: `8501`
- `auto_port=False`
- `headless=True`
- fallback disabled
- no app-side `webapp` arg

That should stay the bridge shape. Do not make RoleThread recreate browser selection, health checks, shutdown protocol, or process supervision.

## Obsolete RoleThread Residue

RoleThread currently duplicates LitLaunch in almost every runtime area:

- Streamlit command construction
- fixed host/port URL helpers
- health check polling
- Edge app-mode launch
- window handle monitoring
- shutdown env/token server
- process termination fallback
- port release diagnostics
- launcher console/status formatting
- packaged launcher lifecycle

After LitLaunch parity, most of that should be deleted, not wrapped forever.

## Packaged/Frozen Launch Assessment

This is the biggest hardening opportunity before TestPyPI.

RoleThread’s packaged launcher is not cleanly modelable with current LitLaunch API because `StreamlitLauncher` internally owns `StreamlitCommandBuilder(config)` and always builds a normal Python module command.

This should become a generic LitLaunch extension point. The clean target is:

- LitLaunch owns lifecycle.
- App/package provides command construction or backend runner.
- LitLaunch still injects shutdown env, waits health, launches browser, monitors window, stops session.

This is generic enough for PyInstaller, cx_Freeze, Nuitka, embedded Python, and app-specific bootstraps.

## Shutdown/Lifecycle Assessment

0.26.0 fixed the major missing piece: `LauncherRuntime.set_shutdown_completion_callback(callback)`.

One remaining trap: shutdown hooks run synchronously before the HTTP response. If a user puts slow cloud sync in a shutdown hook, `ShutdownClient(timeout_seconds=2.0)` can time out even though cleanup is working.

For RoleThread, the better bridge is probably:

- Register only fast hooks, or no hooks.
- Put cloud sync plus process exit in the completion callback.
- Use `RuntimeSession.stop(..., graceful_timeout_seconds=15.0)` or monitor-window equivalent.

Recommended LitLaunch hardening:

- Document that long cleanup belongs in completion callback, not synchronous hooks.
- Consider configurable shutdown request timeout.
- Consider an explicit API name like `set_post_response_shutdown_callback` if the current name is too subtle.

## Logging/Diagnostics Assessment

LitLaunch has good structured `LaunchResult.events`, console rendering, inspect JSON/bundle output, and token redaction.

Gaps:

- No `extra_env` means RoleThread cannot cleanly pass its launcher log path to the backend.
- No file/multi-sink renderer pattern. RoleThread can inject a custom stream, but a documented renderer/stream adapter pattern would help.
- Verbose console command output uses plain command joining, while inspect uses stronger sensitive-arg redaction. This is generic pre-publish polish.

Recommended:

- Reuse `redact_sensitive_args` or equivalent in verbose command rendering.
- Add or document a simple stream-based log sink pattern.
- Add `extra_env` so apps can pass product log destinations without mutating global `os.environ`.

## Browser/App-Mode Assessment

RoleThread can enforce its product policy with:

```python
browser="edge"
allow_browser_fallback=False
```

That is good.

Generic weakness: fallback is resolution-time only. If Edge is detected but launch fails, LitLaunch stops the backend rather than trying Chrome when fallback is allowed. For RoleThread this is fine because fallback is disabled. For LitLaunch’s general audience, launch-time fallback would reduce surprise.

Safe to defer unless you want 0.26.0 to advertise especially robust fallback behavior.

## Window Monitoring Assessment

LitLaunch’s window monitoring is generic enough for RoleThread’s current Windows app-mode path:

- baseline handles exist
- title matching exists
- browser kind matching exists
- timeout/poll config exists in API
- CLI supports `--monitor-window`
- CLI supports `--graceful-timeout`

Weaknesses:

- CLI does not expose appear timeout / poll interval / stable poll count.
- `WindowTarget.url` exists but is not used by the Windows matcher.
- Matching still depends heavily on title and process/class metadata.

These are not blockers for RoleThread, but worth documenting as current monitor limits.

## CLI/API Alignment Assessment

Good:

- CLI has `command`, `run --dry-run`, `inspect`, `--monitor-window`, `--graceful-timeout`.
- Python API has `build_command`, `resolve_browser`, `start`, `run`, `RuntimeSession.monitor_window`.

Gaps:

- CLI has dry-run launch plan; API only has pieces.
- CLI cannot set `auto_port=False`.
- API can set `auto_port=False`, but `StreamlitLauncher.build_command()` is not a resolved launch plan when port is auto-selected.
- CLI monitor flow is higher-level than the API. API users must manually create monitor, baseline target, and call `session.monitor_window`.

Recommended public API addition:

```python
plan = launcher.build_launch_plan()
```

with command, app URL, health URL, resolved port, browser resolution.

## Testability Assessment

RoleThread can test a lot without opening browsers:

- config construction
- command/plan preview
- no app-side `webapp` arg
- fixed port policy
- shutdown bridge with fake completion callback
- fake `ProcessManager`, fake `BrowserLauncher`, fake `WindowMonitor`

But the current API makes some tests more coupled than necessary because launch planning is private/CLI-local. A public plan object would reduce RoleThread scaffolding and help other apps.

## Recommended LitLaunch Changes Before TestPyPI

I would do these before publishing 0.26.0 if the goal is to reduce churn:

1. Add `cwd` to `LauncherConfig` and pass it to `ProcessManager.start`.
2. Add `extra_env` to `LauncherConfig` and merge it into backend env before shutdown env.
3. Add public launch planning API with resolved port, command, app URL, health URL, and browser resolution.
4. Add CLI `--no-auto-port` for `run`, `command`, and `inspect`.
5. Add configurable shutdown request timeout or document why long work must use completion callback.
6. Redact sensitive command values in verbose console command output.
7. Add a generic backend command override or at least design it before publishing. Full implementation can be next if you do not want to expand 0.26.0 scope.

## Changes Safe To Defer

- Launch-time browser retry fallback.
- URL-aware window matching.
- CLI flags for window appear timeout / poll interval.
- Port release owner diagnostics.
- Full packaged/frozen runner abstraction, if `cwd`/`extra_env` and a clear design note land first.
- File logger/multi-sink renderer convenience.

## RoleThread Changes To Avoid For Now

- Do not replace runtime yet.
- Do not add another RoleThread-owned LitLaunch lifecycle wrapper that recreates LitLaunch internals.
- Do not migrate packaged launcher until LitLaunch has a generic packaged/backend extension point.
- Do not move cloud sync behavior into LitLaunch.
- Do not revive `streamlit run app.py -- webapp`.
- Do not broadly rewrite docs or tests until the runtime path is actually replaced.

## Final Recommendation

LitLaunch 0.26.0 is close, and the shutdown hardening is the right direction. Before TestPyPI, I would at minimum add `cwd`, `extra_env`, public launch planning, and CLI `--no-auto-port`. Those are small, generic, high-leverage changes that directly prevent RoleThread from needing ugly temporary scaffolding.

The packaged/frozen command issue is the one big architectural item. It does not have to be fully solved before 0.26.0, but it should at least be explicitly designed now so RoleThread does not become the place where that abstraction gets hacked in sideways.
