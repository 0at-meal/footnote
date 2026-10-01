# Footnote — Diagnostic Fixes Report

> **Produced:** 2026-09-02
> **Source:** Complete recursive audit of all source files, schemas, routers, docs, ADRs, issues charter, business alignment doc, and git history
> **Status of open issues:** All 34 bugs in `docs/issues_charter.md` are unresolved (all checkboxes unchecked)

---

## Part A — What the Project Was Meant to Be

Footnote was conceived as a **narrow, deeply precise tool** for a specific workflow:

> *A junior investment banker uploads a 10-K PDF. The system automatically finds the non-GAAP reconciliation table (Adjusted EBITDA bridge), extracts each line item with exact page and bounding-box coordinates, sends only the text labels to an LLM strictly for classification (never for computation), builds a fully formula-driven provenance-tagged Excel workbook, and provides a review UI for the analyst to confirm or flag items. Any generated cell can be traced back to its exact PDF location in under 10 seconds.*

The core architectural bets:
1. **LLM as classifier only** — the "explainability barrier" between what the AI touches (labels) and what deterministic code computes (numbers)
2. **Frozen 5-field schema** (`value, label, page, bbox, source_file`) — the atomic unit that flows unchanged through the entire pipeline
3. **Deterministic formula engine** — pure functions, no I/O, identical input -> identical output
4. **Human-in-the-loop** — the review UI is the trust anchor; confirmed items are locked

The original deliverable was 8 features across 4 phases, culminating in a downloadable Excel model and compliance PDF for a single company's Adjusted EBITDA reconciliation.

---

## Part B — What Went Wrong and Why

### B.1 Scope Creep Without Institutional Validation

The spec committed to 8 features. The codebase now contains:
- **11 distinct backend modules** (`ingestion`, `extraction`, `classification`, `formula_engine`, `excel_export`, `review`, `audit_trail`, `drift`, `audit_report`, `footnote`, `narrative`)
- `footnote/` and `narrative/` are entirely new feature domains (debt schedule extraction, lease waterfalls, customer concentration, MD&A diffing, risk factor redlines) added as "Step E/F/G/H/I" in `business_alignment.md` without a client commitment
- These two modules are **not wired into the automated pipeline** — they are orphaned features accessible via API but never triggered by the main job runner

**Why this happened:** The `business_alignment.md` document (produced 2026-08-29) correctly identified that practitioners need footnote-level data, not just the non-GAAP bridge. Steps E–K were added to the roadmap. However, the code for these features was partially built while the core pipeline still had P0 demo-blocking bugs (bbox coordinates wrong, review queue broken).

### B.2 Three Parallel Excel Generators — Architectural Confusion

The spec promised a 2-tab banker-editable workbook (Source_Inputs + Reconciliation). Three generators now exist:
- `generator.py` — the original 2-tab generator, **marked DEPRECATED** in its own docstring
- `multi_year_generator.py` — multi-year single-sheet, **marked DEPRECATED** in its own docstring
- `multi_statement_generator.py` — 6-tab comprehensive model, **the current default in `job_runner.py`**

Both "deprecated" generators are still in active use in production code paths:
- `generator.py` is imported by `audit_report/compiler.py` (isolation violation, see B.4)
- `multi_year_generator.py` is called by `company_router.py` `POST /companies/{id}/multi-year-model`

**Why this happened:** ADR-002 locked the 2-tab format. Then `business_alignment.md` (correctly) noted that institutional buyers want multi-year column layouts. A 6-tab generator was built without first deprecating or replacing the prior generators. The 6-tab generator became the default pipeline output even though `business_alignment.md` §1.2 explicitly recommends **reverting to the 2-tab generator as the default**.

### B.3 Twenty Open Bug Steps, Thirty-Four Tickets — None Done

The `issues_charter.md` file documents 20 steps and 34 tickets. Every single checkbox is unchecked. The most critical:

**P0 demo-blockers (bbox coordinates systematically wrong):**
- PyMuPDF fallback assigns the **entire table bbox** to every extracted cell due to a 1-based loop index (`row_idx=1, col_idx=1`) — Step 1, Ticket 1.1
- Docling uses bottom-left origin; PyMuPDF canvas uses top-left origin -> vertical coordinate inversion -> all highlights appear in the wrong vertical position — Step 1, Ticket 1.2
- ReviewPage renders at scale 1.5; AuditTrailView renders at scale 1.3 -> same item appears at different pixel positions in each view — Step 15
- Canvas size read uses `clientWidth` (includes CSS padding) rather than `getBoundingClientRect()` -> bbox pixel placement off by padding width — Step 16

