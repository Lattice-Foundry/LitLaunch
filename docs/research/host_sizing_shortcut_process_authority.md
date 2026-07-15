# LL-HS5 Exact Windows Shortcut Authority and Private Activation Gate

- Date: 2026-07-14
- LitLaunch reference: 1.0.10
- Design references: `litbridge_host_sizing_consumption_recon.md`,
  `host_sizing_geometry_authority_spike.md`,
  `host_sizing_transport_trust_foundation.md`,
  `host_sizing_policy_state_machine.md`,
  `host_sizing_windows_mutation_capability.md`, and
  `host_sizing_private_integration.md`
- Scope: private Windows Edge and Chrome process/window authority only

## Verdict

**SHORTCUT AUTHORITY PROVEN**

LitLaunch can retain an exact browser root process identity from managed-profile Edge
and Chrome app-mode launches made either directly or through the temporary Windows
icon shortcut. Both forms now produce the same immutable private authority model and
the same bounded, creation-time-aware descendant tracking.

One private activation gate can use that process authority to select exactly one new,
stable Chromium app HWND without title inference. The gate revalidates the process
tree immediately before and after LL-HS3 mutation. Any missing, stale, ambiguous,
truncated, inaccessible, or mismatched authority disables host sizing while normal
launch behavior continues.

Real Edge and Chrome direct and shortcut probes each completed one authenticated
LL-HS4 report, policy decision, exact height mutation, and acknowledgement. The full
private pipeline is now production-authority complete for Windows managed-profile
Edge and Chrome webapp launches. It remains inactive and has no public product
surface.

## Previous shortcut limitation

The temporary icon shortcut already contained the final browser executable, complete
app-mode argument list, managed `--user-data-dir`, working directory, icon, and stable
AppUserModelID. The missing value was the process that Windows created after opening
the `.lnk`.

The prior `os.startfile(...)` call provided normal shell activation but returned no
handle or PID. Shortcut intent, AppUserModelID, title, timing, and visible windows do
not prove process ownership. LL-HS4 therefore retained direct-launch PID metadata but
correctly left shortcut launches ineligible.

## Launch options evaluated

### Resolve the shortcut and launch its target directly

LitLaunch already knows the target and arguments before writing the shortcut, so it
could bypass the `.lnk` and call `Popen`. That would retain a PID, but it would stop
testing and using the shell activation path that gives the shortcut its presentation
identity. It would also create two argument/quoting paths for the same launch. This
was not selected.

### ShellExecuteEx with a returned process handle

`ShellExecuteExW` supports `SEE_MASK_NOCLOSEPROCESS`, which requests the launched
process handle while preserving shell activation of the `.lnk`. LitLaunch uses the
ordinary `open` verb plus `SEE_MASK_NOASYNC`, `SEE_MASK_FLAG_NO_UI`, and Unicode mode.
It reads the PID and process creation FILETIME, then closes the raw handle immediately.

This is the selected mechanism. It is the smallest change that preserves shortcut
appearance, arguments, profile behavior, app-mode behavior, shell semantics, and
testability while returning exact process identity.

Windows documents cases where shell activation can succeed without returning a
process handle. LitLaunch treats that as normal launch success with private authority
unavailable. It does not infer a replacement PID.

### Temporary wrapper process

A wrapper could launch Chromium and report a PID, but it would add another executable,
handoff protocol, lifecycle, quoting boundary, and security surface. It provides no
benefit over the shell process handle and was rejected.

### Post-launch process reconciliation

Keeping `os.startfile` and searching afterward would require correlation by time,
profile path, title, or a nearest-process heuristic. Those signals cannot establish
an exact root in the presence of existing browser processes. This option was rejected
as weak authority.

### Exclude shortcuts from host-sizing eligibility

This would remain safe but leave the common custom-icon webapp path unsupported. It
was the LL-HS4 fallback, not the LL-HS5 target.

## Process-authority model

`BrowserLaunchAuthority` is private and frozen. It contains:

- a random opaque launch ID;
- root PID and process creation time in Windows FILETIME units;
- explicit Edge or Chrome identity;
- exact executable path;
- LitLaunch-owned managed profile path;
- direct or Windows-shortcut launch strategy; and
- monotonic launch time.

