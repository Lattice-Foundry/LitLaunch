# LitLaunch Security Audit 0.91.23b1

> INTERNAL / HISTORICAL AUDIT DOCUMENTATION
>
> This document preserves pre-release audit context. It is not part of the
> stable public LitLaunch documentation surface.

I have completed a full pass over the codebase (all 60 source modules, 19 docs, CI, release tooling, tests, examples), run the suite (480 passed, ruff clean), and traced every claim. Here is the audit.

---

# LitLaunch Comprehensive Audit

**Version audited:** 0.91.23b1 — branch `feature/polish` — working tree clean
**Suite:** 480 passed in 9.6s · `ruff check` clean · `ruff format` clean

## 1. Executive Summary

LitLaunch at 0.91.23b1 is a genuinely coherent, well-factored runtime layer. The growth since the 0.31.x audits — CLI package split, inspect package split, HTML diagnostics, the `report` workflow, the profile wizard, shortcut generation, console UX overhaul — has been absorbed without the architecture fraying. The shell-free invariant, the "own only what we start" boundary, and the dependency injection discipline all held. The prior audit's two open items are resolved: `build_command()` now routes through `build_launch_plan()`, and the suite is green (the stale-metadata test failure is gone, and the editable-install caveat is documented).

It is **TestPyPI-ready today**. It is **close to, but not at, confident public-PyPI readiness**, for three concrete reasons:

1. **The profile/shortcut system — the most prominent new feature surface and the largest body of new code — is the least tested.** `profile_wizard.py` (992 lines, the single biggest module) and `profile_writer.py` (196 lines, writes files to disk) have **zero** importing test files. A headline feature ships untested.
2. **Six `[diagram needed]`/`[screenshot needed]` placeholder blocks ship in the public docs**, and two `docs/integration/` files have drifted out of date (they describe shipped features as "not implemented").
3. **One real security gap:** a non-loopback `host` (e.g. `--host 0.0.0.0`) is accepted **silently** everywhere — config, profiles, wizard, diagnostics — with no warning. For a tool whose stated posture is "localhost-first," accidental network exposure has no guardrail.

None of these is architectural. All three are finishable in a focused pass. The bones are good.

**Scores (0–10):** Architecture 8.5 · CLI/UX 8.5 · Docs 7.5 · Diagnostics 8.5 · Profile/Shortcut 6.5 · Security 8.0 · Test/Release 8.0

## 2. Architecture & Maintainability

**Strengths — the prior hardening goals were largely met.**

- **Clean layering.** `LauncherConfig` → `StreamlitLauncher` facade → `planning.py` / `backend_start.py` (orchestration extracted out of the facade) → `RuntimeSession` (live ownership). `runtime_console.py` cleanly isolates presentation from orchestration: its helpers are None-tolerant and never influence lifecycle decisions. This is the "diagnostics separation / reusable internals" goal, achieved.
- **Shell-free, verified.** `ProcessManager.start` and both browser launch paths pass `shell=False`; `subprocess.list2cmdline` appears only in `redaction.format_command_preview` for *display*. `test_no_shell_true.py` guards it. No shell-out duplication.
- **DI everywhere.** Every collaborator is injectable; structural `Protocol`s (`ClockProvider`, `ManagedPopen`, `BackendCommandProvider`, `WindowMonitor`) keep the seams honest. `StreamlitLauncher` takes 8 injectable dependencies and `CliContext` carries 5 factories.
- **Validation at the boundary.** Frozen dataclasses with `__post_init__` normalization throughout (`LauncherConfig`, `BackendCommand`, `DiagnosticItem`, `WindowMonitorConfig`, …).
- **Resolved prior finding.** `StreamlitLauncher.build_command()` is now a documented thin wrapper over `build_launch_plan(...).command`, so custom `BackendCommandProvider`s see the same resolved context everywhere. The bypass is gone.
- 10,770 lines of `src`, average file ~150 lines, ruff-clean.

**Weaknesses / technical debt.**

