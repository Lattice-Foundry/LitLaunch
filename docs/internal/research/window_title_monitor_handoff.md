# LitLaunch Window Title Monitor Handoff

> INTERNAL / RESEARCH DOCUMENTATION
>
> This note captures a real launch failure discovered while hardening the
> LitBridge and LitPack app-stack flow. It is intended as implementation context
> for the LitLaunch thread, not as public documentation.

## 1. Executive Summary

LitLaunch successfully started a Streamlit backend and launched Microsoft Edge
in app mode for the LitBridge generic demo, but then shut the app down because
the app-window monitor timed out before it recognized the browser window.

The immediate root cause was a profile/page title mismatch:

- LitLaunch profile title: `LitBridge Generic Interaction Demo`
- Streamlit page title: `LitBridge Generic Demo`

The monitor currently treats the configured profile title as the expected
window title. It does support containment matching when the expected title is
contained in the observed title, plus a transient URL-title fallback. It does
not catch the inverse or near-match case where the browser window has a shorter
but obviously related title.

This is not just a one-off mistake. It is a predictable developer trap because
`title` looks like a friendly app/profile label, while the monitor depends on
the browser/OS-exposed window title. Frameworks such as Streamlit set the real
browser title through app code, commonly `st.set_page_config(page_title=...)`.
Developers can reasonably assume the launcher title and the framework page
title are separate concerns unless LitLaunch makes the contract obvious or more
forgiving.

Recommended direction:

1. Improve timeout diagnostics immediately.
2. Document the profile-title/page-title contract clearly.
3. Add conservative fuzzy title matching for browser app-mode windows.
4. Consider a future config split between friendly display title and monitored
   page/window title only if real usage keeps showing the distinction matters.

## 2. Observed Failure

LitBridge demo command:

```powershell
cd X:\dev\prod\litbridge\examples\generic_interaction_demo
litlaunch --profile demo
```

Relevant console output:

```text
[   ok   ] LitLaunch Starting runtime...
[   ok   ] Backend: Started Streamlit in 0.0s.
[   ok   ] Health: Waiting for Streamlit...

2026-06-10 15:12:51.225 Uvicorn server started on 127.0.0.1:8520

  You can now view your Streamlit app in your browser.

  URL: http://127.0.0.1:8520

[   ok   ] Health: Ready in 0.5s.
[   ok   ] Browser: Launched Microsoft Edge in app mode in 0.0s.
[   ok   ] Runtime: Ready locally at http://127.0.0.1:8520.
[   ok   ] Monitor: Watching app window...
[ error  ] Monitor: Timed out before app window was observed.
[ cause  ] Timed out waiting for app-mode window to appear.
[  next  ] Use verbose mode for more runtime details.
[ error  ] Shutdown: Graceful request failed.
[ cause  ] The app did not accept the cleanup request.
[  next  ] Use verbose mode for more runtime details.
[  warn  ] Shutdown: Using backend termination fallback.
[ cause  ] The backend did not stop through graceful shutdown.
[  next  ] Use verbose mode for more runtime details.
[   ok   ] Shutdown: Complete; backend stopped through termination fallback in 2.0s.
[   ok   ] Backend: Port 8520 released.
[ error  ] Timed out waiting for app-mode window to appear.
[  next  ] Use verbose mode for more runtime details.
```

User-visible behavior:

- The app window appeared.
- The demo looked correct.
- LitLaunch later closed it because the monitor never marked it observed.

That creates a confusing experience: from the user's perspective launch worked,
then the tool tore it down.

## 3. Immediate Root Cause

Before the LitBridge-side fix:

```toml
[profiles.demo]
app_path = "app.py"
title = "LitBridge Generic Interaction Demo"
mode = "webapp"
browser = "auto"
trust_mode = "strict_local"
host = "127.0.0.1"
port = 8520
auto_port = true
headless = true
allow_browser_fallback = true
runtime_event_log = ".litlaunch/runtime-events.log"
graceful_timeout = 15

[profiles.demo.window_monitor]
enabled = true
appear_timeout = 60
poll_interval = 1
stable_polls = 2
```

The Streamlit app set:

```python
st.set_page_config(page_title="LitBridge Generic Demo", layout="wide")
```

The browser window title followed Streamlit's `page_title`, not the longer
LitLaunch profile title. The practical fix in LitBridge was to align the
profile title with the Streamlit page title:

```toml
title = "LitBridge Generic Demo"
```

That is a good app-level fix, but LitLaunch should still make this failure mode
easier to diagnose and, where safe, avoid.

## 4. Why This Will Recur

This trap is likely in normal developer use:

- `LauncherConfig.title` reads like a friendly product or shortcut title.
- `st.set_page_config(page_title=...)` controls the actual Streamlit browser
  title.
