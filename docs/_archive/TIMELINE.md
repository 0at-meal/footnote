# TIMELINE.md — Chronological Requirements History

> **Purpose:** A commit-anchored, chronological log of every requirement change across the project lifecycle. Built from `git log --follow --format="%H %ad %s" --date=iso` on all doc files, then corroborated against code commits in the same windows. Contradiction rows are explicitly flagged.

---

## Key: Status Column

| Symbol | Meaning |
|---|---|
| 📜 NEW | Document or requirement introduced for the first time |
| 🔄 CHANGED | Prior requirement replaced or modified |
| ➕ EXTENDS | Prior requirement extended or elaborated without contradiction |
| ⚠️ CONTRADICTS | Explicit contradiction of an earlier requirement on the same topic |
| 🔗 CODE-LINKED | Code commit in the same time window—likely related |
| ❓ UNDOCUMENTED | Code changed with no corresponding doc change nearby |

---

## Volume 1 — Initial Scaffold (2026-08-10 to 2026-08-11)

### Commit `8ee5b497` — 2026-08-10 — "initial project scaffold"

**Doc files touched:** `docs/CONSTITUTION.md`, `docs/plan.md`, `docs/spec_feature9.md` (then named `spec.md`)

| Feature Area | Stated Requirement | Status |
|---|---|---|
| Core product | Financial filing intelligence tool. Upload 10-K → extract non-GAAP reconciliation table → LLM classify (label only) → deterministic formula-driven Excel with provenance → review UI → audit trail | 📜 NEW |
| Target metric | **Adjusted EBITDA only** — Phase 1/2 target metric, locked decision | 📜 NEW |
| LLM provider | Groq API, `openai/gpt-oss-120b`. Free tier: 30 RPM / 1,000 RPD / 8,000 TPM / 200,000 TPD | 📜 NEW |
| Extraction scope | Full PDF, all tables | 📜 NEW |
| Excel output | Real formulas, not hardcoded values; provenance per cell | 📜 NEW |
| Feature count | 9 features, 4 phases + Phase 5 (eval harness) | 📜 NEW |
| Tech stack | FastAPI, Docling, PyMuPDF, xlsxwriter, NetworkX + SQLite, React, PDF.js, ReportLab/WeasyPrint, Pytest | 📜 NEW |
| Architecture | Single-user, single-session. LLM = classifier only, never numeric source. formula_engine = pure functions | 📜 NEW |
| Confidence bands | auto-accept ≥ 0.95, human-review 0.65–0.95, manual entry < 0.65 | 📜 NEW |
| Eval harness (F9) | 5–10 manually tied-out 10-Ks; ≥ 90% accuracy; >15% low-confidence = failed extraction | 📜 NEW |

### Commits `1b229751`, `6c198fa6`, `c411c3ee`, ... — 2026-08-11 to 2026-08-12

🔗 CODE-LINKED: Feature 1 implementation (upload zone, server-side PDF validation, job persistence). No doc changes — matching initial spec.

---

## Volume 1 Continued — Phase 1 & 2 Code Build (2026-08-12 to 2026-08-15)

### Commits 2026-08-12 to 2026-08-15 — Feature 2 and Feature 3 code

🔗 CODE-LINKED (no doc changes during this window):
- `b270901e` (2026-08-12): Docling structural parse for extraction (Feature 2, Step 1)
- `b2f2b091` (2026-08-13): Audit remediation — extraction isolation, error handling, architecture
- Multiple extraction sub-commits (assembler, confidence scoring, coordinate normalization, repository persistence, record flagging)
- `e60c64fc`–`30c31be1` (2026-08-14): Groq client, seed taxonomy matching, label attachment, decision log
- `2b3e01b3`–`2f10072c`–`887f230d`–`ed88f476` (2026-08-15): formula_engine, xlsxwriter workbook generation, W3C provenance tagging

📜 CONSTITUTION modified at `6c198fa6` (2026-08-11, Feature 1 Step 2 commit — spec updates committed together with early code).

### Commit `513cb466` — 2026-08-12 — "docs: add Engineering Workbook entry for Feature 1"

**Doc files touched:** `docs/workbook/feature-1-ingestion.md`

| Feature Area | Stated Requirement | Status |
|---|---|---|
| Feature 1 workbook | Detailed step-by-step ticket log for Feature 1 engineering | 📜 NEW |

---