- **`profile_wizard.py` is the maintainability outlier — 992 lines, 4× the next largest file.** The step-table design is sound, but the file carries wizard state, IO, ~25 step handlers, six `_ask_*` prompt helpers, color styling, preview rendering, and shortcut offering. It should be split (wizard engine / step handlers / prompt-IO).
- **Four parallel ANSI-color mechanisms.** `ConsoleRenderer._style` + `ANSI_COLORS`; `cli/help.py._HelpStyle._style`; `profile_wizard.py._style` + `_style_help_magenta` (which hardcodes `\033[95m`); and the argparse `_colorize` theming in `cli/main.py`. Each re-implements `f"{ansi}{text}\033[0m"`. This is real drift risk — a palette change must be made in four places.
- **The profile wizard bypasses `ConsoleRenderer` entirely.** It writes straight to the stream with its own `_write` and even hardcodes a status label literal (`_write_warning_status` → `"[  warn  ]"`). The console UX overhaul never reached the wizard, so there are effectively two console systems. If `console.py` changes its status-label format, the wizard silently drifts.
- **Dead code.** `ConsolePhase.RUNTIME` and `ConsolePhase.STOPPING_BACKEND` enum members are referenced nowhere (`STOPPING_BACKEND` was retired in 0.91.6b0; the member was left behind). `ANSI_COLORS["indigo"]` and `ANSI_COLORS["cyan"]` have no consumer. `cli/main.py:36` re-aliases an import to `_source_checkout_example_path` for no reason.
- **Fragile argparse internals.** `cli/main.py` mutates the private `subparsers._choices_actions` (with `# type: ignore`) to hide `console-preview` from the command metavar. It works on 3.14 but is not a stable contract.
- **Minor:** `copy_streamlit_flags`'s middle `hasattr(flags, "items")` branch is likely unreachable given config normalization always yields a `MappingProxyType` or `tuple`. `BackendCommand.command` is typed `Sequence[str]` but stored as `tuple`. Stale `.pyc` files for deleted modules (`cli.py`, `diagnostics.py`, `inspect.py`, …) sit in `src/litlaunch/__pycache__/` — gitignored, but a `find . -name __pycache__ -prune -exec rm -rf` is overdue.

## 3. CLI & UX Maturity

The CLI **does now feel like a coherent product surface.** It is the best-tested area (108 tests in `test_cli.py`).

- **Layering is clean:** `cli/main.py` (parser + entry) → `cli/commands.py` / `create.py` / `inspect.py` / `help.py` / `preview.py` handlers → `cli/config.py` (arg↔profile mapping) → `cli/common.py` (`CliContext`). Shorthand (`litlaunch app.py`, `litlaunch --profile X`) routes through the explicit `run` pipeline via `_normalize_launch_shorthand` — one launch path, two front doors.
- **Ergonomics are mature:** consistent `--force`/`--dry-run` on every file-writing command; `report` (ergonomic) vs `inspect --html/--json/--bundle` (advanced) is a deliberate, documented split; workflow `help <topic>` vs argparse `--help` is a clean reference/guidance divide; `console-preview` is genuinely hidden and labeled internal; exit codes are disciplined (`LitLaunchError`→2, other→1, wizard cancel→130).
- Bare profile names are intentionally rejected — correct call, and documented in three places.

**Remaining pain points:**

- `inspect --html --output X` and `report --output X` produce the same artifact. Defensible as an ergonomic alias and documented as such, but it is surface a new user must reconcile.
- No `--headless` CLI flag — `headless` is settable only via a profile. Small but real gap given `--mode`/`--host`/`--port` all have flags.
- `help`'s implicit default topic `"menu"` is not in `HELP_TOPICS`, so an unknown-topic error never lists it. Cosmetic.
- The `subparsers._choices_actions` hack is the one CLI construct that could break on a future Python.

## 4. Documentation & Help System

The **user-facing docs are accurate and current.** README, `cli.md`, `quickstart.md`, `overview.md`, `philosophy.md`, `troubleshooting.md`, `browser_support.md`, `window_monitoring.md`, `installation.md` all match the shipped behavior. The Feature Status table is honest (Window monitoring = Experimental, Packaging = Notes only, Diagnostics dashboard = Not implemented). The CHANGELOG is genuinely excellent — concise, per-version, no drift, back to 0.8.0. Sanitization caveats are honest throughout ("pattern-based … not a cryptographic scrubber").

**But the docs are not yet public-PyPI clean:**