- Developers may write richer page H1 text, a different friendly launcher title,
  and a shorter browser title.
- Browser/OS window title APIs can expose suffixes, prefixes, loading states,
  URL placeholders, or browser chrome variations.
- A window may briefly show `127.0.0.1_/`, `localhost`, `about:blank`, or a
  browser-specific placeholder before the final page title settles.
- In app-mode flows, a failed monitor can lead to LitLaunch terminating a
  perfectly healthy app.

The conceptual issue is that one string is currently doing too much:

- human-friendly app label;
- shortcut/window display title;
- monitoring target;
- sometimes docs/profile identity.

That is acceptable for a simple default, but the failure mode needs stronger
tooling support.

## 5. Current Relevant Code Shape

Known implementation points from current LitLaunch source:

- `src/litlaunch/windowing/base.py`
  - `WindowTarget(title, url, browser_kind, app_mode, baseline_handles)`
  - `WindowInfo(handle, title, class_name, pid, process_name)`
  - `WindowMonitorResult(...)`
  - `WindowMonitorConfig(...)`
- `src/litlaunch/windowing/polling.py`
  - `PollingWindowMonitor._wait_for_stable_target(...)`
  - `_candidate_windows(target)`
  - `_matches_target(window, target)`
  - `_matches_target_title(window_title, target)`
  - `_matches_transient_url_title(window_title, target.url)`
- `src/litlaunch/monitored_browser.py`
  - browser-window selection has similar matching logic.
- `src/litlaunch/console.py`
  - `ConsoleRenderer.render_window_monitor_result(...)`
  - Current timeout guidance says:
    - confirm the app-mode browser window opened and the title matches;
    - try `--title` if the window title differs from the app title.
- `src/litlaunch/session.py` and `src/litlaunch/monitored.py`
  - wire monitoring into runtime lifecycle and shutdown.

Current app-mode title matcher in `windowing/polling.py` is effectively:

```python
normalized_title = window_title.strip().lower()
normalized_target = target.title.strip().lower()
if normalized_target and normalized_target in normalized_title:
    return True
if target.title == "Streamlit App":
    return True
return _matches_transient_url_title(normalized_title, target.url)
```

This catches:

- exact title;
- browser title with suffix/prefix containing target title;
- default `Streamlit App`;
- transient URL-ish title.

It misses:

- target title longer than observed title;
- same words with one extra token;
- punctuation/case/spacing drift beyond basic lowercase strip;
- title abbreviations such as `LitBridge Generic Demo` vs
  `LitBridge Generic Interaction Demo`.

## 6. Recommended Fix Plan

### Pass 1: Better Failure Diagnostics

Make timeout output self-explanatory when monitoring saw plausible windows but
none matched.

Suggested behavior on timeout:

```text
[ error  ] Monitor: Timed out before app window was observed.
[ cause  ] Timed out waiting for app-mode window to appear.
[ detail ] Expected window title: LitBridge Generic Interaction Demo
[ detail ] Browser: Microsoft Edge
[ detail ] Observed app-window candidates:
[ detail ] - LitBridge Generic Demo (process msedge)
[ detail ] - 127.0.0.1_/ (process msedge)
[  next  ] Match the profile title to the framework page title.
[  next  ] For Streamlit, set st.set_page_config(page_title="...").
[  next  ] Or pass --title / update litlaunch.toml.
```

Implementation idea:

- Capture and retain rejected candidates during polling.
- Either:
  - add `observed_candidates: tuple[WindowInfo, ...]` or
    `diagnostic_windows: tuple[WindowInfo, ...]` to `WindowMonitorResult`; or
  - add a final `WindowMonitorEvent` with candidate info.

Prefer adding a typed field to `WindowMonitorResult` if this is still an
internal beta-compatible change. It is easier for console rendering, diagnostics
bundles, and tests than encoding data in strings.

Suggested result extension:

```python
@dataclass(frozen=True)
class WindowMonitorResult:
    ...
    candidates: tuple[WindowInfo, ...] = field(default_factory=tuple)
```

Then on timeout:

- include the most recent windows returned by `capture(target)` after baseline
  filtering and browser-kind filtering, even if title matching failed;
- cap display to a small number, for example 5;
- redact nothing by default because window titles are local diagnostics, but
  diagnostics bundle paths already have sanitization posture, so be mindful if
  these get included in support bundles.

Important distinction:

- `capture(target)` currently returns all captured windows from the provider,
  while `_candidate_windows(target)` only returns matching target windows.
- For diagnostics, capture "near candidates" before title matching filters them
  out. Otherwise the timeout knows only that zero candidates matched.

Possible helper:

```python
def _diagnostic_windows(self, target: WindowTarget) -> tuple[WindowInfo, ...]:
    baseline = set(target.baseline_handles)
    return tuple(
        window
        for window in self.capture(target)
        if window.handle not in baseline
        and _matches_browser_kind_if_known(window, target)
    )
```

