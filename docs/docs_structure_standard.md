# Documentation Structure Standard

> Local note: LitLaunch follows Profile A. `docs/internal/**` is intentionally
> absent from tracked public source after the 2026-06-14 exposure remediation
> pass.

**Status:** Proposed v1.0 (derived from the LitBridge/LitPack emerging standard)
**Applies to:** repositories under the production, experimental, and web workspace roots, and all future SCG / LatticeFoundry projects
**Companion document:** workspace documentation structure audit
**Date:** 2026-06-14

> This is a reusable standard a new project can adopt from day one without guessing. Existing projects adopt it via the migration sequence in the audit report. This document defines *target state*; it does not itself move or change any existing file.

---

## 1. Purpose and Scope

This standard defines **where documentation lives, who it is for, and whether it is committed**, consistently across every project in the workspace. It exists to:

- Give every repo one predictable place for public docs and one predictable set of internal categories.
- Keep a hard line between **audience** (public vs internal) and **git hygiene** (tracked vs ignored) so neither decision contaminates the other.
- Make the layout **machine-validatable** later (the rules in §17 are written to be automatable).
- Let new projects bootstrap a correct structure in minutes (§18–19).

**In scope:** folder layout, naming/casing, tracking policy, public/internal classification, root files, indexes, archival, source-of-truth, Markdown-first policy, privacy review, and `.gitignore`/`.gitkeep` conventions.

**Out of scope:** doc *content* quality, doc tooling/site generators, and code structure.

---

## 2. Workspace Applicability

| Project class | Location | Profile | Notes |
|---|---|---|---|
| App / library / tool | production and experimental project roots | **Profile A** | Default for anything with a package surface (`pyproject.toml`/`Cargo.toml`/`package.json` for a shipped tool), `src/`, tests. |
| Website | web project roots | **Profile B** | Private repo, public rendered output. Content lives in the site source tree, not `docs/Public/`. |
| Experimental prototype | experimental project roots | Profile A (by default) | Lifecycle is "experimental"; docs *profile* is still A unless it is a website. |
| Placeholder / inactive | e.g. `prod\litserver` | Defer | Adopt Profile A when the project becomes active. |

The two non-website experimental projects (`noesiz`, `rinno`) use **Profile A** plus the **legal/lineage** internal folders (§9), because they are a Streamlit fork and an Inno clean-room reimplementation respectively.

---

## 3. The Core Public/Internal Boundary Rule

**Two independent axes. Never collapse them.**

- **Audience** answers *"who is this written for?"* → `public` | `internal` | `unclear`.
- **Git tracking** answers *"is this committed to the repo?"* → `tracked` | `ignored`.

> **Internal does NOT mean ignored.** Durable internal docs (audits, architecture, research, plans) are **tracked** when they are durable, intentional, and safe for the repository's visibility level. Only *scratch/transient/private-local* notes are ignored.

> **Public does NOT mean tracked-anywhere.** Public-facing documentation must live **only** in `docs/Public/**` or in an approved root file (§6). It must never sit loose in `docs/` once this standard is adopted.

### Audience classification rules
- **Public** = written for end users / external integrators / the public web. Examples: help articles, FAQs, getting-started guides, API/CLI reference, troubleshooting, public security posture.
- **Internal** = written for the team/maintainers. Examples: audits, architecture rationale, planning/roadmaps, research/recon, implementation notes, migration plans, private release notes, test plans, security-sensitive working notes.
- **Unclear** = mark as a human decision (§16); do not guess.

### Tracking decision rule
A doc is **tracked** when it is **durable AND safe for the repo's current visibility**. It is **ignored** when it is scratch/transient, machine-local, or unsafe to commit at the repo's visibility level. A **public repo** raises the safety bar: internal docs containing local paths, unannounced features, or security-sensitive detail are *not* "safe" to track there (see §15).

---

## 4. Profile A — App / Library / Tool Projects

**Public surface:** approved root files (§6) + `docs/Public/**`.
**Internal surface:** the flat category folders under `docs/`.

