# OPEN_QUESTIONS.md — Resolved Decisions & Technical Baseline (Volume 4)

> **Status:** ✅ Fully Resolved & Baselined (2026-09-09)  
> **Purpose:** Records the architectural rationale, stakeholder trade-offs, and final technical decisions for the 10 ambiguous requirements identified during the Volume 4 SDD Re-baseline. Every item has been evaluated against `CONSTITUTION.md`, practitioner requirements, and codebase constraints.

---

## OQ-1 — `workflow_pack` Default for Legacy Jobs

**Context:** `fixes.md` §7.1 added `workflow_pack` to `JobRecord` with default `"non_gaap_bridge"`. Old persisted jobs in `data/jobs.json` do not have this field. The `job_runner.py` handles this with `getattr(job, "workflow_pack", "non_gaap_bridge") or "non_gaap_bridge"`.

### Decision: Option 1 & 3 Hybrid — Explicit Default to `non_gaap_bridge` with Safe State Preservation
- **Resolution:**
  1. All historical jobs prior to 2026-09-03 were created under the original product scope: extracting Non-GAAP reconciliation tables for Adjusted EBITDA. They never targeted Note 8 debt schedules or multi-statement models. Defaulting missing fields to `"non_gaap_bridge"` is both historically and semantically accurate.
  2. Historical job execution artifacts (`data/results/*_provenance.json`, model workbooks, classified records) are preserved as-is on disk without forcing automated re-extraction or re-classification on startup.
  3. If an analyst or test suite explicitly triggers a re-run on a legacy job, it will execute cleanly through `bridge_generator.py` under the current Master Financial Taxonomy.
- **Actionable Rule:** Maintain `getattr(job, "workflow_pack", "non_gaap_bridge") or "non_gaap_bridge"` in `ingestion/models.py` and `job_runner.py`. No database migration script is necessary.

---

## OQ-2 — Role of `target_metric` Field in the New Architecture

**Context:** `updates.md` (2026-08-24) removed `target_metric` from the upload form, making it informational only. `fixes.md` (2026-09-02) replaced it with `workflow_pack`. However, `plan.md` still references Adjusted EBITDA as a locked target metric, and `bridge_generator.py` accepts a `target_metric` parameter.

### Decision: Option 2 & 3 Hybrid — Workflow Pack Derived Default with Optional Advanced Override
- **Resolution:**
  1. `workflow_pack` is the primary top-level user selection (intent-driven spreading).
  2. `target_metric` is retained on `JobRecord` for full backward compatibility, but is **automatically derived** based on the selected pack:
     - When `workflow_pack == "non_gaap_bridge"`: default `target_metric = "Adjusted EBITDA"`.
     - When `workflow_pack == "capital_structure"`: default `target_metric = "Capital Structure"` (informational).
     - When `workflow_pack == "cash_conversion"`: default `target_metric = "Free Cash Flow"`.
  3. In the frontend `UploadZone.tsx`, `target_metric` is removed from the primary form fields and placed inside an expandable "Advanced Settings" accordion. Standard analysts only pick the workflow pack; power users can override the specific bridge metric (e.g. to "Adjusted EBIT" or "Free Cash Flow").
- **Actionable Rule:** Do not delete `target_metric` from `JobRecord`. In `ingestion/router.py`, default `target_metric` based on `workflow_pack` if omitted in the upload payload.

---

## OQ-3 — Semantic Drift Detection vs. String Exact-Match

**Context:** `business_alignment.md` §2.3 states that exact string equality on `normalized_label` cries wolf on cosmetic renamings (e.g., "purchase accounting amortization" vs. "acquisition-related intangible amortization"), causing alert fatigue.

### Decision: Option 3 — Deterministic Exact-Match Detection + User Feedback Loop
- **Resolution:**
  1. Under `CONSTITUTION.md` §1.4 and §6.7, formula and evaluation engines must remain strictly deterministic. Introducing an embedding similarity threshold or LLM call into the automated drift comparison introduces non-determinism, network overhead, and potential regression.
  2. Automated cross-year comparison continues to use exact string matching on `normalized_label` as the trigger.
  3. False-positive cosmetic relabelings are resolved through human-in-the-loop confirmation using the existing endpoint:
     `POST /drift/jobs/{job_id}/mark-relabeled`
  4. When an analyst marks an item as a confirmed cosmetic renaming, the drift graph in `drift.db` links the two terms with a `cosmetic_relabel` relationship. Subsequent drift runs recognize the equivalence and suppress redundant warnings.
- **Actionable Rule:** Retain exact-string graph comparison as the automated trigger. Use the `mark-relabeled` endpoint to store confirmed equivalences in SQLite. Defer vector/embedding semantic search to post-pilot.

---

## OQ-4 — `narrative/` Module Re-evaluation Gate