## Volume 1 Continued — Phase 3 & 4 Code Build (2026-08-15 to 2026-08-17)

### Commits 2026-08-15 to 2026-08-17 — Features 5–8 code (no doc changes)

🔗 CODE-LINKED:
- `97c83427` (2026-08-15): Review UI — PDF streaming, bounding-box rendering, confirm/edit/flag actions, lock persistence
- `d5326ce4`–`4f8c2d9b` (2026-08-16): Audit trail source-chain resolution, per-component review badges
- `c6a3f56b`–`b6323d24`–`7298fa8b` (2026-08-17): Drift — label extraction, discrepancy flagging, SQLite graph, history endpoints
- `e13b0202`–`c859ddc8`–`35bc0672`–`91b94fa9` (2026-08-17): Audit report — PDF compile, provenance matrix, downloadable endpoint

❓ UNDOCUMENTED DRIFT: CONSTITUTION.md appears as touched in `c6a3f56b` (drift implementation commit) — evidence that a CONSTITUTION rule was co-committed with feature code rather than as a separate doc-first commit. Specifically: the module boundary for `audit_trail/` (§3.10) was added at this point.

---

## Volume 1 Continued — Phase 5 / Eval Harness (2026-08-17 to 2026-08-18)

### Commits `4684c67c` to `114303fc` — 2026-08-17–18 — "feat(eval): ..."

🔗 CODE-LINKED — Eval harness built (corpus loader, diffing engine, accuracy metrics, CLI runner, report generator, verification).

**No doc change at `spec_feature9.md` during this period** — the eval harness was built during the same time window as spec_feature9.md's git history shows it was modified at `4684c67c`. The spec was being maintained alongside code.

| Feature Area | Requirement (per spec_feature9.md at this point) | Status |
|---|---|---|
| Eval harness scope | 5–10 10-Ks, three-layer diff (extraction / classification / generation), ≥ 90% accuracy, >15% failed extraction | 📜 NEW (matching plan.md) |

---

## Volume 2 — Refinement (2026-08-18 to 2026-08-24)

### Commit `16d28ec4` — 2026-08-19 — "fix(classification): inject seed taxonomy into classifier prompt and add deterministic fallback"

🔗 CODE-LINKED: `debugging.md` created here. Evidence of a classification bug fix (seed taxonomy not injected) creating a new doc to track debugging.

| Feature Area | Stated Requirement | Status |
|---|---|---|
| Classification | Seed taxonomy must be injected into classifier prompt. Deterministic fallback for exact matches. | ➕ EXTENDS (clarification of Feature 3 mechanism) |

### Commit `20d18eee` — 2026-08-24 — "docs: add institutional multi-statement valuation engine spec and constitution amendments"

**Doc files touched:** `docs/CONSTITUTION.md`, `docs/implementation-loop.md`, `docs/updates.md`, `docs/archive/proposed_changes.md` (partially), `docs/glossary.md`

> **This is the most significant single-doc requirement change in the project.**

| Feature Area | Stated Requirement | Prior State | Status |
|---|---|---|---|
| Taxonomy scope | Replace 10-item flat seed with **60–80 item Master Financial Taxonomy (GAAP/IFRS)**, grouped by StatementType. Two-level pipeline: deterministic alias matching first, Groq for genuine unknowns only | Groq-first for all items; 10-item flat seed | ⚠️ CONTRADICTS |
| Formula engine behavior | **All 4 statement trees built simultaneously** for every filing | Single Adjusted EBITDA tree | ⚠️ CONTRADICTS |
| Target metric field | `target_metric` removed from upload form; informational-only on JobRecord | `target_metric` was the primary user-facing selector | ⚠️ CONTRADICTS |
| Excel output | **6 tabs**: Executive_Summary, Income_Statement, EBITDA_Bridge, Cash_Flow, Balance_Sheet, Audit_Trail; new `multi_statement_generator.py` replaces `generator.py` | 2-tab: Source_Inputs + Reconciliation | ⚠️ CONTRADICTS |
| Review UI | `ReviewPage.tsx` completely rewritten with statement-triage tabs | Single flat review list | ⚠️ CONTRADICTS |
| CONSTITUTION amendments | `classification/models.py` may be imported by `review/`, `formula_engine/`, `excel_export/` for Pydantic data models; `mypy --strict` extended to cover `classification/models.py` | classification/ was full isolation boundary | ⚠️ CONTRADICTS (loosening) |
| Implementation loop | `implementation-loop.md` formally added | Referenced but not formally codified | 📜 NEW |