```text
docs/
  README.md                 # docs index (layered: Start here -> Public -> Records)
  Public/                   # the ONLY public-facing docs tree
    Help/                   # task-oriented how-to articles (manifest-driven when app-rendered)
    FAQ/                    # frequently-asked questions (prose .md and/or machine-readable data)
    Guides/                 # narrative onboarding / adoption / conceptual guides
    Reference/              # API / CLI / config / compatibility reference
    Troubleshooting/        # symptom -> fix
  architecture/             # design rationale, boundaries, subsystem notes
  audits/                   # internal + third-party audit/review records
  planning/                 # roadmaps, milestone plans, handoff checklists
  research/                 # recon, spikes, viability, design exploration
  implementation/           # implementation notes/specs tied to a build
  migrations/               # extraction/integration/upgrade plans
  release/                  # private release notes, release-gate checklists
  security/                 # internal security notes, hardening, threat notes
  testing/                  # test plans, matrices, validation runs
  archive/                  # superseded/deprecated docs kept for history
  legal/                    # OPTIONAL: attribution/clean-room posture (forks/clean-room)
  lineage/                  # OPTIONAL: upstream import/rename provenance (forks)
```

**Renames vs current workspace usage** (so existing repos converge): `roadmap`/`roadmaps` → **`planning`**; `validation` → **`testing`** (validation runs are testing records); `docs/spec/` → **`docs/architecture/spec/`** or **`docs/implementation/spec/`**; `docs/help/` → **`docs/Public/Help/`**.

### Profile A internal folders — definitions

| Folder | Holds | Tracked by default? |
|---|---|---|
| `architecture/` | Design rationale, component/runtime boundaries, subsystem design | Yes |
| `audits/` | Internal and third-party audit/review reports with verdicts | Yes |
| `planning/` | Roadmaps, milestone/pass plans, handoff checklists | Yes |
| `research/` | Recon, spikes, viability, design exploration | Yes (durable); ignore scratch via `research/scratch/` |
| `implementation/` | Build-tied implementation notes and internal specs | Yes |
| `migrations/` | Extraction/integration/upgrade/migration plans | Yes |
| `release/` | Private release notes, release-gate checklists | Yes |
| `security/` | Internal security/hardening/threat notes | Yes (only if safe for visibility) |
| `testing/` | Test plans, matrices, validation runs | Yes |
| `archive/` | Superseded docs kept for history | Yes |
| `legal/` *(opt)* | Attribution, clean-room posture (public-safe) | Yes (force-track) |
| `lineage/` *(opt)* | Upstream import manifest / rename map | Yes (force-track) |

---

## 5. Profile B — Website Projects

Website repos are **private at the repo level** even when the rendered site is public. Website source content (routes, pages, components, generated docs) stays in the **website source tree** (`src/`), never in `docs/Public/`.

```text
docs/
  content/        # site copy / messaging / content strategy (internal authoring)
  design/         # design system, brand tokens, visual language
  deployment/     # build/adapter/hosting/CI/headers notes
  dns/            # domain + subdomain topology, records
  operations/     # runbooks, ops references (e.g. payment/ledger infra)
  analytics/      # measurement plan, dashboards, KPIs
  planning/       # roadmap, implementation doctrine, launch sequencing
  research/       # competitive/UX/market research
  archive/        # superseded site docs
  Public/         # OPTIONAL: only for standalone public docs separate from the site
```

### Website-specific rules
- **Site content stays in `src/`.** Routes, pages, components, and generated docs (e.g. `src/lib/generated/docs/**`) are website *source/build output* and must not move to `docs/Public/`. Moving them breaks route imports.
- **`docs/Public/` is optional** and used only when the repo intentionally stores standalone public documents *separate from the rendered site itself*.
- **Generated/synced docs** (produced from upstream product repos via a sync script + manifest) are tracked so the site builds without re-running sync, but they are **derived** — never hand-edited. Their source of truth is the upstream product repo (§14). Consider a CI check that fails if the generated tree is stale.
- **Sync/build config** (e.g. `docs/docs-sync.manifest.json`) is tooling, not a relocatable doc; keep it where the script resolves it.
- **Internal ops/infra docs** (payment, DNS, deployment) are tracked in a private website repo **but must never be rendered to a route**. Place them under `docs/operations|deployment|dns`, never `docs/Public/`.

---

## 6. Approved Project-Root Documentation Files

Only these doc-class files belong at the repo root (everything else goes under `docs/`):