**Context:** `fixes.md` §14.2 defers the `narrative/` module (MD&A diffing, risk factor redlines) from the primary pipeline until the numeric spreading packs are "bulletproof."

### Decision: Option 2 — Strict Numeric-First Milestone Gate
- **Resolution:**
  1. The primary economic value of Footnote is **reconciliation spreading, debt tranche extraction, and formula-backed provenance in Excel**. Generic text diffing is readily available in existing word processors; numeric cell tracing is not.
  2. The gate condition to re-evaluate `narrative/` is:
     - **Milestone A:** All P0/P1 remediation tickets (PyMuPDF bbox indexing, `model_compilation_service`, review queue candidate gating, DI consistency) are fully resolved and passing CI.
     - **Milestone B:** The pipeline extracts and compiles clean 2-tab workbooks across at least 3 diverse 10-K filings with zero bounding-box highlight misalignments.
     - **Milestone C:** An explicit Product ADR is drafted defining how narrative diffs are displayed in the frontend without slowing down the PDF rendering canvas.
  3. Until Milestones A–C are signed off, `narrative/` routes remain isolated and will NOT be invoked by `job_runner.py`.
- **Actionable Rule:** Keep `narrative/` code in repository but disconnected from `job_runner.py`.

---

## OQ-5 — EDGAR Direct Integration Priority

**Context:** `business_alignment.md` §3.2 identifies EDGAR integration as "P1 — Pilot Prerequisite" (Step D), whereas `plan.md` lists it as "Future."

### Decision: Option 2 — Post-Pilot / Secondary Ingestion Source
- **Resolution:**
  1. In investment banking and private equity workflows, analysts regularly work with local PDFs, data-room documents, foreign filings, and confidential merger prospectuses. Manual drag-and-drop upload is a completely standard and acceptable interaction pattern.
  2. Integrating EDGAR (EFTS search, CIK lookups, 10-K HTML/XBRL handling, SEC rate limiting) adds 2–3 weeks of development and ongoing maintenance. If the core extraction or formula generation fails on a PDF, EDGAR ingestion is useless.
  3. The pilot will proceed with drag-and-drop PDF upload. EDGAR direct integration is formally sequenced as **Phase 6 (Post-Pilot Expansion)**.
- **Actionable Rule:** Do not block pilot deployment or remediation on EDGAR integration.

---

## OQ-6 — `cash_conversion` Workflow Pack Specification

**Context:** `fixes.md` §7 defined three workflow packs (`non_gaap_bridge`, `capital_structure`, `cash_conversion`), but `cash_conversion` is not yet specified. Currently, `job_runner.py` falls back to `multi_statement_generator.py` for unimplemented packs, violating ADR-003.

### Decision: Freeze as "Under Specification"; Do Not Expose in Active UI; Return Skip Reason
- **Resolution:**
  1. In `UploadZone.tsx`, present only the two fully implemented and tested workflow packs:
     - **Earnings Quality / Non-GAAP Bridge** (`non_gaap_bridge`)
     - **Capital Structure & Debt Sizing** (`capital_structure`)
     - Display `cash_conversion` as disabled with a badge: *"Coming in Phase 5"*.
  2. In `job_runner.py`, remove the fallback call to `generate_multi_statement_workbook()`. If a job has `workflow_pack == "cash_conversion"`, set `model_skip_reason = "Workflow pack 'cash_conversion' is under specification. Please select non_gaap_bridge or capital_structure."`
  3. Formal specification of `cash_conversion` (Operating Cash Flow reconciliation, CapEx, Working Capital) will be scheduled as an independent Phase after Remediation.
- **Actionable Rule:** Prevent fallback to `multi_statement_generator.py` in `job_runner.py`. Guard in UI.

---

## OQ-7 — Excel Numeric Format: 0 vs. 2 Decimal Places

**Context:** `fixes.md` §8.1 noted that `_parse_numeric_value()` diverges across generators (2 decimals in `generator.py` vs. 0 decimals in `multi_statement_generator.py`).

### Decision: Option 3 — Context-Aware Standard with 0-Decimal Bridge Default
- **Resolution:**
  1. Institutional investment banking convention:
     - Dollar values in corporate EBITDA bridges and Debt Schedules (which are stated in thousands or millions) must be formatted with **0 decimal places, thousands commas, and negative numbers in parentheses**:
       `"$#,##0;($#,##0);\"-\""`
     - Per-share metrics (EPS, adjusted EPS) and unit ratios require **2 decimal places**:
       `"$#,##0.00;($#,##0.00);\"-\""`
     - Percentage margins require **1 decimal place**:
       `"0.0%"`
  2. Deduplicate format string helpers in `backend/app/excel_export/utils.py`:
     ```python
     def get_currency_format(is_per_share: bool = False) -> str:
         if is_per_share:
             return '$#,##0.00;($#,##0.00);"-";@'
         return '$#,##0;($#,##0);"-";@'
     ```
  3. `bridge_generator.py` and `debt_schedule_generator.py` will use 0 decimals for statement aggregates and line items by default.