🔗 CODE-LINKED (immediately following, 2026-08-22 to 2026-08-23):
- `98e1ff8e` (2026-08-22): filter extraction to reconciliation tables before classification ← ADR-001 precursor
- `dd22ee0c` (2026-08-22): Excel output to editable 2-column format ← contradicts the 6-tab expansion
- `ec4f3ff2` (2026-08-23): multi-year workbook generator and company endpoints ← from proposed_changes.md Phase A
- `3dd7eb26` (2026-08-23): company data model and filing year grouping ← from proposed_changes.md

> ⚠️ **CONTRADICTION DETECTED (Volume 1 vs. Volume 2):** `updates.md` and `proposed_changes.md` proposed the 6-tab generator becoming the default. `refinement.md` (same era) locked the 2-tab format as the IB-standard. These two document lines are simultaneously in play during 2026-08-22 to 2026-08-24, with conflicting code commits (2-tab fix on 2026-08-22, 6-tab build on 2026-08-23).

---

## Volume 2 Continued — Multi-Year Company Architecture (2026-08-24)

### Commit `60b1a141` — 2026-08-24 — "test(e2e): add multi-statement and multi-year company end-to-end pipeline verification"

🔗 CODE-LINKED: Test coverage for multi-year. No doc change.

---

## Volume 3 — Business Alignment & Refinement Archive (2026-08-26 to 2026-09-01)

### Commits `78aedb64`, `017b406a` — 2026-08-26 — "docs: add end-to-end issues audit (issues.md)" / "docs: add issues implementation charter (issues_charter.md)"

**Doc files touched:** `docs/issues_charter.md` (created)

| Feature Area | Stated Requirement | Status |
|---|---|---|
| 34 open bugs | PDF bbox wrong, review queue overcrowded, audit PDF download failing, isolation violations, fragile review IDs, etc. | 📜 NEW (diagnosis) |
| Step 1 bbox fix | PyMuPDF 1-based index bug; Docling Y-axis inversion | 📜 NEW |
| Step 3 review queue | Auto-lock auto_accepted+matched items; tighten candidate predicate; fix isFlagged frontend predicate | 📜 NEW |
| Step 13 isolation | `audit_report/compiler.py` imports `excel_export/generator.py` — Constitution §3.10 violation | 📜 NEW |

### Commit `3f3a261c` — 2026-08-26 — "chore: move docs to docs/ and remove root duplicates"

Structural reorganization. No requirement changes.

### Commit `54aea539` — 2026-08-29 — "fix: resolve PDF coordinate accuracy and canvas scaling (Step A)"

🔗 CODE-LINKED: `business_alignment.md` touched here (adds last-reviewed date). Coordinate bug partially fixed in code.

### Commit `6008d647` — 2026-09-01 — "docs: rename spec, update plan/glossary/charter/alignment/ADR-001"

**Doc files touched:** `docs/plan.md`, `docs/spec_feature9.md` (rename from spec.md), `docs/business_alignment.md`, `docs/glossary.md`, `docs/issues_charter.md`, `docs/adr/ADR-001-target-metric-scoped-review.md`

| Feature Area | Stated Requirement | Prior State | Status |
|---|---|---|---|
| Phase 5 eval harness | **DEFERRED** — benchmark corpus does not exist. Frozen pending pilot client confirmation | Active in plan.md as Phase 5 | ⚠️ CONTRADICTS (deferral) |
| Refinement Phase 0/1/2 | **COMPLETE** — added status note to plan.md | Not yet closed | 🔄 CHANGED |
| Spec filename | `docs/spec_feature9.md` (was `docs/spec.md`) | `spec.md` | 🔄 CHANGED (rename only) |
| ADR-001 | Implemented — Target-Metric-Scoped Extraction & Review Triage | Draft | 🔄 CHANGED (closure) |

### Commit `763e3656` — 2026-09-01 — "docs: create archive subfolder, add ADRs 002-004, add workbooks 2-8"

**Doc files touched:** `docs/archive/` (created), `docs/archive/refinement.md` (moved), `docs/archive/proposed_changes.md` (archived), ADRs 002–004, workbooks 2–8 added.

