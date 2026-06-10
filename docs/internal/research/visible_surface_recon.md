# LitLaunch Visible Surface Recon

> INTERNAL / RESEARCH DOCUMENTATION
>
> This document preserves pre-release visible-surface review notes. It is not
> part of the stable public LitLaunch documentation surface.

## 1. Executive Summary

LitLaunch’s runtime console is now the most polished visible surface. The remaining visible surfaces are mostly CLI help/output, inspect reports, generated diagnostics files, profile/dry-run output, browser/app-window behavior, and RoleThread-visible shutdown hook behavior.

The biggest next review target is **diagnostics output**, especially HTML and support bundle presentation. HTML diagnostics exists, is functional, and can be generated through the RoleThread sandbox today. It is safe and useful, but visually plain compared with the newly polished console. CLI help is mostly good, with one small wording drift around inspect `--output`.

I did not modify LitLaunch or RoleThread during this recon pass.

## 2. User-Visible Surface Inventory

| Surface | Module/File | Public/Beta/Internal | How to Invoke | RoleThread Exercisable | Notes |
|---|---|---:|---|---:|---|
| CLI top-level help | `src/litlaunch/cli/main.py` | Public beta | `python -m litlaunch.cli --help` | Yes | Clean, concise. Hidden `console-preview` does not appear. |
| CLI command help | `src/litlaunch/cli/main.py`, `cli/config.py`, `cli/inspect.py` | Public beta | `run --help`, `inspect --help` | Yes | Mostly accurate. Inspect `--output` help still says “JSON or bundle” though HTML is supported. |
| `version` output | `src/litlaunch/cli/commands.py` | Public beta | `python -m litlaunch.cli version` | Yes | Simple and fine. |
| `platform` output | `src/litlaunch/cli/commands.py` | Public beta | `python -m litlaunch.cli platform --no-color` | Yes | Minimal. Verbose mode should be reviewed once for raw detail shape. |
| `browsers` output | `src/litlaunch/cli/commands.py` | Public beta | `python -m litlaunch.cli browsers --no-color` | Yes | Readable; uses older `>` step style rather than bracket console style. Worth reviewing. |
| Command preview | `src/litlaunch/cli/commands.py`, `planning.py` | Public beta | `python -m litlaunch.cli command --profile rolethread-webapp` | Yes | Emits raw command only. Useful, not pretty. Probably correct for machine/copy usage. |
| Dry-run output | `src/litlaunch/cli/commands.py` | Public beta | `python -m litlaunch.cli run --profile rolethread-webapp --dry-run --no-color` | Yes | Uses polished bracket console plus command line. Looks good. |
| Runtime launch output | `runtime_console.py`, `console.py`, `launcher.py`, `backend_start.py`, `session.py` | Public beta | `python -m litlaunch.cli run --profile rolethread-webapp` | Yes | Already heavily polished. RoleThread is the best manual harness. |
| Browser/app-mode visible behavior | `browsers/*`, `monitored.py`, `launcher.py` | Public beta | `run --profile rolethread-webapp` | Yes | Needs manual visual confirmation: Edge app window title, app-mode feel, fallback behavior. |
| Window monitor behavior | `windowing/*`, `monitored.py`, `session.py` | Beta/platform-specific | close RoleThread app window after monitored launch | Yes | Needs manual observation. Current profile enables monitor. |
| Shutdown hook output | `shutdown.py`, `console.py`, RoleThread `core/runtime_shutdown.py` | Public beta API | close RoleThread app window | Yes | RoleThread registers `Cloud backup sync`; good real-world hook path. |
| Inspect text | `inspect/render_text.py` | Public beta | `inspect --profile rolethread-webapp --no-color` | Yes | Functional, readable, older `[OK]` style. Candidate for polish. |
| Inspect JSON | `inspect/render_json.py` | Public beta/machine output | `inspect --profile rolethread-webapp --json` | Yes | Stable and parseable. Should remain plain and machine-oriented. |
| Support bundle | `inspect/render_bundle.py` | Public beta/support artifact | `inspect --profile rolethread-webapp --bundle` | Yes | Useful and safe; maybe needs copy/readability pass. |
| HTML diagnostics | `inspect/render_html.py` | Public beta/support artifact | `inspect --profile rolethread-webapp --html --output ...` | Yes | Exists. Functional but visually plain; likely next polish target. |
| Inspect output file handling | `cli/inspect.py` | Public beta | `--output`, `--force` | Yes | Works for JSON/bundle/HTML. Help text needs update. |
| Profile loading errors | `profiles.py`, `cli/config.py` | Public beta | bad `--profile`, bad TOML | Yes | User-facing errors likely need review. |
| Config/validation errors | `config.py`, `ports.py`, `process.py`, `backend.py` | Public beta/API + CLI | invalid host/port/path/provider | Partly | Many exception strings are clear but not yet UX-reviewed as a set. |
| Console preview tooling | `cli/preview.py` | Internal/dev-facing | `console-preview --all|--normal|--verbose` | Yes, via LitLaunch not RT-specific | Documented in CLI docs; hidden from normal help. |
| Docs examples | `README.md`, `docs/*.md`, RoleThread docs | Public/dev | read docs | Yes | Mostly aligned. A few drift items below. |