- **Actionable Rule:** Standardize on 0 decimals for financial bridge totals. Centralize format definitions in `excel_export/utils.py`.

---

## OQ-8 — `multi_statement_generator.py` Long-Term Fate

**Context:** ADR-003 froze the 6-tab multi-statement generator as "beta." `fixes.md` called it unneeded bloatware vs FactSet. However, it represents ~1,260 lines of code.

### Decision: Option 3 — Decouple from Automated Pipeline; Retain as Explicit Company-Level Export
- **Resolution:**
  1. Comply strictly with **ADR-003**: The 6-tab generator must NEVER run as the default output or as an automated fallback for incomplete jobs in `job_runner.py`.
  2. Retain the file `backend/app/excel_export/multi_statement_generator.py` in the repository without deleting it.
  3. It remains accessible solely via the explicit company endpoint `POST /companies/{company_id}/multi-year-model` when all statement inputs are present.
  4. If after 6 months of client pilot feedback no enterprise user requests 3-statement models, archive the generator to `docs/_archive/` and remove from production imports.
- **Actionable Rule:** Eliminate `generate_multi_statement_workbook` from `job_runner.py`. Maintain guard rails per ADR-003.

---

## OQ-9 — Health Check SQLite Logic Verification

**Context:** `fixes.md` §11 identified and commit `7a256125` fixed a `db_ok` logic inversion. The question arose whether the outer `OSError` block could still return `True` incorrectly.

### Decision: Verified and Closed — Health Check Logic is Correct
- **Resolution:**
  1. Direct code inspection of `backend/app/main.py` (lines 96–124) confirms:
     - `data_writable` is initialized to `False` and only set to `True` if `test_file.write_text()` succeeds.
     - `db_ok` is independently evaluated in a separate `try/except (sqlite3.Error, OSError)` block connecting to `drift.db` and executing `SELECT 1`.
     - An error during file writing does not affect `db_ok`, and a failure in SQLite sets `db_ok = False`.
     - The endpoint returns `status="ok"` only if `data_writable and db_ok` is `True`.
  2. The health check is operational, properly isolated, and meets all criteria for Step 11 / Ticket 11.1.
- **Actionable Rule:** No further modifications required for `/health`.

---

## OQ-10 — `fixes_implementation.md` (Root Level) — Archive or Integrate?

**Context:** A 44KB file `fixes_implementation.md` exists at repo root, tracking 14 steps and 44 atomic tickets from the Sep 3 sprint.

### Decision: Option 2 — Archive to `docs/_archive/fixes_implementation.md` and Link in `PROVENANCE.md`
- **Resolution:**
  1. The file contains valuable atomic ticket definitions and verification acceptance criteria for the fixes implemented on 2026-09-03.
  2. Leaving implementation trackers in the project root clutters repository navigation and violates SDD document hygiene.
  3. The file will be moved to `docs/_archive/fixes_implementation.md`.
  4. Its provenance and relationship to `docs/fixes.md` will be documented in `docs/_archive/PROVENANCE.md`.
- **Actionable Rule:** Archive `fixes_implementation.md` into `docs/_archive/`. Update `PROVENANCE.md`.

---

## Summary of Baselined Decisions

| OQ ID | Subject | Final Decision | Architectural Impact |
|---|---|---|---|
| **OQ-1** | Legacy Jobs Workflow Pack | Default to `non_gaap_bridge`; preserve existing outputs | Zero-risk backwards compatibility |
| **OQ-2** | Role of `target_metric` | Derived from `workflow_pack`; advanced override | Clean UI upload, full backend flexibility |
| **OQ-3** | Semantic Drift Detection | Exact match + `mark-relabeled` feedback loop | Determinism preserved (Constitution §1.4) |
| **OQ-4** | `narrative/` Re-evaluation | Strict gate: numeric pipeline verified on 3 10-Ks | Protects engineering focus on core spreading |
| **OQ-5** | EDGAR Integration Priority | Post-pilot (Phase 6) | Prevents pilot delay on secondary ingestion |
| **OQ-6** | `cash_conversion` Pack | Frozen; remove fallback to 6-tab; UI disabled | ADR-003 compliance; no partial execution |
| **OQ-7** | Excel Number Formatting | 0 decimals for bridges (`$#,##0`), 2 for EPS | Strict compliance with IB modeling standards |
| **OQ-8** | 6-Tab Generator Fate | Decouple from pipeline; retain as company export | Closes critical ADR-003 violation |
| **OQ-9** | Health Check Logic | Verified as fully correct in `main.py` | Step 11 / Ticket 11.1 signed off |
| **OQ-10** | `fixes_implementation.md` | Archive to `docs/_archive/` | Repository root hygiene restored |