| Feature Area | Stated Requirement | Status |
|---|---|---|
| ADR-002: Excel format | Plain values + cross-sheet references (Source_Inputs + Reconciliation, 2-tab). No HYPERLINK wrappers | 📜 NEW (formal record) |
| ADR-003: 6-tab freeze | 6-tab multi_statement_generator.py **frozen as beta**; `generator.py` remains default shipping output | ⚠️ CONTRADICTS `updates.md` Phase A which made 6-tab the default |
| ADR-004: Multi-year | One sheet with fiscal years as columns; user-manually groups filings; user types fiscal year | 📜 NEW (formal record) |
| `refinement.md` | ARCHIVED — all Phase 0/1/2 complete | 🔄 CHANGED (archival) |
| `proposed_changes.md` | ARCHIVED — superseded by `business_alignment.md` §1.2 | 🔄 CHANGED (archival) |

---

## Volume 4 — Workflow Packs & Final Fixes (2026-09-02 to 2026-09-08)

### Commit `88072dad` — 2026-09-02 — "docs: add fixes.md with issue diagnostics and workflow pack architecture"

**Doc files touched:** `docs/fixes.md` (created)

| Feature Area | Stated Requirement | Prior State | Status |
|---|---|---|---|
| Output format | **Revert to 2-tab generator as default** (ADR-003 reconfirmed). 6-tab is "useless bloatware" | ADR-003 decision | ➕ EXTENDS (confirms ADR-003) |
| **Workflow Packs** | NEW CONCEPT: Intent-driven spreading. Three packs: Pack 1 (Non-GAAP Bridge), Pack 2 (Capital Structure / Debt), Pack 3 (Cash Conversion). User selects at upload time | No prior equivalent | 📜 NEW |
| `footnote/` module | Should be wired into pipeline as Pack 2 (capital_structure workflow), not orphaned | Orphaned — API-accessible but not pipeline-triggered | ⚠️ CONTRADICTS (prior state was orphan by accident, not design) |
| `narrative/` module | Deferred — defer from primary pipeline | Existed in codebase without pipeline wiring | 🔄 CHANGED |
| Multi-statement generator | **Demote** from default. Rename `generator.py` to `bridge_generator.py`. New `debt_schedule_generator.py` for Pack 2 | `multi_statement_generator.py` was previous default per `updates.md` | ⚠️ CONTRADICTS (updates.md Phase A) |
| DI pattern | All routers must use `Depends()` — no module-level singletons | `narrative/router.py` had singletons; `drift/router.py` used global state | ⚠️ CONTRADICTS (existing code) |
| Health check | `db_ok = True` in exception block was a bug; must be `False` | Inverted logic in `main.py` line 104 | ⚠️ CONTRADICTS (code bug) |

### Commits `ab1fa470`–`290d62fe`–`24c6d22d` — 2026-09-03 — Workflow pack implementation

🔗 CODE-LINKED (major code changes implementing fixes.md):
- `290d62fe`: Introduce targeted workflow packs architecture
- `ab1fa470`: Surface pipeline failures and review completion actions
- `24c6d22d`: Fix review page inline errors, progress pulse, metric warnings, CORS config
- `7a256125`: Fix db_ok logic inversion on connection failure ← **health check bug fixed**
- `1784de73`: Eliminate route duplication and harmonize DI
- `dcf6639e`: Normalize audit report route paths
- `c2246f25`: Freeze evaluation harness pending pilot client confirmation
- `2378d0a1`: Wire footnote debt schedule into capital structure workflow pack

### Commit `740e17fb` — 2026-09-08 — "docs: move fixes.md and explainer.md into docs directory"

Doc reorganization. `fixes.md` and `explainer.md` moved to `docs/`. No new requirement content.

---

## Chronological Cross-Reference Table (All .md-touching Commits)