## 3. Diagnostics / Inspect Findings

**Text inspect:** Works through RoleThread:

```powershell
X:\dev\rolethread-test\.venv\Scripts\python.exe -m litlaunch.cli inspect --profile rolethread-webapp --no-color
```

Observed sections: `LitLaunch`, `Platform`, `Streamlit`, `Browsers`, `Profile`, `Target`, `Summary`. Output is readable and reports `0 errors, 0 warnings` in the sandbox. It still uses `[OK]`, `[INFO]`, `[ERROR]` rather than the polished runtime bracket system. That may be okay because inspect is report-like, but it is visually now the older surface.

**JSON inspect:** Exists and works. It includes stable metadata:

- `schema_version`
- `generated_by`
- `litlaunch_version`
- `generated_at_utc`
- `ok/errors/warnings`
- `sections`

It is machine-readable and should not be over-polished.

**Support bundle:** Exists and works. It has a clear sanitization note and copyable text. It still includes non-home project paths like `X:\dev\rolethread-test\app.py`, which is probably useful for local support but should remain documented as something users review before sharing.

**HTML diagnostics:** Yes, implemented in `src/litlaunch/inspect/render_html.py`.

Generate through RoleThread:

```powershell
X:\dev\rolethread-test\.venv\Scripts\python.exe -m litlaunch.cli inspect --profile rolethread-webapp --html --output $env:TEMP\rolethread_litlaunch_report.html --force --no-color
```

Open the generated file in a browser. It is standalone, dependency-free HTML, no JS, no server. It is useful, but visually basic: default system font, simple sections, simple table, status colors. This is probably the highest-value visual polish target after console.

## 4. RoleThread Manual Viewing Workflow

From PowerShell:

```powershell
cd X:\dev\rolethread-test
.\.venv\Scripts\Activate.ps1
```

If activation is blocked by local execution policy, use the venv Python directly:

```powershell
X:\dev\rolethread-test\.venv\Scripts\python.exe -m litlaunch.cli version
```

Confirm LitLaunch editable source:

```powershell
X:\dev\rolethread-test\.venv\Scripts\python.exe -c "import litlaunch; print(litlaunch.__version__); print(litlaunch.__file__)"
```

Expected:

```text
0.91.9b0
X:\dev\litlaunch\src\litlaunch\__init__.py
```

Inspect profile and command planning:

```powershell
python -m litlaunch.cli inspect --profile rolethread-webapp --no-color
python -m litlaunch.cli inspect --profile rolethread-webapp --json
python -m litlaunch.cli inspect --profile rolethread-webapp --bundle
python -m litlaunch.cli inspect --profile rolethread-webapp --html --output litlaunch-report.html --force
python -m litlaunch.cli command --profile rolethread-webapp
python -m litlaunch.cli run --profile rolethread-webapp --dry-run --no-color
```