| File | Profile A | Profile B | Notes |
|---|---|---|---|
| `README.md` | required | required | Public front door. |
| `CHANGELOG.md` | required | optional | The single release-history source of truth. |
| `LICENSE` | required | as applicable | Public license (or proprietary marker). |
| `SECURITY.md` | recommended | optional | Public security/disclosure policy; may point to `docs/Public/Reference/security.md`. |
| `CONTRIBUTING.md` | recommended | optional | Contributor guide; may absorb a `docs/development.md`. |
| `NOTICE` | if required | — | Attribution notice (forks; Apache convention). |
| Package metadata | required | required | `pyproject.toml`, `Cargo.toml`/`Cargo.lock`, `package.json`, `MANIFEST.in`, `.gitattributes`, etc. |

**Not approved at root:** strategy docs, design systems, doctrine, roadmaps, release notes as a second file (`RELEASE_NOTES.md` → fold into `CHANGELOG.md` or `docs/release/`), or any UPPERCASE prose doc. These belong under `docs/`.

---

## 7. Public vs Internal Documentation Rules (applied)

1. Public docs live **only** under `docs/Public/**` or as an approved root file. Never loose in `docs/`.
2. `docs/README.md` (the index) is the one permitted Markdown file directly in `docs/`; everything else is in `Public/` or a category folder.
3. Internal docs live under their category folder. They may be tracked (§3) but never under `docs/Public/`.
4. The same audience classification must hold across repos: a "recon/pass research note" is `internal/research` everywhere; a "help article" is `public/Help` everywhere.
5. On a **public** repo, treat the entire internal tree as never-public and verify it is safe to track (§15); if not, scrub or ignore it.

---

## 8. Git Tracking vs Audience Classification Rules

| Audience \ Tracking | tracked | ignored |
|---|---|---|
| **public** | normal case: `docs/Public/**`, root files, website generated docs | almost never (a public doc should be committed) |
| **internal** | normal case: durable `docs/<category>/` when safe for visibility | scratch lanes, local-only notes, unsafe-on-public-repo material |

Decision flow:
1. Determine **audience** first (public / internal / unclear).
2. If unclear → human decision (§16); stop.
3. Determine **durability** (will this matter next month?) and **safety** (no secrets; no local paths/unannounced features if the repo is/maybe public).
4. Durable + safe → **track**. Scratch or unsafe-for-visibility → **ignore** (and, if durable-but-unsafe, scrub so it *can* be tracked, or keep it in an ignored lane / private repo).

**Track-when-safe, never-track lists:**
- Normally **tracked**: `docs/Public/**`, all approved root files, durable `docs/<category>/` files, `legal/` + `lineage/`, website generated docs + sync manifest.
- Normally **ignored**: `docs/**/scratch/`, `docs/**/tmp/`, `docs/**/inbox/`, `docs/private/`, `docs/local/`, top-level `notes/`, `scratch/`, `*.bak`, `*.tmp`, `*.log`.

---

## 9. Approved Internal Folders + Legal/Lineage Addition

The standard internal set is the eleven Profile A folders in §4. **This standard adds `legal/` and `lineage/`** as approved internal folders (they were not in the original baseline) because forked/clean-room products need version-controlled provenance:

- `docs/legal/` — attribution, clean-room posture, modification-tracking policy. **Force-tracked** even under broad ignore rules, so attribution can never be accidentally omitted from a public release.
- `docs/lineage/` — upstream import manifest, rename/translation map.

Clean-room *hazard inventories* and detailed recon (the "do-not-port" lists) are **internal-detail** and may stay in an ignored lane; the **public-safe summary** (attribution, boundaries) belongs in `docs/legal/` (tracked) or `docs/Public/Reference/`. Keep these layered, not duplicated.

---

## 10. Folder Naming and Casing Rules

- **Internal category folders:** lowercase, single word, as named in §4 (`architecture`, `audits`, `planning`, `research`, `implementation`, `migrations`, `release`, `security`, `testing`, `archive`, `legal`, `lineage`). No plurals beyond those listed (use `planning`, not `roadmaps`).
- **Public tree:** `docs/Public/` with TitleCase subfolders `Help/`, `FAQ/`, `Guides/`, `Reference/`, `Troubleshooting/`. The TitleCase is a **deliberate exception** mirroring `README.md`, signaling "public surface." (If a project prefers all-lowercase, it must apply that choice consistently and document it — but the workspace default is TitleCase for the public tree only.)
- **No file/folder name collisions:** never have `docs/X.md` and `docs/X/` as siblings (e.g. `integration.md` + `integration/`). Use `docs/X/index.md` (or `README.md`) instead.
- **Index files:** uppercase `README.md` (consistent with the root `README.md`).
- **Case-rename caution:** case-only renames (`help` → `Help`) need care on case-insensitive Windows + case-sensitive git (use `git mv` through a temporary name).