Then `_candidate_windows` can continue applying full title matching.

Test goals:

- timeout result includes observed non-matching app/browser window titles;
- console timeout renders expected title and candidate title in verbose mode;
- normal mode gives one or two actionable lines, not a wall of noise;
- no candidates still renders current simple guidance.

### Pass 2: Title Contract Documentation

Update public docs wherever app-window monitoring is explained:

- `README.md`
- `docs/window_monitoring.md`
- profile wizard docs/help if present
- CLI `--title` help if wording can be improved

Recommended wording:

```text
When window monitoring is enabled, LitLaunch uses the configured app title as
the expected browser window title. For Streamlit apps, this should usually match
st.set_page_config(page_title="..."). If the browser window title differs,
LitLaunch may launch the app successfully but fail to monitor its close event.
```

Clarify that `title` is not merely decorative for monitored app-mode launches.

Also consider wizard copy:

Current-ish concept:

```text
App title
Set the friendly title used in app-window and shortcut workflows.
```

Suggested:

```text
App title
Used for shortcuts and monitored app-window matching. For Streamlit, match
st.set_page_config(page_title=...).
```

### Pass 3: Conservative Fuzzy Matching

Add a safe "near title" matcher after strict containment and URL fallback, with
tests around false positives.

The goal is not broad fuzzy search. The goal is to handle obvious product-title
drift without accidentally attaching to the wrong browser window.

Recommended matching order:

1. normalized exact/containment match: existing behavior;
2. transient URL match: existing behavior;
3. token-set overlap match with conservative thresholds;
4. optional sequence similarity only as a secondary confirmation.

Suggested normalization:

- lowercase;
- strip browser suffixes if practical:
  - ` - Microsoft Edge`
  - ` - Google Chrome`
  - ` - Chromium`
- replace punctuation/separators with spaces;
- collapse whitespace;
- split into alphanumeric tokens;
- drop weak framework/browser tokens:
  - `streamlit`
  - `app`
  - `localhost`
  - maybe browser names.

Example:

```text
target: LitBridge Generic Interaction Demo
window: LitBridge Generic Demo

target tokens: litbridge, generic, interaction, demo
window tokens: litbridge, generic, demo
overlap: litbridge, generic, demo
ratio vs shorter side: 3 / 3 = 1.0
ratio vs longer side: 3 / 4 = 0.75
```

This should match.

Counterexamples that should not match:

```text
target: LitBridge Generic Demo
window: Generic Admin
```

Overlap is too generic and lacks distinctive project token.

```text
target: LitBridge Demo
window: LitPack Demo
```

Only `demo` or maybe one weak token overlaps; should not match.

```text
target: My App
window: Other App
```

Do not match because all useful tokens are weak/common.

Suggested predicate:

```python
def _titles_are_near_match(window_title: str, target_title: str) -> bool:
    window_tokens = _significant_title_tokens(window_title)
    target_tokens = _significant_title_tokens(target_title)
    if len(window_tokens) < 2 or len(target_tokens) < 2:
        return False
    overlap = window_tokens & target_tokens
    if len(overlap) < 2:
        return False
    shorter_ratio = len(overlap) / min(len(window_tokens), len(target_tokens))
    longer_ratio = len(overlap) / max(len(window_tokens), len(target_tokens))
    return shorter_ratio >= 0.8 and longer_ratio >= 0.6
```

For the LitBridge case:

- shorter ratio: 1.0
- longer ratio: 0.75
- match.

Risk controls:

- require browser process match when `target.browser_kind` is known;
- require non-baseline window handle as today;
- require at least two significant overlapping tokens;
- do not use fuzzy matching when target title is too short or generic;
- log/render that a fuzzy match was used in verbose mode.

Possible event message:

```text
App-mode window observed by near-title match.
```

If adding match reasons is too invasive now, defer the verbose reason until
after diagnostics are improved.

### Pass 4: Optional Config Split

Do not lead with new config surface unless needed. But if multiple apps want a
friendly profile title that differs from the page/window title, add a separate
field.

Possible names:

```toml
title = "LitBridge Generic Interaction Demo"
window_title = "LitBridge Generic Demo"
```

or under monitor config:

```toml
[profiles.demo.window_monitor]
enabled = true
title = "LitBridge Generic Demo"
```

Recommendation if implemented:

- keep `title` as the default when no window-specific title is configured;
- prefer `window_title` only for matching;
- ensure CLI `--title` behavior remains backward-compatible;
- consider whether shortcut title should still use `title`.

This is useful but not urgent. Better diagnostics and conservative fuzzy
matching probably solve most real-world pain without adding another concept.

## 7. Tests To Add

Suggested focused tests:

### Windowing/polling tests