Manual runtime views:

```powershell
python -m litlaunch.cli run --profile rolethread-webapp --no-color
python -m litlaunch.cli run --profile rolethread-webapp --verbose
python -m litlaunch.cli run --profile rolethread-browser --verbose
```

For monitor/shutdown review:

1. Run `python -m litlaunch.cli run --profile rolethread-webapp --verbose`.
2. Confirm Edge app-mode window opens.
3. Confirm RoleThread UI appears.
4. Close the app-mode window manually.
5. Observe monitor close detection.
6. Observe `Shutdown:` and `Hook:` output.
7. Confirm backend exits and CLI returns.

RoleThread-specific hook path exists: `X:\dev\rolethread-test\core\runtime_shutdown.py` registers a `Cloud backup sync` shutdown hook and completion callback.

## 5. Editable Install Verification

Command:

```powershell
X:\dev\rolethread-test\.venv\Scripts\python.exe -c "import litlaunch; print(litlaunch.__version__); print(litlaunch.__file__)"
```

Observed:

```text
0.91.9b0
X:\dev\litlaunch\src\litlaunch\__init__.py
```

Also observed metadata:

```powershell
X:\dev\rolethread-test\.venv\Scripts\python.exe -c "import litlaunch, importlib.metadata as m; print(litlaunch.__version__); print(litlaunch.__file__); print(m.version('litlaunch'))"
```

Output:

```text
0.91.9b0
X:\dev\litlaunch\src\litlaunch\__init__.py
0.91.9b0
```

Normal LitLaunch source edits should be picked up after restarting RoleThread/LitLaunch processes. Reinstall is only needed for dependency, entry point, or package metadata changes.

## 6. Manual Test Matrix

| Surface | Command / Workflow | Expected Output | Inspect Visually |
|---|---|---|---|
| CLI help | `python -m litlaunch.cli --help` | Commands listed; no hidden preview command | Help clarity, no stale command names |
| Run help | `python -m litlaunch.cli run --help` | Profile, monitor, browser flags | Flag descriptions and wrapping |
| Inspect help | `python -m litlaunch.cli inspect --help` | JSON/bundle/HTML/output flags | `--output` help currently stale |
| Version | `python -m litlaunch.cli version` | `LitLaunch 0.91.9b0` | Version consistency |
| Platform | `python -m litlaunch.cli platform --verbose --no-color` | Platform summary/details | Detail names and readability |
| Browsers | `python -m litlaunch.cli browsers --verbose --no-color` | Browser capability list | Old `>` step style vs polished console |
| Command preview | `python -m litlaunch.cli command --profile rolethread-webapp` | Streamlit command only | Copyability, redaction |
| Dry run | `python -m litlaunch.cli run --profile rolethread-webapp --dry-run --no-color` | Bracketed runtime summary + command | Alignment, punctuation |
| Normal launch | `python -m litlaunch.cli run --profile rolethread-webapp --no-color` | Clean startup sequence | Console polish in real app |
| Verbose launch | `python -m litlaunch.cli run --profile rolethread-webapp --verbose` | More technical detail | Too much/not enough detail |
| Browser/app-mode | Launch `rolethread-webapp` | Edge app window opens | Title, app-mode behavior, fallback |
| Monitor close | Close Edge app window | Monitor close, shutdown, backend exit | Window close-to-exit timing |
| Shutdown hook | Close app with RT runtime hook configured | `Hook: Cloud backup sync...` | Hook message clarity and result |
| Inspect text | `inspect --profile rolethread-webapp --no-color` | Report sections, summary | Report readability |
| Inspect JSON | `inspect --profile rolethread-webapp --json` | Parseable JSON | Schema and sensitive data |
| Support bundle | `inspect --profile rolethread-webapp --bundle` | Copyable sanitized text | Support usefulness, path privacy |
| HTML diagnostics | `inspect --profile rolethread-webapp --html --output ... --force` | Standalone HTML file | Visual polish, print/share quality |
| Console preview | `console-preview --all|--normal|--verbose` | Simulated console language | Regression visualization only |