Authority is created only for explicit Edge or Chrome commands containing a
LitLaunch-owned `--user-data-dir`. Direct launch obtains the root PID from `Popen` and
queries its image and creation time. Shortcut launch obtains both values from the
short-lived `ShellExecuteExW` process handle. No raw handle survives authority
creation, and the authority does not imply process ownership.

`BrowserLauncher` retains the immutable value privately. `StreamlitLauncher` copies it
into `RuntimeSession`, where it remains available for private authority collection.
Session cleanup invalidates it before running artifact callbacks. No stop, terminate,
kill, or browser-process wait behavior was added.

## Descendant tracking

The private Windows tracker captures the process table through Toolhelp and enriches
records with `OpenProcess`, `GetProcessTimes`, and `QueryFullProcessImageNameW`. It is
bounded to:

- 4,096 process-table records;
- 256 launch descendants; and
- 12 ancestry levels.

The root must continue to match both its creation time and executable. Descendants
must be connected to that root, have creation times at or after the root, and remain
inside the traversal bounds. Browser PID authority includes only records whose image
matches the exact launched executable. Non-browser helper descendants may be crossed
for ancestry but never become authorized browser PIDs.

If the initial root exits after spawning Chromium children, the tracker can retain the
creation-time-valid descendant branch through the recorded parent PID. A reused root
PID, unreadable root identity, truncated table, excessive tree, capture error, or loss
of all exact browser descendants fails closed. Each capture is fresh, so exited
descendants disappear rather than remaining in a stale PID set.

## Exact HWND authority

The private activation gate is disabled unless its internal caller explicitly passes
`private_enabled=True`. It also requires:

1. Windows and `webapp` mode;
2. explicit Edge or Chrome;
3. a LitLaunch-owned managed profile;
4. retained exact launch authority;
5. a live creation-time-valid process tree;
6. a visible HWND not present in the pre-launch baseline;
7. a PID in the exact browser process set;
8. the validated `Chrome_WidgetWin*` app-window class and browser process name;
9. exactly one candidate stable for at least three polls; and
10. normal immutable baseline geometry.

The window title is not consulted. More than one candidate fails immediately, no
candidate times out, and a changing HWND never reaches authority promotion.

The promoted `WindowSizingAuthority.authority_id` is the same opaque launch ID used by
transport and policy. A process-bound verifier refreshes the browser tree immediately
before and after LL-HS3 mutation, requires the authorized HWND PID to remain inside
that tree, then delegates to the existing exact HWND/PID verifier. Transport
`source_id` never participates in native process or window authority.

## Direct and shortcut parity

Both launch forms preserve the same browser command and managed-profile arguments.
Their only intentional authority difference is how the root identity is acquired:

| Launch form | Root PID source | Creation-time source |
| --- | --- | --- |
| Direct | `subprocess.Popen.pid` | immediate process query |
| Windows shortcut | `ShellExecuteExW` process handle | `GetProcessTimes` on that handle |

The shortcut file, icon, AppUserModelID, working directory, command arguments, cleanup
callback, and launch message remain unchanged. A shortcut write/open failure retains
the existing direct-launch fallback. Shell success without a process handle keeps the
shortcut launch successful but host sizing ineligible.

## Real-browser evidence

Test host:

- Windows `10.0.26200.0`;
- Microsoft Edge `150.0.4078.65`;
- Google Chrome `150.0.7871.116`;
- 96-DPI primary display for this matrix.

Each run used a unique LitLaunch-owned profile, a new app-mode window, an authenticated
loopback report, and the production-shaped private gate and coordinator.

| Browser | Launch | Root retained | Exact HWND | Report | Viewport | Result |
| --- | --- | --- | --- | --- | --- | --- |
| Edge | direct | yes | stable for 3 polls | HTTP 202 | 761 to 881 CSS px | applied |
| Edge | shortcut | yes | stable for 3 polls | HTTP 202 | 761 to 881 CSS px | applied |
| Chrome | direct | yes | stable for 3 polls | HTTP 202 | 761 to 881 CSS px | applied |
| Chrome | shortcut | yes | stable for 3 polls | HTTP 202 | 761 to 881 CSS px | applied |