**P0 UX: review queue always overcrowded:**
- `is_target_metric_candidate_item()` in `normalizer.py` uses broad keyword matching on raw labels regardless of whether the item comes from a reconciliation table — items from P&L, balance sheet, footnote tables all marked as candidates — Step 3, Ticket 3.2
- Auto-accepted taxonomy-matched items should be pre-locked (not shown in flagged tab) but are currently shown — Step 3, Ticket 3.1
- Frontend `isFlagged` predicate uses `confidence_score < 0.95` instead of status-based filtering — Step 3, Ticket 3.4

**Structural bugs:**
- Review item IDs are `{job_id}_{idx}` (sequential loop index) — if classification re-runs or record order changes, audit trail cross-references silently break — Step 12
- `audit_report/compiler.py` imports `generate_workbook` from `excel_export/generator.py` — direct Constitution §3.10 isolation violation — Step 13
- `drift/router.py` has a duplicate route: `POST /{job_id}/mark-relabeled` AND `POST /jobs/{job_id}/mark-relabeled` both registered

### B.4 Confirmed Constitution Violations

| Violation | Location | Constitution Rule | Severity |
|---|---|---|---|
| `audit_report/compiler.py` imports from `excel_export/generator.py` | compiler.py lines 31-32 | §3.10: audit_report must not import from classification or formula_engine | **Active** |
| `audit_report/compiler.py` imports from `formula_engine/reader.py` and `formula_engine/tree.py` | compiler.py lines 35-39 | §3.10: audit_report boundary isolation | **Active** |
| `narrative/router.py` instantiates repositories as module-level singletons | router.py lines 30-31 | Bypasses FastAPI `Depends()` DI system used by all other routers | **Active** |
| `footnote/router.py` same singleton pattern | router.py lines 30-33 | Same | **Active** |

### B.5 Duplicated Code

`_parse_numeric_value()` is copy-pasted identically into three files:
- `excel_export/generator.py` (deprecated label)
- `excel_export/multi_year_generator.py` (deprecated label)
- `excel_export/multi_statement_generator.py` (active)

With a subtle format divergence: `generator.py` uses `'$#,##0.00;($#,##0.00);"-"'` (2 decimals); `multi_statement_generator.py` uses `'$#,##0;($#,##0);"-"'` (no decimals).

### B.6 The 6-Tab Generator Is Scope Inflation

`business_alignment.md` §1.2 explicitly states:
> *"The Income Statement, Cash Flow Statement, and Balance Sheet tabs reconstruct data that Bloomberg and FactSet already serve in cleaner form... The multi-statement generator silently expanded scope without institutional buyer confirmation."*

The 6-tab generator is:
- The **default output** in `job_runner.py`
- Tightly coupled to `ComprehensiveModelTree` requiring all 5 statement types to be populated
- A frequent source of partial-tree generation errors when only a reconciliation table is found
- Never confirmed as the correct output format by any client

### B.7 Eval Harness: Premature Infrastructure

The `eval/` directory contains a sophisticated benchmark harness (~80KB of code). Per `plan.md` §4:
> *"The benchmark corpus does not exist... Freeze the eval harness."*

The harness exists but has no corpus. It cannot run against real data.

### B.8 The Fallacy of the Two Extremes: Why "Full Generative Models" Fail and "Targeted Workflow Packs" Win

A critical strategic question emerged:
> *If the 6-tab model is useless bloatware, but the original 2-tab model is naive and too simple, why not just ask the analyst what type of financial model they are building and extract all relevant items from the PDF?*

Here is the direct analysis of why that naive approach fails and what the correct architecture is:

1. **Bankers do NOT want an AI to build their financial model:**
   Investment banks, private equity shops, and hedge funds have **rigid internal Excel models** with proprietary formatting, dynamic macros, custom debt schedules, and sensitivity tables. They will **never** replace their firm’s master LBO, DCF, or M&A merger model with an AI-generated workbook.
2. **What analysts actually suffer from is "Spreading" (Footnote Hunting):**
   Junior analysts spend hours manually control-F digging through 180 pages of 10-K disclosures to transcribe data into their existing firm models:
   - Locating the Debt footnote (Note 8) to parse loan tranches, floating spreads (SOFR + bps), and the 5-year maturity schedule.
   - Locating the ASC 842 Lease footnote (Note 12) to calculate operating vs. finance lease debt equivalents.
   - Reconciling Non-GAAP adjustments (litigation settlements, restructuring, stock-based compensation).