---

## 11. File Naming Rules

- **Public Help/FAQ/Guides/Reference/Troubleshooting files:** **kebab-case** (`getting-started.md`, `recipe-lifecycle.md`). This matches site slugs and the generated website tree. Do **not** carry ordering in the filename (no `00_`, `01_` prefixes) — drive order from the help manifest's `order` field.
- **Internal docs:** **snake_case** (`design_principles.md`, `runtime_validation_01.md`) is the workspace convention and matches the Python codebases. Pick one separator per repo and apply it consistently (do not mix snake and kebab within one internal tree).
- **Series / dated artifacts:** zero-padded numeric suffix for repeated artifacts (`internal_audit_01.md`, `audit_02.md`); embed version/milestone anchors where relevant (`foundation_audit_0_5_10.md`).
- **No spaces, no UPPERCASE prose filenames, no legacy product names.** (Rename legacy names such as "LoreForge" → current product name before promoting any doc to tracked.)
- **Per-doc front-matter (recommended):** internal docs carry a header with `Status`, `Date`, `Scope`, and (for audits) `Verdict`, for an auditable trail. Dates are absolute.

---

## 12. `.gitkeep` Rules for Required-but-Empty Folders

- Every **required** standard folder that would otherwise be empty carries a **tracked `.gitkeep`** so the structure exists in a fresh clone.
- This applies to scaffolded-ahead-of-content folders, especially `docs/Public/{Help,FAQ,Guides,Reference,Troubleshooting}/` and any internal lane created before its first real doc.
- **Reference pattern (from rolethread):** `app_data/* ` ignored with `!app_data/.gitkeep` — keeps a required-but-empty folder tracked. Replicate this idiom.
- If a repo uses a broad ignore rule that would hide a needed folder (e.g. noesiz `docs/*/`), add an explicit negation (`!docs/<folder>/` + `!docs/<folder>/.gitkeep`) rather than relying on the broad rule.
- Remove a folder's `.gitkeep` once it has real tracked content (optional; harmless to keep).

---

## 13. Folder `README.md` / Index-File Policy

- **`docs/README.md` is required** and is the canonical documentation map. Use the layered template:
  1. **Start here** — links to the project README + `docs/Public/` entry points.
  2. **Public docs** — `docs/Public/{Help,FAQ,Guides,Reference,Troubleshooting}/`.
  3. **Project records** — internal folders, explicitly annotated as *history/rationale, not onboarding*.
- **Per-folder `README.md` index stubs are recommended** for each internal category (one short paragraph: purpose, audience, tracked-vs-ignored status). This makes the structure self-describing at every level.
- **Index links must resolve in a fresh clone.** Never link the index to an ignored folder. If a category is ignored, either track it (preferred) or omit it from the index.
- **App-rendered help** keeps a machine-readable manifest (`help_manifest.json`) as the canonical index for `docs/Public/Help/`; the per-article `.md` files hold content only.

---

## 14. Archive / Deprecated-Doc Policy