- `test_polling_monitor_timeout_records_rejected_browser_candidates`
  - baseline excludes old window;
  - new Edge window appears with non-matching title;
  - result times out;
  - result includes candidate title/process in diagnostics.

- `test_polling_monitor_near_title_match_handles_missing_middle_token`
  - target `LitBridge Generic Interaction Demo`;
  - observed `LitBridge Generic Demo`;
  - monitor observes the window.

- `test_polling_monitor_near_title_match_requires_distinctive_overlap`
  - target `My App`;
  - observed `Other App`;
  - no match.

- `test_polling_monitor_near_title_match_respects_browser_kind`
  - matching title but wrong process should not match when browser kind is set.

- `test_polling_monitor_renders_timeout_candidates`
  - console output includes expected title and candidate title.

### Browser monitored tests

There is similar title matching in `monitored_browser.py`. Avoid fixing only
`windowing/polling.py` if browser-window monitoring has a separate matcher.
Either:

- extract shared title matching helpers into one internal module; or
- duplicate tests for browser path until a shared helper exists.

Prefer a shared helper to avoid drift.

Potential shared module:

```text
src/litlaunch/windowing/title_match.py
```

Exports can remain internal:

```python
matches_window_title(window_title: str, target_title: str, target_url: str | None) -> bool
title_match_reason(...) -> WindowTitleMatch
```

Keep public API untouched unless there is a strong reason.

## 8. Console UX Recommendation

Normal mode should stay concise. The key is to reveal the expected title and at
least one plausible observed title when available.

Suggested normal output:

```text
[ error  ] Monitor: Timed out before app window was observed.
[ cause  ] Expected title "LitBridge Generic Interaction Demo"; saw "LitBridge Generic Demo".
[  next  ] Match the profile title to the app page title, or run with --title.
```

Suggested verbose additions:

```text
[detail] Expected window title: LitBridge Generic Interaction Demo
[detail] Expected browser: Microsoft Edge
[detail] Target URL: http://127.0.0.1:8520
[detail] Candidate windows:
[detail] - handle=0x001234 title="LitBridge Generic Demo" process=msedge class=...
[detail] - handle=0x001235 title="127.0.0.1_/" process=msedge class=...
```

Avoid telling users only to "use verbose mode" when LitLaunch already has
enough information to name the likely mismatch in normal mode.

## 9. Public Docs Recommendation

Add a short section to `docs/window_monitoring.md`:

```markdown
### Window Titles

When app-window monitoring is enabled, LitLaunch must identify the browser
window that belongs to your app. By default, it uses the profile or CLI title as
the expected browser window title.

For Streamlit apps, set the same title in your app:

```python
st.set_page_config(page_title="My App")
```

and in your LitLaunch profile:

```toml
title = "My App"
```

If these differ, LitLaunch may launch the browser successfully but fail to
observe the app window close event.
```

Also mention this in troubleshooting:

```text
Symptom: browser opens, then LitLaunch reports "Timed out waiting for app-mode
window to appear" and shuts down the backend.

Likely cause: window title mismatch.
Fix: match `title` to the framework page title or pass `--title`.
```

## 10. LitBridge Fix Already Applied

LitBridge-side follow-up was committed on branch `feature/class_architecture`:

```text
6380f8c LB-M6D2 Align demo LitLaunch window title
```

Changes:

- `examples/generic_interaction_demo/litlaunch.toml`
  - `title = "LitBridge Generic Demo"`
- `tests/test_generic_demo.py`
  - asserts the profile title remains aligned
- `examples/generic_interaction_demo/README.md`
  - documents that the LitLaunch profile title intentionally matches
    Streamlit `page_title`

This app-level fix should remain, even if LitLaunch gets smarter. Matching
titles is still the cleanest configuration.

## 11. Suggested Implementation Order

1. Add diagnostic candidate capture to `WindowMonitorResult`.
2. Render expected title and observed candidate titles on timeout.
3. Update docs and wizard/help copy around title matching.
4. Extract shared title matching helper.
5. Add conservative near-title matching.
6. Add tests for LitBridge-style mismatch and false positives.
7. Manually validate with:

```powershell
cd X:\dev\prod\litbridge\examples\generic_interaction_demo
litlaunch --profile demo
```

8. Optionally validate an intentionally mismatched profile in a scratch copy to
   confirm diagnostics are clear before fuzzy matching lands, and confirm it is
   tolerated after fuzzy matching lands.

## 12. Success Criteria

LitLaunch is improved when:

- a healthy app window is not torn down merely because of an obvious title
  near-match;
- timeout output identifies the expected title and likely observed title;
- Streamlit users know to align `st.set_page_config(page_title=...)` with the
  LitLaunch profile title;
- false positives remain unlikely when multiple browser windows are open;
- browser-window and app-window monitoring do not diverge in title matching
  behavior.