3. **Unconstrained extraction across a 10-K causes accuracy to implode:**
   A 10-K is an adversarial legal document. If you ask the pipeline to "find everything for an LBO model", it must simultaneously parse unstructured text, pricing grids, maturity tables, and cash flow items across 180 pages. If a single debt tranche is missed or has a wrong bounding box, **the analyst throws the entire output away**.
4. **Dynamic model generation breaks determinism:**
   Footnote’s core architectural promise (Constitution §3.1) is that mathematical calculations and formulas are pure, deterministic functions (zero LLM hallucination). If model structures are generated dynamically on the fly, you lose deterministic DAG formula trees.

**The Solution: Intent-Driven "Workflow Packs" (Targeted Spreading):**
Instead of free-form model generation, the user selects their spreading task upfront at upload time:
- **Pack 1: Non-GAAP & Earnings Quality** (Adjusted EBITDA, Free Cash Flow bridge, one-offs) -> 2-tab clean model.
- **Pack 2: Capital Structure & Debt Sizing** (Note 8 debt tranches, maturity waterfalls, ASC 842 leases) -> 2-tab schedule that **finally puts the orphaned `footnote/` module to work!**
- **Pack 3: Valuation & Cash Conversion Inputs** (Unlevered FCF, CapEx, Working Capital changes).

---

## Part C — Nested Numbered List of All Changes to Be Made

### 1. P0 — Fix Core Correctness Bugs (Demo Blockers)

1. Fix PyMuPDF cell bbox indexing (`extraction/docling_parser.py`, `_parse_pdf_with_pymupdf()`)
   1. Change loop from 1-based (`row_idx=1, col_idx=1`) to 0-based (`row_idx=0, col_idx=0`)
   2. Fix `flat_idx` formula to `(row_idx) * len(row) + col_idx`
   3. Verify `table.cells` is a flat list before indexing
   - *Issues Charter Step 1, Ticket 1.1*

2. Fix Y-axis coordinate inversion for Docling bboxes (`extraction/coordinate_normalizer.py`, `normalize_item_bbox()`)
   1. Apply inversion: `y0_screen = 1000.0 - y1_norm`, `y1_screen = 1000.0 - y0_norm` for Docling items only
   2. Condition on `item.parser_used == "docling"`
   3. Add module-level docstring explaining coordinate spaces
   - *Issues Charter Step 1, Ticket 1.2*

3. Add `parser_used` field to `DoclingItem` and propagate (`extraction/models.py`, `docling_parser.py`)
   1. Add `parser_used: Literal["docling", "pymupdf"] = "docling"` to `DoclingItem`
   2. Set `parser_used = "pymupdf"` on all items created in `_parse_pdf_with_pymupdf()`
   - *Issues Charter Step 1, Ticket 1.3*

4. Write unit tests for both bbox paths (`tests/extraction/test_coordinate_normalizer.py`)
   1. Docling path: y0=50 on 792pt page -> assert y0_norm approx 937
   2. PyMuPDF path: y0=50 on 792pt page -> assert y0_norm approx 63
   3. Per-cell flat_idx: 3x4 table -> each cell gets correct bbox
   - *Issues Charter Step 1, Ticket 1.4*

5. Standardize PDF render scale (`frontend/src/lib/pdf/renderer.ts`, `AuditTrailView.tsx`)
   1. Add `export const PDF_RENDER_SCALE = 1.5` to `renderer.ts`
   2. Import and use in both `ReviewPage.tsx` and `AuditTrailView.tsx`
   - *Issues Charter Step 15, Ticket 15.1*

6. Fix canvas size read (`ReviewPage.tsx`, `AuditTrailView.tsx`)
   1. Replace `clientWidth/clientHeight` with `getBoundingClientRect().width/height`
   2. Apply to both views
   - *Issues Charter Step 16, Ticket 16.1*

### 2. P0 — Fix Review Queue (UX Blocker)

1. Auto-lock `auto_accepted + taxonomy matched` items (`review/repository.py`, `_from_classified_records()`)
   1. If `confidence_band == auto_accepted AND taxonomy_status == matched`: set `status = locked` not `auto_accepted`
   2. These items still appear in the full list but never in the flagged tab
   - *Issues Charter Step 3, Ticket 3.1*