All four measured zero CSS-pixel error. Native left, top, and width were unchanged.
Each policy reached `complete` after exactly one mutation call and one acknowledgement.

Eighteen unrelated Edge processes were already running during both Edge probes. They
were excluded from the launch tree and HWND candidates. A separate Chrome isolation
probe kept one unrelated managed Chrome app open while launching direct and shortcut
targets. Both target process sets were disjoint from the existing app, the existing
HWND was in the pre-launch baseline, and only each new target HWND was selected.

Probe cleanup sent `WM_CLOSE` only to the exact owned probe HWND so browser exit could
be observed without process termination. Every browser tree exited naturally. All
temporary profiles and shortcut files were removed, and the unrelated existing Edge
processes remained running.

## Deterministic proof

The LL-HS5 matrix covers:

- Edge and Chrome direct/shortcut metadata parity;
- exact root PID, creation time, browser, profile, strategy, and launch-ID binding;
- quoted paths and spaces in executable/profile paths;
- immutable authority values and LitLaunch ownership requirements;
- valid descendants, root exit with descendant handoff, stale descendant removal,
  unrelated branches, wrong images, pre-launch children, capture errors, traversal
  bounds, unreadable roots, and PID reuse;
- exact, absent, ambiguous, pre-existing, unstable, title-only, wrong-process, unsafe
  state, shutdown, and authority-loss HWND outcomes;
- launch-ID and process-tree revalidation at mutation time;
- authority retention through `RuntimeSession` and invalidation on shutdown;
- no browser termination surface or browser stop call;
- shortcut failure and no-handle behavior preserving normal launch; and
- absence from package exports and normal launcher activation.

Final validation evidence:

- focused LL-HS5 authority, browser launch, shell, session, and gate matrix:
  110 passed;
- full `python -m pytest`: 1,010 passed, including the real Streamlit smoke test;
- `python -m ruff check .`: passed;
- `python -m ruff format --check .`: 129 files already formatted;
- `python -m mypy src/litlaunch`: passed for 82 source files;
- `python scripts/check_release.py`: passed, including wheel/sdist build, Twine
  checks, isolated wheel install, CLI smoke checks, and version 1.0.10; and
- `git diff --check`: passed.

## Security and regression review

- No title, timing, AppUserModelID, URL, or nearest-process heuristic grants authority.
- No untrusted report field controls PID, process ancestry, HWND, or native authority.
- Launch ID binds browser authority, window authority, transport, and policy.
- Capability tokens remain confined to LL-HS1 and never enter process metadata.
- Process records and HWND authority are private and absent from user-facing events.
- Normal launches do not import or call the activation gate and do not wait for it.
- Browser close monitoring remains observation-only and unchanged.
- RuntimeSession still owns only the backend process; browser authority is
  identification metadata.

## Limitations

1. Windows may complete a shell activation without returning a process handle. In
   that case normal launch succeeds and host sizing remains off; no weaker authority
   fallback exists.
2. Process-table access, image queries, or configured traversal bounds can fail on a
   hardened host. This produces a safe false-negative rather than mutation.
3. Exact authority is proven only for Windows managed-profile Edge and Chrome app
   mode. Browser mode, default-browser launch, tabs, other Chromium builds, and other
   operating systems remain ineligible.
4. Chromium process and window behavior was exercised on the versions above. Future
   browser changes can disable the capability through the fail-closed checks.
5. Win32 process/window verification and `SetWindowPos` are not one atomic operating-
   system transaction. Immediate pre/post identity and geometry checks detect drift
   but cannot remove the underlying race.
6. The measurement adapter, private environment injection, and normal-launch
   coordinator startup remain intentionally disconnected. Production authority is
   complete; product activation is not.

## Next gate

LL-HS6 may evaluate private production-path activation and the public-surface design
gate. It must preserve default-off behavior until the measurement handoff, lifecycle,
and user-facing contract are independently approved.

**SHORTCUT AUTHORITY PROVEN**