- **Six shipped placeholder blocks.** `[diagram needed]` in `architecture.md`, `overview.md`, `browser_support.md`, `rolethread.md`; `[screenshot needed]` in `inspect.md`, `quickstart.md`, `window_monitoring.md`. The sdist excludes only `docs/internal`, so all of these ship. The CHANGELOG acknowledges them as "deferred beta documentation work" — fine as tracked debt, but literal bracketed TODOs in a PyPI project page / shipped docs read as unfinished.
- **`docs/integration/packaging_notes.md` is stale and self-contradicting.** It lists "shortcut generation" under **"Not implemented"** — but `litlaunch create shortcut` and the wizard's shortcut offer exist as of 0.91.22b0. The "Windows Shortcuts / Future notes should cover…" section is also obsolete. This file ships.
- **`docs/integration/rolethread.md` is stale.** "Future launch profiles may help RoleThread … Until implemented, integration should use explicit `LauncherConfig` fields." Profiles shipped at 0.41.0. This file ships.
- `installation.md`: `git clone …/LitLaunch` then `cd litlaunch` — case mismatch; fails on Linux.
- README "Non-Goals" still lists "shortcut … workflows," now partially contradicted by `create shortcut`.

Help system itself (workflow `help`, argparse `--help`) is well-built and consistent. The problem is purely doc *content drift* in the integration files and the placeholder debt.

## 5. Diagnostics & Reporting

**Architecturally the cleanest subsystem.** `DiagnosticItem/Section/Report` model → HTML/JSON/bundle renderers from one report. `to_dict()` applies `redact_sensitive_text` at the model boundary; `HTMLDiagnosticsRenderer` additionally `html.escape(..., quote=True)`s — two-layer, XSS-safe. The HTML report is standalone: no JavaScript, no external CSS, dark-mode + print styles — safe to open and to share after review. `SCHEMA_VERSION = 1` with `generated_by`/`litlaunch_version` makes the JSON a real machine contract. Collection never starts a process.

**Polish gaps and one privacy gap:**

- **Diagnostics never surface host exposure.** `_target_section` embeds the host inside `app_url` but emits no dedicated "Host binding" item and no WARNING when `host != 127.0.0.1`. The single report a corp developer would run to sanity-check a setup will not tell them they've bound to `0.0.0.0`. This should be a WARNING-status item.
- **`SanitizedBundleRenderer` carries only `SANITIZATION_NOTE`, not `PRIVACY_NOTE`.** The support bundle is the artifact *most* likely to be pasted into a public issue tracker, yet it lacks the stronger "pattern redaction may miss encoded/reformatted secrets — review before sharing" warning that the HTML report carries. Invert that: the bundle needs the strongest warning.
- The HTML `PRIVACY_NOTE` itself is exactly right — honest about redaction limits. Keep that tone.

## 6. Profile & Shortcut System

This is the **weakest area relative to its prominence**, and it is where I'd focus before a public tag.

**Design and safety rails are good:**