2. Tighten `is_target_metric_candidate_item()` (`classification/normalizer.py`)
   1. Gate the predicate on `is_reconciliation_candidate == True` as the primary signal
   2. Remove the broad keyword fallback that marks all items with reconciliation-sounding labels as candidates regardless of source table
   3. Items from P&L, balance sheet, and footnote tables must NOT be flagged as candidates when an explicit reconciliation table exists
   - *Issues Charter Step 3, Ticket 3.2*

3. Fix `isFlagged` frontend predicate (`ReviewPage.tsx`)
   1. Replace `confidence_score < 0.95` with status-based predicate: `['needs_review', 'manual_required', 'extraction_error', 'pending_taxonomy_confirmation', 'flagged'].includes(item.status)`
   2. Items with `status === 'auto_accepted'` or `status === 'locked'` must never appear in the Flagged tab
   - *Issues Charter Step 3, Ticket 3.4*

4. Improve confidence scoring for reconciliation items (`extraction/confidence.py`)
   1. Add Signal: `+0.05` if value is a well-formed numeric (parseable float after stripping `$`, `,`, `(`, `)`, `%`)
   2. Add table-consistency second pass in `score_records()`: group by `table_name`; if >=70% of items in a table scored >=0.80, boost remaining items in that table by `+0.10` (clamped to 1.0)
   - *Issues Charter Step 6, Tickets 6.1-6.2*

### 3. P0 — Fix Isolation Violation

1. Extract on-the-fly model compilation into `model_compilation_service.py` (new file at `app/` root level)
   1. Create `backend/app/model_compilation_service.py` with a pure function `try_compile_model_on_the_fly()`
   2. Move the on-the-fly compilation block (lines 92-117) from `audit_report/compiler.py` into this function
   3. This file may import from both `excel_export/` and `formula_engine/` — allowed at app-root tier
   - *Issues Charter Step 13, Ticket 13.1*

2. Remove `excel_export` and `formula_engine` imports from `audit_report/compiler.py`
   1. Replace `from app.excel_export.generator import generate_workbook` and `from app.excel_export.repository import ModelRepository` with a call to `try_compile_model_on_the_fly()` imported from `app.model_compilation_service`
   2. Remove `from app.formula_engine.reader import ...` and `from app.formula_engine.tree import ...`
   3. Verify: `ruff check backend/app/audit_report/` reports zero import isolation violations
   - *Issues Charter Step 13, Ticket 13.2*

### 4. P1 — Fix Fragile Review Item IDs

1. Replace sequential IDs with content-based hash (`review/repository.py`)
   1. Replace `id=f"{job_id}_{idx}"` with a deterministic hash of `(job_id, source_file, page, bbox)`:
      ```python
      def _make_review_id(job_id: str, source_file: str, page: int, bbox: dict) -> str:
          key = f"{job_id}:{source_file}:{page}:{bbox.get('x0',0):.0f}:{bbox.get('y0',0):.0f}"
          return hashlib.sha256(key.encode()).hexdigest()[:16]
      ```
   2. Apply to both `_from_classified_records()` and `_from_scored_records()`
   - *Issues Charter Step 12, Ticket 12.1*

2. Update audit trail resolver to use content-based ID matching (`audit_trail/resolver.py`)
   1. Build `review_item_by_hash: dict[str, ReviewItem]` keyed by the same content-hash formula
   2. Extract `source_file`, `page`, and `bbox` from the leaf record's target selector and compute the hash to find the matching review item
   - *Issues Charter Step 12, Ticket 12.2*

### 5. P1 — Fix Audit PDF Download

1. Gate the Export Audit PDF button on `model_ready` (`AuditTrailView.tsx`)
   1. Accept `modelReady: boolean` prop (already passed from `App.tsx` line 209)
   2. When `!modelReady`, render a disabled button with tooltip: "Generate a model first: go to Review and click 'Approve & Generate'"
   3. When `modelReady`, render the active `<a download>` link
   - *Issues Charter Step 2, Ticket 2.1*

2. Enrich audit trail empty state with step-by-step guidance (`AuditTrailView.tsx`)
   1. Replace terse "Model not yet generated" card with a numbered checklist
   2. Include a prominent "Go to Review Tab" button calling `onReview(jobId)`
   - *Issues Charter Step 2, Ticket 2.2; Step 4, Ticket 4.1*