## 7. Priority Polish Candidates

**Must Review Before Beta Release**

1. **HTML diagnostics visual/readability pass**
   - Why: It is now a public beta support artifact and likely to be shared.
   - RoleThread can exercise it: Yes, with `inspect --profile rolethread-webapp --html`.
   - Likely polish: layout, spacing, status badges, table scanning, path wrapping, print/share quality.
   - Timing: Before broader beta distribution.

2. **Inspect/help wording drift**
   - Why: `inspect --help` says `--output` writes JSON or bundle, but HTML is supported too.
   - RoleThread can exercise it: Yes.
   - Timing: Tiny pre-beta fix.

3. **RoleThread runtime manual smoke**
   - Why: Console was polished via preview, but real app shutdown hook and monitor behavior should be seen end-to-end.
   - RoleThread can exercise it: Yes.
   - Timing: Before beta release.

**Should Review During RoleThread Integration**

4. **Text inspect/support bundle wording**
   - Why: These are support surfaces, and they still look like earlier report language.
   - RoleThread can exercise it: Yes.
   - Likely polish: concise section summaries, maybe align status language with console without making it noisy.

5. **Browser capability output**
   - Why: `litlaunch browsers` still uses `>` step lines, visually different from console polish.
   - RoleThread can exercise it: Yes.
   - Likely polish: either leave as report-like or convert to report/bracket style.

6. **Profile/config error messages**
   - Why: Bad profile/TOML/path/port errors will be common during integration.
   - RoleThread can exercise it: Yes by temporary bad configs.
   - Likely polish: ensure calm actionable output.

**Can Defer Until Public PyPI/Release**

7. **JSON diagnostics schema polish**
   - Why: Works and is machine-oriented.
   - RoleThread can exercise it: Yes.
   - Defer unless schema field names need final freeze.

8. **CLI top-level help styling**
   - Why: Argparse output is ordinary but acceptable.
   - Defer unless you want a custom help formatter later.

**Not Currently Implemented**

9. **Diagnostics dashboard/server**
   - HTML file exists; local dashboard/server does not.
   - Docs correctly say no diagnostics dashboard or web server.

## 8. Documentation Drift / Follow-up

Concrete drift found:

- `src/litlaunch/cli/inspect.py` help for `--output` says: “Write JSON or bundle inspect output to a UTF-8 file.” It should mention HTML too.
- `docs/integration/rolethread.md` says “Future launch profiles may help...” but launch profiles now exist. That doc should be updated.
- RoleThread sandbox `requirements.txt` contains commented `#litlaunch==0.91.0b0`; since editable install is being used this is not functionally wrong, but it is stale and may confuse future readers.
- RoleThread docs are mostly current and already mention:
  - `python -m litlaunch.cli run --profile rolethread-webapp`
  - `python -m litlaunch.cli inspect --profile rolethread-webapp`
  - HTML report generation.
- LitLaunch docs correctly mention HTML diagnostics as implemented and diagnostics dashboard/server as not implemented.
- No stale `console-preview-norm`, `console-preview-verb`, or preview `--no-color` docs found in LitLaunch public docs.

## 9. Recommended Next Pass

**Recommended next focused pass: Diagnostics Surface Polish Pass 1**

Scope should be small and concrete:

- Fix inspect `--output` help text to include HTML.
- Update stale RoleThread integration doc wording around profiles.
- Do a visual polish pass on `HTMLDiagnosticsRenderer`.
- Keep JSON schema unchanged.
- Keep collection behavior unchanged.
- Generate HTML through `X:\dev\rolethread-test` and review in browser.
- Optionally make text/bundle status labels slightly cleaner, but do not redesign all diagnostics in the same pass.

This gives you the highest visible value after the console work without touching runtime ownership or browser behavior.