- Superseded docs are **moved to `docs/archive/`**, not deleted (preserve history and rationale).
- An archived doc keeps its original filename and gains a short header note: `Status: Superseded YYYY-MM-DD by <path>`.
- Do not edit archived docs except to add the supersession note.
- Stale *descriptions inside* a still-relevant doc (e.g. an audit describing an old policy) are left as historical record; add a one-line addendum rather than rewriting, and rely on the source-of-truth doc (§15) for current state.
- Build artifacts that bundle docs (e.g. an installer's copied help tree) are **not** archive material — they are regenerated from source and stay ignored.

---

## 15. Source-of-Truth Policy

- Each documented topic has **exactly one** source-of-truth doc. Other mentions **link** to it; they do not re-copy content.
- **Never copy a doc across repos.** Cross-repo references link to the owning repo's source-of-truth (re-copying causes silent drift, especially when one copy is ignored).
- **Generated/synced docs are derived, never authoritative.** The upstream product repo owns the content; the website's generated tree renders it.
- **Release history:** `CHANGELOG.md` is the single source of truth; do not maintain a parallel `RELEASE_NOTES.md`.
- **Layered (not duplicated) docs are allowed** when they serve different audiences: a public summary + an internal detailed version (e.g. clean-room: public posture in `docs/legal/`, detailed hazard inventory in an ignored internal lane). State the relationship explicitly.
- When two docs conflict, the standard names the source of truth and the other becomes a pointer or moves to `archive/`.

---

## 16. Markdown-First Policy and Allowed Exceptions

**All prose documentation is Markdown (`.md`).** Justified non-Markdown exceptions:

| Allowed non-`.md` | When |
|---|---|
| `.json` | Machine-readable manifests / FAQ data the app consumes (`help_manifest.json`, `faq.json`, `docs-sync.manifest.json`). |
| `.toml` / `.ini` / `.cfg` | Package metadata and tool config (`pyproject.toml`, `Cargo.toml`, `pytest.ini`). |
| `.txt` (specific) | Web-spec/served formats (`robots.txt`, `.well-known/security.txt`, `_headers`), license texts (`OFL-*.txt`), `NOTICE`, `VERSION`. |
| `.xml` | Machine-readable feeds (`sitemap.xml`). |
| `.png` / images | Screenshots/diagrams embedded in docs. |

**Not justified:** prose in `.docx` or generic `.txt` (e.g. a development plan or audit kept as `.docx`/`.txt`). Convert to `.md` before tracking. A binary original may be kept only as an *ignored* artifact, with the tracked `.md` as the source of truth.

---

## 17. Privacy / Public-Boundary Review Checklist

Run this before promoting any doc into `docs/Public/**`, before rendering anything to a website, and before flipping any repo to public visibility:

- [ ] **No local machine paths** — local workspace roots, user-home paths, tool-install paths, or machine-specific absolute paths.
- [ ] **No secrets** — API keys, tokens, passwords, webhook secrets, credentials, connection strings. (Env-var *names* alone are lower-risk but still belong in internal ops docs, not public.)
- [ ] **No private endpoints / infra detail** — internal webhook URLs, table/bucket names, region/profile, schemas (keep in `docs/operations`/`security`, never `Public/`).
- [ ] **No unannounced features / roadmap** unless deliberately disclosed with a clear "not a commitment" disclaimer (and owner sign-off).
- [ ] **No business/pricing strategy**, founder-program economics, or division positioning.
- [ ] **No `internal` / `private` / `do not publish` / `confidential` markers** in a public doc.
- [ ] **No TODO/DRAFT placeholder language** in published docs.
- [ ] **Forked/clean-room safety** — public attribution is present; detailed do-not-port/hazard inventories remain internal.
- [ ] **Generated docs** carry source-commit/version stamps and match upstream (not stale).

Severity model: distinguish **currently-exposed** (live on a public repo/site now → act immediately) from **tracked-but-private** (safe while the repo is private → fix before any public flip).

---

## 18. `.gitignore` and Tracking Policy

Each repo's `.gitignore` carries a **documentation-policy comment block** stating the tracked/ignored boundary in plain terms (the LitBridge model). Recommended canonical block:

```gitignore
# Documentation policy (audience != tracking):
# Public docs (docs/Public/**) and durable internal docs
# (docs/{architecture,audits,planning,research,implementation,migrations,
#  release,security,testing,archive,legal,lineage}) are TRACKED by default.
# Only scratch/private/local note lanes are ignored.
docs/**/scratch/
docs/**/tmp/
docs/**/inbox/
docs/private/
docs/local/
notes/
scratch/
*.bak
*.tmp
*.log
```

Rules:
- **Do not blanket-ignore `docs/<subfolder>/`.** If a broad rule is unavoidable (e.g. a pre-public prototype), use explicit negations to keep durable trees and `legal/`/`lineage/` tracked, and add `.gitkeep` for required-empty folders.
- **Scratch whitelist idiom (LitPack model)** is allowed for a mostly-scratch folder: `docs/research/scratch/*` ignored with `!` un-ignores for the few durable files — but prefer a dedicated `research/scratch/` lane over ignoring all of `research/`.
- **Durable internal docs must not be hidden** in an ignored `notes/`/`internal/`/`.dev/` tree. Promote them into a tracked `docs/<category>/` (after rename/scrub) or accept they are knowingly local-only.
- **Website repos** ignore only build output (`.svelte-kit`, `build`, `.output`, `.vercel`, `.netlify`, `.wrangler`), deps, and env; keep generated docs and `docs/**` tracked. Put portability-sensitive ignores (`.codex/`, `*.log`) in the repo-local `.gitignore`, not only the user global.
- **Generated reports/exports** are either ignored or placed in a clearly tracked `docs/audits/` (when durable). Never let scratch reports become silently tracked.

---

## 19. Proposed Future Validation Rules (automatable; not implemented here)

A future linter/CI check could enforce:

1. **No public docs loose in `docs/`** — the only `.md` allowed directly in `docs/` is `README.md`; all other public docs must be under `docs/Public/**` (Profile A).
2. **Approved root files only** — fail if a non-approved prose/UPPERCASE `.md` sits at repo root.
3. **No file/folder name collisions** under `docs/`.
4. **Naming/casing** — internal folders match the §4 set; Public subfolders are the §10 TitleCase set; Help/FAQ/Guides/Reference/Troubleshooting filenames are kebab-case; no `NN_` order prefixes in Help.
5. **`.gitkeep` present** in every required-but-empty standard folder.
6. **`docs/README.md` exists** and contains no links to ignored paths.
7. **Markdown-first** — any non-`.md` doc-class file must match the §16 allow-list.
8. **Privacy scan** on `docs/Public/**`, approved root files, and website-rendered trees: regex for local workspace roots, user-home paths, secret patterns, `do not publish`/`confidential`/`internal only`, and `TODO`/`DRAFT`. Fail on a match (with an allow-list for legitimate redaction-prose).
9. **Tracking-policy consistency** — the `.gitignore` doc-policy block is present and does not blanket-ignore a durable `docs/<category>/`.
10. **Source-of-truth** — no identical doc filename tracked in one repo and ignored in another (cross-repo duplicate detector); generated docs not stale vs upstream (content-hash check).
11. **`legal/` + `lineage/` force-tracked** in fork/clean-room repos.

---

## 20. New-Project Bootstrap Tree — App / Library / Tool (Profile A)

```text
README.md
CHANGELOG.md
LICENSE
SECURITY.md
CONTRIBUTING.md
pyproject.toml            # (or Cargo.toml / package.json, as applicable)
.gitattributes
docs/
  README.md               # layered index
  Public/
    Help/
      .gitkeep
    FAQ/
      .gitkeep
    Guides/
      .gitkeep
    Reference/
      .gitkeep
    Troubleshooting/
      .gitkeep
  architecture/
    .gitkeep
  audits/
    .gitkeep
  planning/
    .gitkeep
  research/
    .gitkeep
  implementation/
    .gitkeep
  migrations/
    .gitkeep
  release/
    .gitkeep
  security/
    .gitkeep
  testing/
    .gitkeep
  archive/
    .gitkeep
  # legal/  + lineage/  ONLY for forked / clean-room products (force-tracked)
```

With the canonical `.gitignore` doc-policy block (§18). For forks/clean-room projects, add `docs/legal/.gitkeep` and `docs/lineage/.gitkeep` and force-track them.

---

## 21. New-Project Bootstrap Tree — Website (Profile B)

```text
README.md
package.json
docs/
  content/
    .gitkeep
  design/
    .gitkeep
  deployment/
    .gitkeep
  dns/
    .gitkeep
  operations/
    .gitkeep
  analytics/
    .gitkeep
  planning/
    .gitkeep
  research/
    .gitkeep
  archive/
    .gitkeep
  # Public/  OPTIONAL — only for standalone public docs separate from the rendered site
```

Website rules (§5) apply: site content stays in `src/`; generated/synced docs and their manifest stay where the build resolves them; internal ops/infra docs are tracked but never rendered.

---

## 22. Adoption Checklist (per project)

1. Pick the profile (A or B; add `legal/`+`lineage/` for forks/clean-room).
2. Add the `.gitignore` doc-policy block (§18).
3. Scaffold the bootstrap tree (§20/§21) with `.gitkeep`s.
4. Place/route docs by audience: public → `docs/Public/**` or root file; internal → `docs/<category>/`.
5. Write `docs/README.md` (layered index) + per-folder index stubs.
6. Run the privacy checklist (§17) before anything enters `docs/Public/**` or a public surface.
7. For repos with code/test coupling to doc paths, treat any relocation as a coordinated code+manifest+test change, not a file move.
8. Record genuinely ambiguous placements as open questions for a human, rather than guessing.

---

*This standard is a proposal. It defines target state and conventions; it does not retroactively change any existing repository. The companion workspace documentation structure audit records current-state findings and per-project migration sequences.*