- `profiles.py`: strict profile-name regex; unknown-field rejection; ambiguity detection when both `litlaunch.toml` and `pyproject.toml` carry profiles; paths resolved against the TOML's directory.
- `profile_writer.py`: writes only `litlaunch.toml`; **refuses** a file containing non-`profiles` content (won't clobber a hand-edited config); `--force`/`--dry-run`; dry-run validates the rendered TOML in a temp directory.
- Wizard: Simple/Advanced modes, app-root detection, `back`/`quit` navigation, clean Ctrl+C → exit 130, preview-before-write, conservative shortcut prompt (`default=False`).
- `shortcut_writer.py`: deterministic OS-appropriate `.bat`/`.sh`/`.command`; correct POSIX quoting (`'\''`); exec bit set on POSIX.

**Real weaknesses:**

- **Zero test coverage on `profile_wizard.py` (992 lines) and `profile_writer.py` (196 lines).** No test file imports either. Six "Create Profile Wizard Pass" commits landed the largest module in the project with no automated test, even though `run_profile_wizard` ships an injectable `input_func` *designed* for testing. `profile_writer` writes files to disk untested.
- **`_toml_string` (profile_writer) does not escape control characters** (`\n`, `\r`, `\t`). A title or `extra_env` value containing a newline produces invalid TOML. Worse: the non-dry-run path writes the file *then* validates with `load_profile` — so a validation failure **leaves a corrupt `litlaunch.toml` on disk**. Dry-run validates in a temp dir first; non-dry-run should do the same (validate, then write).
- **`shortcut_writer._quote_windows` is wrong for `cmd.exe`.** It backslash-escapes quotes (`\"`) — `cmd.exe` does not honor that; it uses doubled quotes. More importantly it does not handle `%` (variable expansion) or `&`/`^`/`<`/`>`, all legal in Windows paths. A profile app-root or `--config` path containing `%` or `&` yields a broken or surprising `.bat`. The POSIX side is correct; the Windows side — the primary internal-tooling target — is not.
- Generated shortcuts invoke bare `litlaunch`, relying on `PATH`. A venv-only install that isn't activated will not resolve it. The shortcut captures no Python/venv path.
- `_step_cwd` re-prompts via self-recursion while every other step uses `while True` — inconsistent, with theoretical stack growth on repeated bad input.

## 7. Security & Runtime Hardening

**Current posture — honestly good for the local/internal scope it claims.** LitLaunch does not pretend to make Streamlit secure, and it shouldn't.

What is solid:

- Default `host=127.0.0.1`. Shell-free everywhere. Owns only the backend process it starts; never kills by name, PID, or port owner.
- **Shutdown endpoint is well-hardened:** loopback-only enforced (`_is_loopback_host` gate before bind), `secrets.token_urlsafe(32)` token delivered in a header (never in URL/query), idempotent under `_shutdown_lock`, the shutdown port is found dynamically, and the token is redacted from console *and* diagnostics. Critically, the shutdown endpoint **always binds `127.0.0.1` regardless of the app's `host`** — so even an app on `0.0.0.0` keeps a loopback-only control channel. That is a deliberate, correct decision.
- Diagnostics sanitized at the model boundary; `<user-home>` path-prefix redaction; HTML escaped; no JS in the report.
- Browser launch shell-free, never owned/killed. Window monitoring is observation-only and uses minimal Win32 privilege (`PROCESS_QUERY_LIMITED_INFORMATION`).
- `extra_env` is child-process only; shutdown vars win on collision.

**The one real weakness — and it matters:**

- **Silent non-loopback host binding.** `config._normalize_host` accepts `0.0.0.0`, `::`, or any LAN IP with **no warning**. `--host`, TOML profiles, and the wizard's Host step all accept it silently. `tests/test_cli.py` and `test_config.py` *codify* `0.0.0.0` as valid. A Streamlit app has no built-in auth; `litlaunch --host 0.0.0.0` quietly publishes an internal dashboard to the whole subnet, and **nothing** — not the console, not the launch output, not the diagnostics report — says a word. For a "localhost-first" tool this is the gap that an internal-tooling developer would expect you to close.

**Other gaps:**

- `PortManager` is IPv4-only (`socket.AF_INET`). An IPv6 `host` such as `::1` makes `is_port_available` always return `False`, so `resolve_port` walks to exhaustion and raises `PortError`. `health.py` and `shutdown.py` both have IPv6 bracket handling, so IPv6 is *intended* to work — `PortManager` simply doesn't follow through. Latent bug + internal inconsistency.
- The wizard offers no warning when a user pastes a secret as an `extra_env` value — it lands in `litlaunch.toml` in plaintext.

**Practical, in-scope hardening recommendations (priority order):**

1. **Non-loopback guardrail.** When the resolved `host` is not loopback: emit a prominent console WARNING at launch *and* a WARNING diagnostic item. Gate it behind an explicit opt-in — a `--allow-network-exposure` flag, `LITLAUNCH_ALLOW_REMOTE=1`, or a profile `allow_network_exposure = true` — and refuse (or loudly warn) without it. This is the "accidental exposure prevention / unsafe-config detection" the audit asks for, and it's a small change.
2. **Diagnostics "Host binding" item** — WARNING when non-loopback, so `report` becomes a real safety check.
3. **A `strict`/lockdown profile mode** — a profile flag (or `--strict-localhost`) that refuses any non-loopback host and rejects `extra_browser_args`. This is the "runtime lockdown / profile trust mode" idea, scoped realistically.
4. **Wizard hardening defaults** — warn on non-loopback host in the Host step; warn that `extra_env` values are stored plaintext and recommend OS environment variables for secrets.
5. **Optional opt-in runtime audit log** — append-only local log of launch / stop / shutdown-request events, for internal-tooling traceability. Off by default.
6. **Fix `_toml_string` control-char escaping + validate-before-write; fix `_quote_windows`.** Treat the profile/shortcut generators as trusted-output paths.
7. **One honest "internal-network deployment" doc page** — state plainly that Streamlit itself has no auth, that LitLaunch governs the *runtime*, and recommend a reverse proxy with auth (or SSH tunnel) for anything beyond loopback. Honesty here is a trust asset; don't oversell.

## 8. Corporate/Internal-Tooling Positioning

LitLaunch is a **credible runtime-governance layer** for localhost and internal-network Streamlit tools — analyst dashboards, dev utilities, local AI tools, internal ops tooling. The fundamentals that matter to that audience are present: explicit process ownership, shell-free construction, graceful shutdown hooks (excellent for cleanup/backup/sync-on-close — a real Streamlit gap), sanitized diagnostics, repeatable profiles, and shortcuts that let a non-technical analyst double-click to launch. The recurring honesty ("LitLaunch does not magically make Streamlit secure") is itself a trust asset — corp reviewers distrust tools that overclaim.

What it does **not** yet give that audience, and should:

- A guardrail against the most common internal-tooling mistake: binding `0.0.0.0` and exposing an unauthenticated dashboard. Right now LitLaunch is silent.
- A documented threat model. An internal-tooling lead evaluating LitLaunch wants one page that says exactly what is and isn't protected.
- Trustworthy generated artifacts. The `.bat` quoting weakness directly hits this audience — corporate paths routinely contain spaces and `&`. A shortcut handed to an analyst must be correct.
- A lockdown/trust profile mode for "this profile is for an internal tool; refuse anything non-loopback."

With items 1–4 and 6–7 from §7, LitLaunch becomes something an internal platform team can adopt with a straight face. Today it's 80% there and the missing 20% is the part a security reviewer checks first.

## 9. Test & Release Readiness

**Strong overall.** 480 tests green in 9.6s; ruff lint + format clean. `scripts/check_release.py` is genuinely good: builds wheel+sdist, `twine check`, validates wheel/sdist contents and metadata, rejects forbidden archive entries (path traversal, `__pycache__`, `.pyc`), scans for suspicious repo-root artifacts (it even has a regex for the old `3.10\`` stray-file bug), and runs an installed-wheel smoke test in a temp venv covering `version/platform/browsers/help/inspect/report/command`. CI is modern: 3 OS × Python 3.10/3.12/3.14, lint, format, plus a dedicated release-hygiene job, `permissions: contents: read`, pinned `@v6` actions, 15-min timeouts. The prior audit's red metadata test is resolved and the editable-install caveat is now documented in the README and `installation.md`.

**Weak spots:**

- **`profile_wizard.py` and `profile_writer.py` have zero importing test files** (§6). The largest and a file-writing module, both untested. This is the headline test gap.
- **Tests pollute the repository root.** `tests/test_cli.py:50`, `test_release_hygiene.py`, `test_shortcut_writer.py`, and `test_profile_detection.py` create `tempfile.TemporaryDirectory(..., dir=Path.cwd())`. Cleanup is evidently failing — **six `litlaunch-test-*` directories are sitting in the repo root right now**. Use the `tmp_path` fixture with `monkeypatch.chdir` (the pattern `test_cli.py` already uses extensively elsewhere). At minimum, do not write temp trees into the project root.
- CI matrix omits Python **3.11 and 3.13**, which the `pyproject.toml` classifiers claim. The README discloses this honestly, and 3.10/3.12/3.14 bracket the gap — but a public release advertising 3.11/3.13 support without CI proof is a small risk.
- `test_launcher_browser.py`, `test_no_shell_true.py`, and the real-Streamlit smoke are single-test files — acceptable for narrow scopes, but `test_launcher_browser` (1 test) is thin for the browser-launch path.

**Verdict:** TestPyPI rehearsal — ready. Public PyPI — gated on the wizard/writer tests and the doc/host items below.

## 10. Remaining Risks / Weak Spots

Concrete, in priority order:

1. `profile_wizard.py` (992 lines) and `profile_writer.py` (196 lines) — **zero test coverage**.
2. **Silent non-loopback host binding** — no warning anywhere (config / profile / wizard / diagnostics).
3. **Six `[diagram needed]`/`[screenshot needed]` placeholders** ship in public docs.
4. **`docs/integration/packaging_notes.md` and `rolethread.md` are stale** — describe shipped features (shortcuts, profiles) as "not implemented" / "future."
5. **`shortcut_writer._quote_windows`** mis-quotes for `cmd.exe`; `%`/`&`/`^` in paths break the `.bat`.
6. **`_toml_string`** doesn't escape control characters; non-dry-run writes-then-validates, leaving a corrupt file on failure.
7. **GitHub org slug inconsistency:** `pyproject.toml` + `installation.md` + `test_metadata.py` use `github.com/Lattice-Foundry/LitLaunch`; **`examples/minimal_app/app.py` links to `github.com/LatticeFoundry/litlaunch` and `…/rolethread`** — wrong org slug, broken links, and they render in the running example app's UI.
8. `PortManager` is IPv4-only — IPv6 `host` breaks port resolution.
9. Tests write `litlaunch-test-*` dirs into the repo root; cleanup leaks.
10. Dead code: `ConsolePhase.RUNTIME`/`STOPPING_BACKEND`, `ANSI_COLORS["indigo"]`/`["cyan"]`. Four duplicated color mechanisms; the wizard bypasses `ConsoleRenderer`.
11. `cli/main.py` depends on the private `subparsers._choices_actions`.
12. CI omits Python 3.11/3.13 despite classifier claims.

## 11. Recommended Next Passes

**Pass A — release blockers (do before any public PyPI tag):**
- Add `test_profile_wizard.py` and `test_profile_writer.py`. Use the injectable `input_func` to drive Simple + Advanced flows, back/quit navigation, skip predicates, and overwrite/dry-run.
- Fix the example app's GitHub URLs to `Lattice-Foundry/LitLaunch` (and the RoleThread URL); add a `test_examples.py` assertion so it can't regress.
- Fill or remove the six doc placeholders.
- Refresh `docs/integration/packaging_notes.md` and `rolethread.md` to reality.

**Pass B — security/hardening pass:**
- Non-loopback host warning + explicit opt-in gate (§7.1).
- Diagnostics "Host binding" WARNING item (§7.2).
- `_toml_string` control-char escaping + validate-before-write.
- `_quote_windows` correctness for `cmd.exe` (`%`, `&`, `^`, doubled quotes).
- Give `SanitizedBundleRenderer` the strong `PRIVACY_NOTE`.

**Pass C — cleanup/maintainability:**
- Move test temp dirs to `tmp_path`; stop writing to the repo root.
- Fix `PortManager` IPv6 (`AF_INET6`/`getaddrinfo`).
- Delete dead `ConsolePhase` members and `indigo`/`cyan`; consolidate the four color mechanisms into one helper; route the wizard through `ConsoleRenderer`.
- Add Python 3.11 + 3.13 to the CI matrix (or drop the classifiers).
- Replace the `subparsers._choices_actions` hack.

**Pass D — corp/internal-tooling features (post-1.0-rc):**
- Profile lockdown/trust mode; opt-in runtime audit log; an honest internal-network deployment + threat-model doc page.

## 12. Final Verdict

LitLaunch is in real shape. The "significantly hardened and improved" claim is **largely justified** — the architecture absorbed a large feature wave (CLI split, diagnostics system, HTML reports, profile wizard, shortcuts, console overhaul) without losing coherence, the ownership invariants held, the prior audit findings closed, the suite is green, and the release tooling is better than most projects ship with at 1.0.

It is **not quite there for a confident public PyPI tag**, and the reason is a clean inversion: the newest, most user-visible feature surface — profile creation and shortcut generation — is also the **least tested and least hardened** code in the repo. A 992-line interactive wizard with zero automated tests, a TOML writer that can leave a corrupt file on disk, and a Windows `.bat` generator that mis-quotes paths is not what you want to be the first thing a new user touches. Pair that with six placeholder blocks in the shipped docs, two stale integration docs, and broken GitHub links in the example app, and the gap is one of *finish*, not *foundation*.

The security posture is honest and mostly solid — the loopback-only shutdown endpoint and the "own only what we start" discipline are exactly right. The one true hole is that LitLaunch will silently bind `0.0.0.0` and expose an unauthenticated Streamlit app with no warning. For a tool that markets itself as localhost-first to internal-tooling developers, that guardrail is the difference between "I trust this" and "I have to check."

Do **Pass A** and you have a defensible public release. Add **Pass B** and LitLaunch becomes something an internal platform team can adopt deliberately, not just try. The hard part — the architecture — is already done.