3. Add Refresh button to audit trail (`AuditTrailView.tsx`)
   1. Extract `fetchMetadataAndInitialChain` into a callable `loadProvenance()` function
   2. Add a "Refresh" button in the header that calls `loadProvenance()`
   - *Issues Charter Step 4, Ticket 4.2*

### 6. P1 — Surface Pipeline Failures

1. Populate `model_skip_reason` in job_runner and verify persistence (`job_runner.py`, `ingestion/repository.py`)
   1. When `len(formula_inputs.nodes) == 0`: set `model_skip_reason = formula_inputs.error_message or "No auto-accepted or confirmed records available"`
   2. When `comp_tree.is_valid == False`: set `model_skip_reason = comp_tree.error_message`
   3. Verify the field is actually written to `data/jobs.json` and returned by `GET /upload/jobs`
   - *Issues Charter Step 11, Ticket 11.1*

2. Surface `model_skip_reason` in JobList UI (`JobList.tsx`, `types/job.ts`)
   1. Add `model_skip_reason?: string | null` to the TypeScript `JobRecord` type (already present in `job.ts` — verify it's populated)
   2. In `StatusBadge`, when `status === 'done' && !model_ready`, render an info icon with tooltip showing the skip reason
   - *Issues Charter Step 11, Ticket 11.2*

3. Add "Generate Model" button to empty Flagged tab (`ReviewPage.tsx`)
   1. When `activeTab === 'flagged'` and the flagged items list is empty, render an empty state with the "Approve & Generate Complete Financial Model" button calling `handleApproveBridgeAndGenerateModel`
   - *Issues Charter Step 9, Ticket 9.1*

### 7. P2 — Introduce Targeted Workflow Packs (Intent-Driven Spreading Architecture)

1. Add `workflow_pack` to Ingestion Schemas (`ingestion/models.py`, `types/job.ts`)
   1. Extend `JobRecord` with:
      `workflow_pack: Literal["non_gaap_bridge", "capital_structure", "cash_conversion"] = "non_gaap_bridge"`
   2. Update `POST /upload/jobs` and `POST /upload/jobs/async` to accept optional `workflow_pack` parameter in form data.

2. Implement Bounded Extraction Routing in Pipeline (`job_runner.py`, `docling_parser.py`)
   1. If `workflow_pack == "non_gaap_bridge"`: filter parser to non-GAAP reconciliation tables (Item 7 MD&A).
   2. If `workflow_pack == "capital_structure"`: route directly to `footnote/extractor.py` parsing Note disclosures matching Debt, Borrowings, Credit Facilities, and Leases.
   3. If `workflow_pack == "cash_conversion"`: filter parser to the Statement of Cash Flows and related CapEx / Working Capital notes.
   4. Bounded extraction prevents unconstrained 180-page scans, keeps confidence high, and eliminates review queue overcrowding.

3. Restructure Generators by Workflow Pack (`excel_export/`)
   1. Demote `multi_statement_generator.py` (6-tab model) out of the automated pipeline. Label it as legacy/company-level full-model only.
   2. Rename / update `generator.py` as `bridge_generator.py` for `workflow_pack == "non_gaap_bridge"` (Source_Inputs + Reconciliation tabs with deterministic formulas).
   3. Wire `footnote/` models (`DebtSchedule`, `LeaseSchedule`) to a dedicated `debt_schedule_generator.py` producing a clean 2-tab Capital Structure workbook (Debt Tranches & Spreads + Lease Waterfall).
   4. Both generators follow strict IB formatting: blue hardcoded inputs, green cross-sheet references, black formulas, and cell comments containing exact W3C provenance metadata.

4. Add Workflow Pack Selector to Ingestion UI (`UploadZone.tsx`, `App.tsx`)
   1. In `UploadZone.tsx`, add a segmented control or card selector allowing the analyst to pick their task:
      - **Earnings Quality / Non-GAAP Bridge** (EBITDA, Free Cash Flow, adjustments)
      - **Capital Structure & Debt Sizing** (Debt tranches, maturities, ASC 842 leases)
      - **Cash Flow & Valuation Inputs** (Unlevered FCF, CapEx, Working Capital)
   2. Pass selected `workflow_pack` to `POST /upload/jobs`.

### 8. P2 — Extract and De-duplicate Shared Code

1. Extract `_parse_numeric_value()` into `excel_export/utils.py`
   1. The function exists identically in all three generators with subtle format divergence (0 vs 2 decimal places) — pick one canonical format
   2. Import from `excel_export.utils` in all three generators

2. Extract `_col_to_letter()` and `_to_cell_coord()` into `excel_export/utils.py`
   1. These utility functions are duplicated across generators

3. Document `is_well_formed_numeric_value()` relationship note
   1. `extraction/confidence.py` has `is_well_formed_numeric_value()` which is semantically equivalent to `_parse_numeric_value()` in the generators — they should not be merged (different layers, different isolation rules) but implementations should be consistent

### 9. P2 — Fix Remaining UX Issues

1. Replace `alert()` with inline error state (`ReviewPage.tsx`)
   1. Replace `alert(err instanceof Error ? err.message : "Confirmation failed")` (line 333) with `setEditError(...)`
   2. The `editError` state is already rendered as an inline error element below action buttons
   - *Issues Charter Step 18, Ticket 18.1*

2. Add pulsing progress indicator to Extracting status badge (`JobList.tsx`, `App.css`)
   1. Add a CSS `@keyframes` pulse animation on `.status-badge--extracting`
   2. Add `title="Processing PDF — this may take 30-60 seconds for large documents"` attribute
   - *Issues Charter Step 17, Ticket 17.1*

3. Derive audit trail sheet selector dynamically from provenance records (`AuditTrailView.tsx`)
   1. Replace hardcoded `["Reconciliation", "Source_Inputs"]` options with:
      `const availableSheets = [...new Set(provenanceRecords.map(r => r.sheet_name))].sort()`
   2. Default `selectedSheet` to the first item, or `"Reconciliation"` if present
   - *Issues Charter Step 8, Ticket 8.1*

4. Detect and surface target metric not found in document (`job_runner.py`, `review/router.py`, `ReviewPage.tsx`)
   1. In `job_runner.py`, after `parse_pdf()`: check if `target_metric.lower()` appears in any `item.table_name` — if not, set `target_metric_found: bool = False` on `ExtractionSummary`
   2. In `review/router.py`: include `target_metric_found` in `ReviewItemsResponse`
   3. In `ReviewPage.tsx`: render a dismissible amber banner when `target_metric_found === false`
   - *Issues Charter Step 19, Tickets 19.1-19.2*

5. Warn user when PyMuPDF fallback was used (`ReviewPage.tsx`)
   1. When `data.parser_used === "pymupdf"` or `"mixed"`, render a dismissible amber banner
   - *Issues Charter Step 5, Ticket 5.2*

6. Make CORS origin configurable (`backend/app/main.py`)
   1. Replace hardcoded `allow_origins=["http://localhost:5173"]` with env var `ALLOWED_ORIGINS`
   2. Document `ALLOWED_ORIGINS` env var in README
   - *Issues Charter Step 20, Ticket 20.1*

### 10. P2 — Fix Duplicate Routes and DI Inconsistency

1. Remove duplicate drift mark-relabeled route (`drift/router.py`)
   1. Keep only the namespaced `/jobs/{job_id}/mark-relabeled` form
   2. Remove the bare `/{job_id}/mark-relabeled` route

2. Fix `narrative/router.py` to use `Depends()` for all repositories
   1. Current anti-pattern: module-level singleton repositories (lines 30-31)
   2. Define `get_job_repository()` and `get_narrative_repository()` as dependency provider functions
   3. Inject via `Annotated[T, Depends(get_x)]` in each endpoint signature

3. Fix `footnote/router.py` to use `Depends()` for all repositories
   1. Same singleton anti-pattern (lines 30-33): `_default_job_repo`, `_default_schedule_repo`, `_default_lease_repo`, `_default_concentration_repo`
   2. Apply same fix as 10.2

4. Fix `excel_export/router.py` global mutable repository pattern
   1. `set_model_repository()` uses `global _model_repo`
   2. Replace with proper `Depends()` injection or document the test override mechanism

5. Fix `drift/router.py` global state pattern
   1. `set_drift_repository()`, `set_job_repository()`, `set_review_repository()`, `set_drift_graph()` all use `global` module-level state
   2. Replace with `Depends()` injection

### 11. P3 — Fix Health Check Bug

1. Fix `db_ok` logic inversion in health check (`backend/app/main.py`, line 104)
   1. Current code: `except (sqlite3.Error, OSError): db_ok = True` — a database failure sets db_ok to True (inverted logic)
   2. Fix: `except (sqlite3.Error, OSError): db_ok = False`
   3. This is a single-character fix: the health endpoint currently always reports the database as healthy even when it is failing

### 12. P3 — Normalize Audit Report Route Prefix

1. Standardize to consistent prefix without `/api/`
   1. Routes are registered as both `/api/jobs/{id}/audit-report` AND `/jobs/{id}/audit-report` (the latter hidden from schema)
   2. All other endpoints use no `/api/` prefix
   3. Recommended: remove the `/api/` prefix variant; update `AuditTrailView.tsx` fetch calls accordingly

### 13. P3 — Freeze the Eval Harness

1. Add `eval/README.md` with freeze notice
   > "Frozen pending pilot client confirmation. The benchmark corpus (`eval/corpus/`) does not yet exist. No ground-truth annotations have been produced. Do not add to this harness until a pilot client confirms the pipeline handles their primary use case end-to-end. See `docs/business_alignment.md` §1.1."

### 14. P3 — Wire `footnote/` Module into Pipeline as Workflow Pack 2 and Defer `narrative/`

1. Wire `footnote/` into the automated pipeline
   1. Instead of leaving `footnote/` orphaned or deleting it, bind it directly to `workflow_pack == "capital_structure"`.
   2. When selected, `job_runner.py` invokes `footnote/extractor.py` to extract Debt tranches and ASC 842 lease schedules, making the REST endpoints functional.

2. Defer `narrative/` module from primary pipeline
   1. MD&A and risk-factor word diffing are secondary reading tools, not financial spreading tools.
   2. Keep `narrative/` routes isolated and comment out from active production bundle until the core numeric spreading packs are bulletproof.

---

## Part D — Decision Justifications

| # | Change | Justification |
|---|---|---|
| 1.1-1.4 | Bbox coordinate fixes | Without correct bbox coordinates the review UI highlight feature — the primary UX differentiator — is broken for every PDF. PyMuPDF assigns the whole table bbox to every cell (confirmed 1-based index bug). The product cannot be demoed until this is fixed. Issues Charter Step 1 is P0. |
| 1.5-1.6 | Scale/canvas size fixes | ReviewPage and AuditTrailView render at different scales (1.5 vs 1.3). `clientWidth` includes CSS padding. The same item appears at different pixel positions in each view. These are confirmed systematic measurement errors. One constant, one API call change each. |
| 2.1-2.4 | Review queue fixes | The queue currently shows 300+ items for a typical filing. This defeats the product's core promise. Three compounding bugs: overly broad candidate tagging, missing auto-lock of high-confidence items, wrong frontend filter predicate. All three are fixable deterministically without touching the LLM boundary. |
| 3.1-3.2 | Isolation violation fix | `audit_report/compiler.py` directly imports from `excel_export/generator.py` and `formula_engine/`. This is a documented Constitution §3.10 violation. The fix: a `model_compilation_service.py` at the app-root tier. Architecture hygiene prevents future cross-contamination and enables proper testing. |
| 4.1-4.2 | Content-based review IDs | Sequential loop-index IDs break audit trail cross-references whenever classification re-runs or record order shifts. Content-hash IDs keyed on `(source_file, page, bbox)` are stable — the same physical cell always gets the same ID. This is a prerequisite for reliable audit trail operation. |
| 5.1-5.3 | Audit PDF download fixes | The export button is an always-active link that silently fails for every user who has not generated a model. The empty state gives no actionable guidance. Both are trivially fixable frontend changes gated on the existing `model_ready` prop already passed from App.tsx. |
| 6.1-6.3 | Pipeline failure visibility | When `formula_inputs.nodes` is empty, the job reports `done` with `model_ready=false` and no explanation. The `model_skip_reason` field already exists on `JobRecord` in both Python and TypeScript — this is a matter of verifying it's populated and surfaced. |
| 7.1-7.4 | Introduce Targeted Workflow Packs | The 6-tab model is useless bloatware (analysts get 3-statement data from FactSet), but the 2-tab model was too naive in isolation. Free-form "ask what model you want" fails because bankers already have rigid internal templates and unconstrained 10-K extraction implodes. Workflow Packs solve the actual manual pain point: **footnote spreading** (Debt, Leases, EBITDA adjustments) with bounded extraction and deterministic DAG formulas. |
| 8.1-8.3 | Deduplicate utility functions | `_parse_numeric_value()` appears three times with a subtle format divergence (0 vs 2 decimal places). Any bug fix currently requires three identical edits. Extract to `excel_export/utils.py`. |
| 9.1-9.6 | UX polish fixes | Each is a documented, self-contained fix from Issues Charter Steps 5, 8, 9, 17, 18, 19, 20. They are not P0 but collectively determine whether the product is usable day-to-day. |
| 10.1-10.5 | DI consistency + duplicate routes | Module-level singleton repositories bypass `app.dependency_overrides` — the narrative and footnote tests are absent because these modules are untestable without DI fixes. The Constitution mandates `Depends()` injection. |
| 11.1 | Health check bug | `except (sqlite3.Error, OSError): db_ok = True` means a database failure sets db_ok to True. The health endpoint always reports the database as healthy. One-character fix with outsized operational impact. |
| 12.1 | Route prefix normalization | `/api/jobs/{id}/audit-report` uses an `/api/` prefix not used anywhere else. Inconsistent prefixes confuse new engineers and cause incorrect frontend fetch paths if followed cargo-cult style. |
| 13.1 | Freeze eval harness | The eval harness is sophisticated infrastructure without a corpus. `plan.md` says "freeze pending pilot client confirmation." Investing in harness maintenance before the core pipeline is correct sequences incorrectly. |
| 14.1-14.2 | Wire `footnote/` as Pack 2 engine | Reconnects previously orphaned code directly to a revenue-grade use case (Capital Structure & Debt Sizing). Defers narrative diffing to protect team bandwidth for numeric accuracy. |

---

## Appendix: Files With Open Issues Summary

| File | Issue Type | Issues Charter Steps |
|---|---|---|
| `backend/app/main.py` | Health check db_ok logic inversion; hardcoded CORS origin | Step 20; Bug (line 104) |
| `backend/app/ingestion/models.py` | Add `workflow_pack` to `JobRecord` | Section 7.1 |
| `backend/app/ingestion/router.py` | Accept `workflow_pack` in upload endpoints | Section 7.1 |
| `extraction/docling_parser.py` | PyMuPDF bbox 1-based index bug; bounded section filtering | Step 1 (T1.1); Section 7.2 |
| `extraction/coordinate_normalizer.py` | Y-axis inversion for Docling coordinates | Step 1 (T1.2) |
| `extraction/confidence.py` | Missing numeric value + table-consistency signals | Step 6 (T6.1, T6.2) |
| `classification/normalizer.py` | Overly broad `is_target_metric_candidate_item()` | Step 3 (T3.2) |
| `review/repository.py` | Missing auto-lock of auto_accepted+matched items; fragile sequential IDs | Step 3 (T3.1), Step 12 (T12.1) |
| `audit_trail/resolver.py` | Sequential ID matching breaks on re-run | Step 12 (T12.2) |
| `audit_report/compiler.py` | Isolation violation: imports excel_export + formula_engine | Step 13 (T13.1, T13.2) |
| `job_runner.py` | Route by `workflow_pack`; retire 6-tab default; model_skip_reason not populated | Steps 7, 19, 11 |
| `excel_export/generator.py` | Update to `bridge_generator.py`; deduplicate `_parse_numeric_value` | Section 7.3, 8.1 |
| `excel_export/multi_statement_generator.py` | Demote to legacy/full-model only; deduplicate utility functions | Section 7.3, 8.1 |
| `drift/router.py` | Duplicate mark-relabeled route; global mutable state pattern | Section 10.1, 10.5 |
| `narrative/router.py` | Module-level singleton repositories (untestable); defer from main pipeline | Section 10.2, 14.2 |
| `footnote/router.py` | Wire into pipeline as Pack 2; fix module-level singletons | Section 10.3, 14.1 |
| `frontend/ReviewPage.tsx` | `isFlagged` predicate bug; `alert()` usage; no generate button in empty flagged state | Steps 3, 9, 18 |
| `frontend/AuditTrailView.tsx` | Always-active export button; hardcoded sheet selector; mismatched scale (1.3 vs 1.5) | Steps 2, 4, 8, 15 |
| `frontend/src/components/UploadZone.tsx` | Add Workflow Pack selection UI | Section 7.4 |
| `frontend/lib/pdf/renderer.ts` | No shared `PDF_RENDER_SCALE` constant | Step 15 |

---

*Total open issues: 34 tickets across 20 steps in `docs/issues_charter.md`. Structured into actionable priority tiers.*