| Date | Commit | Files Touched | Key Requirement Change |
|---|---|---|---|
| 2026-08-10 | `8ee5b497` | CONSTITUTION, plan, spec | 📜 Initial Volume 1 baseline |
| 2026-08-11 | `6c198fa6` | CONSTITUTION | ➕ Feature 1 Step 2 — ingestion module boundary rule |
| 2026-08-12 | `513cb466` | workbook/feature-1-ingestion.md | 📜 Engineering workbook Feature 1 |
| 2026-08-12 | `b270901e` | spec_feature9 (via follow) | ➕ Feature 2 docling parse |
| 2026-08-15 | `97c83427` | CONSTITUTION, spec_feature9 | ➕ Feature 5–6 module boundary rules |
| 2026-08-16 | `d5326ce4` | spec_feature9 | ➕ Feature 6 source-chain |
| 2026-08-17 | `c6a3f56b` | CONSTITUTION | ➕ `audit_trail/` module boundary added (§3.10, §3.11) |
| 2026-08-17 | `e13b0202` | spec_feature9 | ➕ Feature 8 audit_report details |
| 2026-08-17 | `4684c67c` | spec_feature9 | ➕ Eval harness F9 expanded |
| 2026-08-19 | `16d28ec4` | debugging.md (new) | 📜 Classification debugging notes |
| 2026-08-24 | `20d18eee` | CONSTITUTION, implementation-loop, updates, proposed_changes, glossary | ⚠️ MAJOR: 6-tab generator, master taxonomy, removed target_metric selector |
| 2026-08-24 | `60b1a141` | (test only) | 🔗 Multi-statement e2e tests |
| 2026-08-26 | `78aedb64` | issues.md (later renamed) | 📜 34-bug audit |
| 2026-08-26 | `017b406a` | issues_charter.md | 📜 Implementation charter for 34 bugs |
| 2026-08-26 | `3f3a261c` | issues_charter.md (move) | Doc restructure |
| 2026-08-29 | `54aea539` | business_alignment.md | 📜 Business alignment diagnosis (Steps A–K) |
| 2026-09-01 | `8369a4b5` | (deletes old files) | Cleanup — no new requirements |
| 2026-09-01 | `6008d647` | plan, spec_feature9, business_alignment, glossary, issues_charter, ADR-001 | 🔄 Phase 5 deferred; Refinement Phases complete; spec renamed |
| 2026-09-01 | `763e3656` | archive/*, ADRs 002-004, workbooks 2-8 | ⚠️ ADR-003: 6-tab frozen; ADR-002: 2-tab format locked |
| 2026-09-02 | `88072dad` | fixes.md (new) | 📜 Workflow Packs introduced; full audit of 34 bugs |
| 2026-09-02 | `098d8e26` | explainer.md (new) | 📜 Architectural onboarding reference |
| 2026-09-03 | `290d62fe` | (code) | 🔗 Workflow packs implementation |
| 2026-09-03 | `7a256125` | (code) | 🔗 Health check db_ok logic fixed |
| 2026-09-03 | `1784de73` | (code) | 🔗 Route deduplication, DI harmonization |
| 2026-09-03 | `2378d0a1` | (code) | 🔗 Wire footnote debt into capital_structure pack |
| 2026-09-08 | `740e17fb` | fixes.md, explainer.md (move) | Doc reorganization |

---

## Major Contradictions Summary

| # | Topic | Earlier Requirement | Later Requirement | Contradiction Commits |
|---|---|---|---|---|
| C1 | Excel output format | 6-tab multi-statement as new default (`updates.md` 2026-08-24) | 2-tab bridge as default; 6-tab frozen as beta (ADR-003, 2026-09-01) | `20d18eee` vs `763e3656` |
| C2 | Target metric selector | `target_metric` removed from upload form (informational only) (`updates.md` 2026-08-24) | `workflow_pack` replaces it with three options; `target_metric` field deprecated but present (`fixes.md` 2026-09-02) | `20d18eee` vs `88072dad` |
| C3 | Formula engine scope | All 4 statement trees simultaneously (`updates.md` 2026-08-24) | Deterministic tree per workflow_pack only; no free-form full model (ADR-003, `fixes.md` 2026-09-02) | `20d18eee` vs `763e3656`/`88072dad` |
| C4 | Eval harness | Active Phase 5 feature, build now (original `plan.md`) | Frozen pending pilot client. Corpus does not exist (`business_alignment.md` §1.1, 2026-08-29) | `8ee5b497` vs `6008d647` |
| C5 | `footnote/` module wiring | Not wired into pipeline (was orphan by 2026-09-02 audit) | Must be wired as workflow_pack=capital_structure (`fixes.md` 2026-09-02, wired at `2378d0a1`) | `88072dad` → `2378d0a1` (resolved) |
| C6 | `narrative/` module | Built as Feature Steps G/H in `business_alignment.md` | Deferred from primary pipeline — not to be wired (`fixes.md` §14.2) | `business_alignment.md` vs `fixes.md` |
