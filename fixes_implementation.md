# Footnote — Fixes Implementation Plan

> **Generated:** 2026-09-03  
> **Source:** Diagnostic Fixes Report (`fixes.md`) & Issues Charter (`docs/issues_charter.md`)  
> **Architecture Target:** Core Correctness, Review UX, Strict Isolation, Intent-Driven Workflow Packs  
> **Execution Strategy:** 14 Steps, 44 Atomic Tickets implemented and verified one at a time.

---

## Master Progress Tracker

| Step | Priority | Title | Tickets | Status |
|---|---|---|:---:|:---:|
| [Step 1](#step-1--p0--fix-core-coordinate--rendering-correctness-bugs) | **P0** | Fix Core Coordinate & Rendering Correctness Bugs | 6 | `[x]` 6/6 |
| [Step 2](#step-2--p0--fix-review-queue-overcrowding--confidence-scoring) | **P0** | Fix Review Queue Overcrowding & Confidence Scoring | 5 | `[x]` 5/5 |
| [Step 3](#step-3--p0--fix-architectural-isolation-violation) | **P0** | Fix Architectural Isolation Violation | 2 | `[x]` 2/2 |
| [Step 4](#step-4--p1--fix-fragile-review-item-ids--audit-trail-resolution) | **P1** | Fix Fragile Review Item IDs & Audit Trail Resolution | 2 | `[x]` 2/2 |
| [Step 5](#step-5--p1--fix-audit-pdf-export--empty-state-guidance) | **P1** | Fix Audit PDF Export & Empty State Guidance | 4 | `[x]` 4/4 |
| [Step 6](#step-6--p1--surface-pipeline-failures--review-completion-actions) | **P1** | Surface Pipeline Failures & Review Completion Actions | 3 | `[x]` 3/3 |
| [Step 7](#step-7--p2--introduce-targeted-workflow-packs-architecture) | **P2** | Introduce Targeted Workflow Packs Architecture | 4 | `[x]` 4/4 |
| [Step 8](#step-8--p2--extract-and-deduplicate-shared-excel-utilities) | **P2** | Extract and Deduplicate Shared Excel Utilities | 2 | `[x]` 2/2 |
| [Step 9](#step-9--p2--fix-remaining-ux--operational-issues) | **P2** | Fix Remaining UX & Operational Issues | 6 | `[ ]` 0/6 |
| [Step 10](#step-10--p2--fix-route-duplication-and-dependency-injection-consistency) | **P2** | Fix Route Duplication and Dependency Injection Consistency | 5 | `[ ]` 0/5 |
| [Step 11](#step-11--p3--fix-health-check-logic-inversion) | **P3** | Fix Health Check Logic Inversion | 1 | `[ ]` 0/1 |
| [Step 12](#step-12--p3--normalize-audit-report-route-prefix) | **P3** | Normalize Audit Report Route Prefix | 1 | `[ ]` 0/1 |
| [Step 13](#step-13--p3--freeze-the-evaluation-harness) | **P3** | Freeze the Evaluation Harness | 1 | `[ ]` 0/1 |
| [Step 14](#step-14--p3--wire-footnote-as-workflow-pack-2-and-defer-narrative) | **P3** | Wire `footnote/` as Workflow Pack 2 and Defer `narrative/` | 2 | `[ ]` 0/2 |

**Total:** 14 Steps, 44 Atomic Tickets

---

## Step 1 — P0 — Fix Core Coordinate & Rendering Correctness Bugs

- **Objective:** Ensure all extracted table cells have exact bounding-box coordinates in screen space, resolving the whole-table highlight bug, Y-axis inversion, and viewer scaling disparities.
- **Priority:** P0 (Demo Blocker)

### Tickets

| Ticket ID | Title | Target File | Status |
|---|---|---|:---:|
| Ticket 1.1 | Fix PyMuPDF fallback per-cell bbox indexing | `backend/app/extraction/docling_parser.py` | `[x]` |
| Ticket 1.2 | Add Y-axis inversion for Docling-native coordinates | `backend/app/extraction/coordinate_normalizer.py` | `[x]` |
| Ticket 1.3 | Add `parser_used` metadata to `DoclingItem` and propagate | `backend/app/extraction/models.py`, `docling_parser.py` | `[x]` |
| Ticket 1.4 | Write comprehensive unit tests for both bbox coordinate paths | `backend/tests/test_coordinate_normalizer.py` | `[x]` |
| Ticket 1.5 | Standardize PDF render scale across frontend views | `frontend/src/lib/pdf/renderer.ts`, `ReviewPage.tsx`, `AuditTrailView.tsx` | `[x]` |
| Ticket 1.6 | Fix canvas dimension read using `getBoundingClientRect()` | `frontend/src/components/review/ReviewPage.tsx`, `frontend/src/components/audit/AuditTrailView.tsx` | `[x]` |

---

### Ticket 1.1 — Fix PyMuPDF fallback per-cell bbox indexing

- **File:** `backend/app/extraction/docling_parser.py` (`_parse_pdf_with_pymupdf`)
- **Problem:** Loop iterates with 1-based indexing (`row_idx=1, col_idx=1`) and calculates `flat_idx = row_idx * len(row) + col_idx`. This skips `(0,0)`, overruns cell bounds, and falls back to assigning the bounding box of the entire table to every cell.
- **Implementation:**
  1. Change row and col loops to 0-based indexing: `for r_i, row in enumerate(table_data): for c_i, cell in enumerate(row):`.
  2. Compute flat index: `flat_idx = r_i * num_cols + c_i`.
  3. Validate that `table.cells` exists and is non-empty; if `flat_idx < len(table.cells)`, assign `table.cells[flat_idx]`, else use cell bbox fallback.
- **Acceptance Criteria:** For a test PDF extracted via PyMuPDF, each cell receives its individual cell bbox coordinates instead of the enclosing table's bounding rectangle.
- **Verification:** Run `pytest backend/tests/test_docling_parser.py` (or extraction tests).

---

### Ticket 1.2 — Add Y-axis inversion for Docling-native coordinates

- **File:** `backend/app/extraction/coordinate_normalizer.py` (`normalize_item_bbox`)
- **Problem:** Docling uses a bottom-left origin ($y=0$ at bottom of page), while PyMuPDF, PDF.js, and HTML5 Canvas use a top-left origin ($y=0$ at top). Direct scaling causes vertical positions to invert on screen.
- **Implementation:**
  1. When source is Docling (`parser_used == "docling"` or `item.parser_used == "docling"`):
     ```python
     y0_screen = 1000.0 - y1_norm
     y1_screen = 1000.0 - y0_norm
     ```
  2. When source is PyMuPDF (`parser_used == "pymupdf"`), keep existing direct top-left normalization.
  3. Add clear module-level docstring defining the 0–1000 top-left normalized screen coordinate system.
- **Acceptance Criteria:** A cell located at the bottom of a 792pt page extracted by Docling normalizes with $y_0 \approx 900+$, matching screen placement.
- **Verification:** Run `pytest backend/tests/test_coordinate_normalizer.py`.

---

### Ticket 1.3 — Add `parser_used` metadata to `DoclingItem` and propagate

- **Files:** `backend/app/extraction/models.py`, `backend/app/extraction/docling_parser.py`
- **Problem:** Coordinate normalizer has to guess which parser generated coordinates unless explicitly tagged.
- **Implementation:**
  1. In `DoclingItem`, add `parser_used: Literal["docling", "pymupdf"] = "docling"`.
  2. In `_parse_pdf_with_pymupdf()`, set `parser_used="pymupdf"` on every instantiated item.
  3. In `_parse_pdf_with_docling()`, set `parser_used="docling"`.
  4. Ensure `parser_used` survives serialization to `docling_items.json`.
- **Acceptance Criteria:** Extracted JSON files contain `"parser_used": "pymupdf"` or `"parser_used": "docling"` on all items.
- **Verification:** Check serialization output on sample fixture document.

---

### Ticket 1.4 — Write comprehensive unit tests for both bbox coordinate paths

- **File:** `backend/tests/test_coordinate_normalizer.py`
- **Problem:** No automated regression tests verifying Docling bottom-left vs PyMuPDF top-left coordinate mapping.
- **Implementation:**
  1. Test Docling path: `y0=50, y1=100` on 792pt page $\rightarrow$ inverted $y_{0,\text{screen}} \approx 873$.
  2. Test PyMuPDF path: `y0=50, y1=100` on 792pt page $\rightarrow$ top-left $y_{0,\text{screen}} \approx 63$.
  3. Test 3x4 table flat indexing: verify 12 unique bounding boxes generated from mocked `table.cells`.
- **Acceptance Criteria:** All unit tests pass with `pytest backend/tests/test_coordinate_normalizer.py`.
- **Verification:** Run `pytest -v backend/tests/test_coordinate_normalizer.py`.

---

### Ticket 1.5 — Standardize PDF render scale across frontend views

- **Files:** `frontend/src/lib/pdf/renderer.ts`, `frontend/src/components/review/ReviewPage.tsx`, `frontend/src/components/audit/AuditTrailView.tsx`
- **Problem:** `ReviewPage.tsx` renders PDF pages at scale 1.5, while `AuditTrailView.tsx` renders at scale 1.3, resulting in bbox pixel misalignment when switching between tabs.
- **Implementation:**
  1. In `frontend/src/lib/pdf/renderer.ts`, export `export const PDF_RENDER_SCALE = 1.5;`.
  2. Import and use `PDF_RENDER_SCALE` in `AuditTrailView.tsx` and `ReviewPage.tsx`.
- **Acceptance Criteria:** Both views render PDF canvas elements at identical pixel dimensions for the same page.
- **Verification:** Frontend test / browser verification of canvas element dimensions.

---

### Ticket 1.6 — Fix canvas dimension read using `getBoundingClientRect()`

- **Files:** `frontend/src/components/review/ReviewPage.tsx`, `frontend/src/components/audit/AuditTrailView.tsx`
- **Problem:** Canvas size calculation relies on `clientWidth` / `clientHeight` which include CSS padding and borders, skewing overlay coordinate calculations.
- **Implementation:**
  1. Replace `canvasRef.current.clientWidth` with:
     ```ts
     const rect = canvasRef.current.getBoundingClientRect();
     setCanvasSize({ width: Math.round(rect.width), height: Math.round(rect.height) });
     ```
  2. Ensure overlay highlight DIV positions use the exact bounding box rendered by PDF.js.
- **Acceptance Criteria:** Highlight boxes align flush with text without padding-induced offsets.
- **Verification:** Inspect canvas overlay in Review and Audit views.

---

## Step 2 — P0 — Fix Review Queue Overcrowding & Confidence Scoring

- **Objective:** Eliminate review queue bloat (300+ items reduced to only genuinely uncertain line items) by tightening target candidate gating, auto-locking matched items, and refining confidence signals.
- **Priority:** P0 (UX Blocker)

### Tickets

| Ticket ID | Title | Target File | Status |
|---|---|---|:---:|
| Ticket 2.1 | Auto-lock `auto_accepted` + `taxonomy_matched` items on init | `backend/app/review/repository.py` | `[x]` |
| Ticket 2.2 | Tighten `is_target_metric_candidate_item()` candidate filter | `backend/app/classification/normalizer.py` | `[x]` |
| Ticket 2.3 | Fix frontend `isFlagged` filter to status-based check | `frontend/src/components/review/ReviewPage.tsx` | `[x]` |
| Ticket 2.4 | Add numeric value (+0.05) & reconciliation (+0.15) signals | `backend/app/extraction/confidence.py` | `[x]` |
| Ticket 2.5 | Add table-consistency second-pass boost in `score_records` | `backend/app/extraction/confidence.py` | `[x]` |

---

### Ticket 2.1 — Auto-lock `auto_accepted` + `taxonomy_matched` items on init

- **File:** `backend/app/review/repository.py` (`_from_classified_records`)
- **Problem:** High-confidence items ($confidence \ge 0.95$) that match the financial taxonomy are emitted with status `auto_accepted`, which the UI currently surfaces in the flagged tab.
- **Implementation:**
  1. When `sr.confidence_band == ConfidenceBand.auto_accepted` and `cr.taxonomy_status == TaxonomyStatus.matched`:
     Set `status = ReviewStatus.locked`.
  2. Locked items remain in `items` for completeness and audit trail, but are excluded from active review queues.
- **Acceptance Criteria:** High-confidence items matching taxonomy are marked `locked` and do not appear in the Flagged tab.
- **Verification:** Run review repository unit tests.

---

### Ticket 2.2 — Tighten `is_target_metric_candidate_item()` candidate filter

- **File:** `backend/app/classification/normalizer.py`
- **Problem:** Broad keyword fallback on raw labels flags unrelated items from P&L, balance sheet, and footnotes as reconciliation bridge candidates.
- **Implementation:**
  1. Require `is_reconciliation_candidate == True` on the record as the primary signal.
  2. If table title contains target metric name (`metric_lower in table_lower`), accept.
  3. Remove broad keyword scan fallback that accepts non-reconciliation table items.
- **Acceptance Criteria:** Balance sheet and P&L line items are not categorized as target metric reconciliation candidates.
- **Verification:** Run classification normalizer unit tests.

---

### Ticket 2.3 — Fix frontend `isFlagged` filter to status-based check

- **File:** `frontend/src/components/review/ReviewPage.tsx`
- **Problem:** `isFlagged()` uses `item.confidence_score < 0.95`, incorrectly flagging auto-accepted and locked items if score rounding differs.
- **Implementation:**
  1. Replace raw score check with explicit status filter:
     ```ts
     const isFlagged = (item: ReviewItem) =>
       ['needs_review', 'manual_required', 'extraction_error', 'pending_taxonomy_confirmation', 'flagged'].includes(item.status);
     ```
  2. Ensure `status === 'auto_accepted'` and `status === 'locked'` are never flagged.
- **Acceptance Criteria:** Flagged tab count matches exactly items needing human confirmation.
- **Verification:** Run `npm test -- ReviewPage.test.tsx`.

---

### Ticket 2.4 — Add numeric value (+0.05) & reconciliation (+0.15) signals

- **File:** `backend/app/extraction/confidence.py` (`compute_confidence_score`)
- **Problem:** Clean numeric values and flat labels in reconciliation tables are penalized by generic text heuristics.
- **Implementation:**
  1. Add Signal: $+0.05$ if value parses as clean numeric (after stripping `$`, `,`, `()`, `%`). Add `value_is_numeric` flag.
  2. Add Signal: $+0.15$ if `is_reconciliation_candidate == True`, offsetting `-0.15` flat-label deduction.
  3. Clamp final score to `[0.0, 1.0]`.
- **Acceptance Criteria:** Well-formed numbers in reconciliation tables achieve $\ge 0.95$ score when no extraction warnings exist.
- **Verification:** Run confidence scoring test suite.

---

### Ticket 2.5 — Add table-consistency second-pass boost in `score_records`

- **File:** `backend/app/extraction/confidence.py` (`score_records`)
- **Problem:** In a clean table where 80% of rows are high confidence, a few borderline rows are flagged unnecessarily.
- **Implementation:**
  1. After initial individual scoring, group records by `table_name`.
  2. If $\ge 70\%$ of items in a table scored $\ge 0.80$, boost remaining items in that table by $+0.10$ (clamped to 1.0).
  3. Record `table_consistency_boost` in diagnostic flags.
- **Acceptance Criteria:** Borderline cells in well-structured tables are elevated to `auto_accepted` or `needs_review` rather than `manual_required`.
- **Verification:** Test `score_records` with multi-row table fixtures.

---

## Step 3 — P0 — Fix Architectural Isolation Violation

- **Objective:** Restore Constitution §3.10 boundary isolation by decoupling `audit_report/` from direct imports of `excel_export/` and `formula_engine/`.
- **Priority:** P0 (Architecture Violation)

### Tickets

| Ticket ID | Title | Target File | Status |
|---|---|---|:---:|
| Ticket 3.1 | Create `model_compilation_service.py` at app root | `backend/app/model_compilation_service.py` | `[x]` |
| Ticket 3.2 | Decouple `audit_report/compiler.py` from `excel_export` | `backend/app/audit_report/compiler.py` | `[x]` |

---

### Ticket 3.1 — Create `model_compilation_service.py` at app root

- **File:** `backend/app/model_compilation_service.py` (New File)
- **Problem:** On-the-fly model compilation requires orchestrating `excel_export` and `formula_engine`. Doing this inside `audit_report/compiler.py` violates modular layer boundaries.
- **Implementation:**
  1. Define pure orchestration function:
     ```python
     def try_compile_model_on_the_fly(
         job_id: str,
         review_items: list[ReviewItem] | None,
         classified_records: list[ClassifiedRecord] | None,
         data_dir: Path,
     ) -> list[W3CAnnotationRecord] | None:
     ```
  2. Move on-the-fly generation logic from `compiler.py` (lines 92–117) into this service.
- **Acceptance Criteria:** Cross-subsystem orchestration lives at app-root level (same tier as `job_runner.py`).
- **Verification:** Unit test `try_compile_model_on_the_fly` with mocked records.

---

### Ticket 3.2 — Decouple `audit_report/compiler.py` from `excel_export`

- **File:** `backend/app/audit_report/compiler.py`
- **Problem:** Direct imports `from app.excel_export.generator import generate_workbook` and `from app.formula_engine.reader import ...` violate §3.10.
- **Implementation:**
  1. Remove imports of `excel_export` and `formula_engine` from `compiler.py`.
  2. Import and call `try_compile_model_on_the_fly` from `app.model_compilation_service`.
  3. Run `ruff check backend/app/audit_report/` to verify zero layer boundary violations.
- **Acceptance Criteria:** `audit_report/` has zero dependencies on `excel_export` or `formula_engine`.
- **Verification:** Run `ruff check backend/app/audit_report/`.

---

## Step 4 — P1 — Fix Fragile Review Item IDs & Audit Trail Resolution

- **Objective:** Eliminate fragile sequential loop-index review IDs (`{job_id}_{idx}`) so that re-running classification or filtering does not break audit trail provenance cross-references.
- **Priority:** P1

### Tickets

| Ticket ID | Title | Target File | Status |
|---|---|---|:---:|
| Ticket 4.1 | Replace sequential index IDs with content-based hash | `backend/app/review/repository.py` | `[x]` |
| Ticket 4.2 | Update audit trail resolver to use content-hash matching | `backend/app/audit_trail/resolver.py` | `[x]` |

---

### Ticket 4.1 — Replace sequential index IDs with content-based hash

- **File:** `backend/app/review/repository.py` (`_from_classified_records`, `_from_scored_records`)
- **Problem:** When items are created as `id=f"{job_id}_{idx}"`, any order shift or pipeline re-run invalidates stored IDs.
- **Implementation:**
  1. Create deterministic helper:
     ```python
     def _make_review_id(job_id: str, source_file: str, page: int, bbox: dict) -> str:
         key = f"{job_id}:{source_file}:{page}:{bbox.get('x0',0):.0f}:{bbox.get('y0',0):.0f}"
         return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
     ```
  2. Use this helper across both `_from_classified_records` and `_from_scored_records`.
- **Acceptance Criteria:** Re-processing the same document produces stable review IDs for the same physical cells.
- **Verification:** Unit test comparing IDs across two runs with shuffled input order.

---

### Ticket 4.2 — Update audit trail resolver to use content-hash matching

- **File:** `backend/app/audit_trail/resolver.py` (`_resolve_record_chain`)
- **Problem:** Resolver extracts leaf indices via regex `r"^leaf_(\d+)_"`, which fails with content-hash IDs.
- **Implementation:**
  1. Build lookup `review_item_by_hash: dict[str, ReviewItem]` using `_make_review_id`.
  2. Extract `source_file`, `page`, and `bbox` from the leaf record's target selector, compute hash, and match directly.
- **Acceptance Criteria:** Audit trail resolver correctly finds matching ReviewItems by content hash.
- **Verification:** Run `pytest backend/tests/test_audit_trail_resolver.py`.

---

## Step 5 — P1 — Fix Audit PDF Export & Empty State Guidance

- **Objective:** Fix broken "Export Audit PDF" button, provide clear onboarding guidance when no model exists, and offer in-page provenance refreshing.
- **Priority:** P1

### Tickets

| Ticket ID | Title | Target File | Status |
|---|---|---|:---:|
| Ticket 5.1 | Gate Export Audit PDF button on `model_ready` flag | `frontend/src/components/audit/AuditTrailView.tsx`, `App.tsx` | `[x]` |
| Ticket 5.2 | Enrich audit trail empty state with 4-step checklist | `frontend/src/components/audit/AuditTrailView.tsx` | `[x]` |
| Ticket 5.3 | Add in-page provenance refresh button | `frontend/src/components/audit/AuditTrailView.tsx` | `[x]` |
| Ticket 5.4 | Surface structured error on audit report failure | `backend/app/audit_report/service.py`, `router.py` | `[x]` |

---

### Ticket 5.1 — Gate Export Audit PDF button on `model_ready` flag

- **Files:** `frontend/src/components/audit/AuditTrailView.tsx`, `frontend/src/App.tsx`
- **Problem:** Export button is an active `<a>` link that raises HTTP 400 when clicked prior to model generation.
- **Implementation:**
  1. Accept `modelReady: boolean` in `AuditTrailViewProps` (passed from `App.tsx`).
  2. When `!modelReady`, render a disabled `<button>` with tooltip: *"Generate a model first: go to Review and click 'Approve & Generate'"*.
  3. When `modelReady`, render the active `<a download>` link.
- **Acceptance Criteria:** Disabled button shown when `model_ready=false`; active download link shown when `true`.
- **Verification:** Run `npm test -- AuditTrailView.test.tsx`.

---

### Ticket 5.2 — Enrich audit trail empty state with 4-step checklist

- **File:** `frontend/src/components/audit/AuditTrailView.tsx`
- **Problem:** Empty state shows an unhelpful "Model not yet generated" card without instructions.
- **Implementation:**
  1. Replace banner with a 4-step numbered checklist:
     1. Go to the Review tab
     2. Review flagged reconciliation items
     3. Click "Approve & Generate Complete Financial Model"
     4. Return here to inspect cell-level provenance
  2. Include primary CTA button "Go to Review Tab →" calling `onReview(jobId)`.
- **Acceptance Criteria:** Clear actionable path presented to first-time users.
- **Verification:** Verify visual render of empty state in frontend test.

---

### Ticket 5.3 — Add in-page provenance refresh button

- **File:** `frontend/src/components/audit/AuditTrailView.tsx`
- **Problem:** If user generates model in another tab, switching back requires a hard page reload to see provenance.
- **Implementation:**
  1. Extract provenance fetching effect into a callable `loadProvenance()` function.
  2. Add a "↻ Refresh" button in the header calling `loadProvenance()`.
- **Acceptance Criteria:** Clicking Refresh updates provenance records without full page reload.
- **Verification:** Manual UI test / Cypress test.

---

### Ticket 5.4 — Surface structured error on audit report failure

- **Files:** `backend/app/audit_report/service.py`, `backend/app/audit_report/router.py`
- **Problem:** Endpoint returns generic 400 when model compilation fails mid-stream.
- **Implementation:**
  1. Catch `ModelNotCompleteError` and return structured JSON:
     `{"detail": "...", "hint": "Confirm at least one line item in the Review tab, then click Generate Model."}`.
- **Acceptance Criteria:** API returns clear, structured hints on HTTP 400 responses.
- **Verification:** Unit test `test_audit_report_router.py`.

---

## Step 6 — P1 — Surface Pipeline Failures & Review Completion Actions

- **Objective:** Prevent silent pipeline failures when formulas fail, surface `model_skip_reason` in the job list, and provide a clear model generation action when all items are reviewed.
- **Priority:** P1

### Tickets

| Ticket ID | Title | Target File | Status |
|---|---|---|:---:|
| Ticket 6.1 | Populate and persist `model_skip_reason` on `JobRecord` | `backend/app/ingestion/models.py`, `repository.py`, `job_runner.py` | `[x]` |
| Ticket 6.2 | Surface `model_skip_reason` tooltip in `JobList` | `frontend/src/components/JobList.tsx`, `frontend/src/types/job.ts` | `[x]` |
| Ticket 6.3 | Add "Approve & Generate Model" CTA to empty Flagged tab | `frontend/src/components/review/ReviewPage.tsx` | `[x]` |

---

### Ticket 6.1 — Populate and persist `model_skip_reason` on `JobRecord`

- **Files:** `backend/app/ingestion/models.py`, `backend/app/ingestion/repository.py`, `backend/app/job_runner.py`
- **Problem:** When `formula_inputs.nodes` is empty, `model_ready` is `False`, but no explanation is saved.
- **Implementation:**
  1. Ensure `model_skip_reason: str | None = None` is on `JobRecord`.
  2. In `job_runner.py`:
     - If `len(formula_inputs.nodes) == 0`: set `model_skip_reason = formula_inputs.error_message or "No auto-accepted or confirmed records available"`.
     - If `comp_tree.is_valid == False`: set `model_skip_reason = comp_tree.error_message`.
  3. Pass `model_skip_reason` to `repo.update_job_status()` and persist in `jobs.json`.
- **Acceptance Criteria:** `GET /upload/jobs` returns `model_skip_reason` string whenever `model_ready == False`.
- **Verification:** Integration test running pipeline on non-reconciliation document.

---

### Ticket 6.2 — Surface `model_skip_reason` tooltip in `JobList`

- **Files:** `frontend/src/components/JobList.tsx`, `frontend/src/types/job.ts`
- **Problem:** User sees "Awaiting Review" or "Done" with no explanation for why Excel model was skipped.
- **Implementation:**
  1. Ensure `model_skip_reason?: string | null` in `JobRecord` TypeScript type.
  2. In `StatusBadge`, when `status === 'done' && !model_ready`, display an information icon `ⓘ` with tooltip showing `model_skip_reason`.
- **Acceptance Criteria:** Hovering over the status badge displays the exact skip reason.
- **Verification:** Run `npm test -- JobList.test.tsx`.

---

### Ticket 6.3 — Add "Approve & Generate Model" CTA to empty Flagged tab

- **File:** `frontend/src/components/review/ReviewPage.tsx`
- **Problem:** When all items are auto-accepted or confirmed, the Flagged tab is empty but lacks an inline CTA to trigger model generation.
- **Implementation:**
  1. When `activeTab === 'flagged'` and flagged items count is 0:
     Render guidance text: *"All items reviewed. Ready to generate the financial model."*
     Render button: `<button onClick={() => void handleApproveBridgeAndGenerateModel()}>Approve & Generate Model →</button>`.
- **Acceptance Criteria:** User can trigger model generation directly from the empty flagged tab.
- **Verification:** Run `npm test -- ReviewPage.test.tsx`.

---

## Step 7 — P2 — Introduce Targeted Workflow Packs Architecture

- **Objective:** Move away from monolithic 6-tab generation towards intent-driven workflow packs (Pack 1: Non-GAAP Bridge, Pack 2: Capital Structure, Pack 3: Cash Conversion) with bounded extraction.
- **Priority:** P2

### Tickets

| Ticket ID | Title | Target File | Status |
|---|---|---|:---:|
| Ticket 7.1 | Add `workflow_pack` to Ingestion Schemas & API | `backend/app/ingestion/models.py`, `router.py`, `frontend/src/types/job.ts` | `[x]` |
| Ticket 7.2 | Implement Bounded Extraction Routing in Pipeline | `backend/app/job_runner.py`, `backend/app/extraction/docling_parser.py` | `[x]` |
| Ticket 7.3 | Restructure Generators: `bridge_generator.py` and demote 6-tab | `backend/app/excel_export/` | `[x]` |
| Ticket 7.4 | Add Workflow Pack Selector to `UploadZone` UI | `frontend/src/components/UploadZone.tsx`, `frontend/src/App.tsx` | `[x]` |

---

### Ticket 7.1 — Add `workflow_pack` to Ingestion Schemas & API

- **Files:** `backend/app/ingestion/models.py`, `backend/app/ingestion/router.py`, `frontend/src/types/job.ts`
- **Problem:** The ingestion pipeline treats every PDF identically without knowing the banker's intended spreading task.
- **Implementation:**
  1. Add `WorkflowPack = Literal["non_gaap_bridge", "capital_structure", "cash_conversion"]` to `models.py`.
  2. Add `workflow_pack: WorkflowPack = "non_gaap_bridge"` to `JobRecord`.
  3. Accept `workflow_pack: str = Form("non_gaap_bridge")` in `POST /upload/jobs` and `POST /upload/jobs/async`.
  4. Update TypeScript `JobRecord` type.
- **Acceptance Criteria:** Jobs are tagged with their selected `workflow_pack` from upload onwards.
- **Verification:** Test upload endpoint with `workflow_pack="capital_structure"`.

---

### Ticket 7.2 — Implement Bounded Extraction Routing in Pipeline

- **Files:** `backend/app/job_runner.py`, `backend/app/extraction/docling_parser.py`
- **Problem:** Unbounded 180-page extraction causes hallucinations, high review burden, and slow processing.
- **Implementation:**
  1. In `job_runner.py`, check `job.workflow_pack`:
     - `"non_gaap_bridge"`: filter parser to Item 7 MD&A non-GAAP reconciliation tables.
     - `"capital_structure"`: route parser to Note disclosures (Debt, Credit Facilities, Leases).
     - `"cash_conversion"`: filter parser to Statement of Cash Flows and Working Capital notes.
- **Acceptance Criteria:** Ingestion targets only relevant tables for the selected pack, discarding extraneous sections.
- **Verification:** Integration test verifying filtered table counts per pack.

---

### Ticket 7.3 — Restructure Generators: `bridge_generator.py` and demote 6-tab

- **File:** `backend/app/excel_export/`
- **Problem:** 6-tab generator was made the default despite client needs for clean 2-tab schedules.
- **Implementation:**
  1. Update `generator.py` to be the primary `bridge_generator.py` (2-tab: Source_Inputs + Reconciliation) for `non_gaap_bridge`.
  2. Demote `multi_statement_generator.py` to legacy / full-model on-demand endpoint only.
  3. Default pipeline output in `job_runner.py` to `bridge_generator.py` for Pack 1.
- **Acceptance Criteria:** Uploading for `non_gaap_bridge` produces the clean 2-tab formula-driven workbook.
- **Verification:** Inspect generated Excel file structure for test job.

---

### Ticket 7.4 — Add Workflow Pack Selector to `UploadZone` UI

- **Files:** `frontend/src/components/UploadZone.tsx`, `frontend/src/App.tsx`
- **Problem:** Analysts cannot select their spreading task in the UI before uploading.
- **Implementation:**
  1. In `UploadZone.tsx`, add an interactive card selector with 3 workflow packs:
     - **Earnings Quality / Non-GAAP Bridge** (Adjusted EBITDA, FCF bridge)
     - **Capital Structure & Debt Sizing** (Note 8 debt tranches, maturities, ASC 842 leases)
     - **Valuation & Cash Conversion** (Unlevered FCF, CapEx, Working Capital)
  2. Pass selected `workflow_pack` in form data when calling upload API.
- **Acceptance Criteria:** UI allows selecting pack before drop/upload; API payload contains `workflow_pack`.
- **Verification:** Component test for `UploadZone.tsx`.

---

## Step 8 — P2 — Extract and Deduplicate Shared Excel Utilities

- **Objective:** Eliminate triple-duplicated numeric parsing and coordinate conversion logic across Excel generators.
- **Priority:** P2

### Tickets

| Ticket ID | Title | Target File | Status |
|---|---|---|:---:|
| Ticket 8.1 | Create `excel_export/utils.py` with canonical `_parse_numeric_value` | `backend/app/excel_export/utils.py` | `[x]` |
| Ticket 8.2 | Extract `_col_to_letter` and `_to_cell_coord` into `utils.py` | `backend/app/excel_export/utils.py` | `[x]` |

---

### Ticket 8.1 — Create `excel_export/utils.py` with canonical `_parse_numeric_value`

- **Files:** `backend/app/excel_export/utils.py` (New File), `generator.py`, `multi_year_generator.py`, `multi_statement_generator.py`
- **Problem:** `_parse_numeric_value` is duplicated across 3 generator files with format divergence ($0$ vs $2$ decimals).
- **Implementation:**
  1. Create `backend/app/excel_export/utils.py`.
  2. Implement canonical `parse_numeric_value(val: Any) -> float | None` handling currency, parentheses, commas, percentages, and dashes.
  3. Replace all 3 duplicate implementations with imports from `utils.py`.
- **Acceptance Criteria:** All generators import shared `parse_numeric_value` from `excel_export.utils`.
- **Verification:** Run `pytest backend/tests/test_excel_export.py`.

---

### Ticket 8.2 — Extract `_col_to_letter` and `_to_cell_coord` into `utils.py`

- **Files:** `backend/app/excel_export/utils.py`, generator files
- **Problem:** Column-to-letter and cell coordinate conversion functions are redundantly defined.
- **Implementation:**
  1. Move `col_to_letter(col_idx: int) -> str` and `to_cell_coord(row: int, col: int) -> str` to `excel_export/utils.py`.
  2. Import in generator modules.
- **Acceptance Criteria:** Zero duplicate coordinate mapping functions in `excel_export/`.
- **Verification:** Unit tests in `backend/tests/test_excel_export.py`.

---

## Step 9 — P2 — Fix Remaining UX & Operational Issues

- **Objective:** Resolve UX papercuts (blocking `alert()`, missing progress feedback, static sheet selector, missing metric warning, CORS portability).
- **Priority:** P2

### Tickets

| Ticket ID | Title | Target File | Status |
|---|---|---|:---:|
| Ticket 9.1 | Replace blocking `alert()` with inline `editError` | `frontend/src/components/review/ReviewPage.tsx` | `[ ]` |
| Ticket 9.2 | Add pulsing extraction progress indicator | `frontend/src/components/JobList.tsx`, `frontend/src/App.css` | `[ ]` |
| Ticket 9.3 | Derive Audit Trail sheet selector dynamically | `frontend/src/components/audit/AuditTrailView.tsx` | `[ ]` |
| Ticket 9.4 | Detect and surface target metric not found warning | `backend/app/job_runner.py`, `review/router.py`, `ReviewPage.tsx` | `[ ]` |
| Ticket 9.5 | Surface PyMuPDF fallback degraded quality warning | `backend/app/review/router.py`, `frontend/src/components/review/ReviewPage.tsx` | `[ ]` |
| Ticket 9.6 | Make CORS origin configurable via `ALLOWED_ORIGINS` | `backend/app/main.py` | `[ ]` |

---

### Ticket 9.1 — Replace blocking `alert()` with inline `editError`

- **File:** `frontend/src/components/review/ReviewPage.tsx`
- **Problem:** Confirmation errors trigger browser `alert()`, which is jarring and inaccessible.
- **Implementation:**
  1. Replace `alert(err ...)` at line 333 with `setEditError(err instanceof Error ? err.message : 'Confirmation failed')`.
  2. Ensure error displays inline under the action button card.
- **Acceptance Criteria:** Error messages display in-page without modal alert dialogs.
- **Verification:** Frontend test simulating confirmation rejection.

---

### Ticket 9.2 — Add pulsing extraction progress indicator

- **Files:** `frontend/src/components/JobList.tsx`, `frontend/src/App.css`
- **Problem:** Extracting status is static, giving no feedback that background processing is active.
- **Implementation:**
  1. In `App.css`, define `@keyframes status-pulse` for `.status-badge--extracting`.
  2. Add tooltip `title="Processing PDF — this may take 30–60 seconds for large documents"`.
- **Acceptance Criteria:** Extracting badge displays visible animated pulse and helpful tooltip.
- **Verification:** Visual verification in browser.

---

### Ticket 9.3 — Derive Audit Trail sheet selector dynamically

- **File:** `frontend/src/components/audit/AuditTrailView.tsx`
- **Problem:** Sheet dropdown is hardcoded to `["Reconciliation", "Source_Inputs"]`, hiding other sheets in custom models.
- **Implementation:**
  1. Derive available sheets: `const availableSheets = [...new Set(provenanceRecords.map(r => r.sheet_name))].sort();`.
  2. Render dynamic `<option>` elements, defaulting to `'Reconciliation'` or first sheet.
- **Acceptance Criteria:** All sheets present in provenance records appear in selector.
- **Verification:** Frontend test with multi-sheet provenance fixture.

---

### Ticket 9.4 — Detect and surface target metric not found warning

- **Files:** `backend/app/job_runner.py`, `backend/app/review/router.py`, `frontend/src/components/review/ReviewPage.tsx`
- **Problem:** If target metric is not found in document, pipeline silently defaults without warning user.
- **Implementation:**
  1. In `job_runner.py`, check if `target_metric.lower()` matches any table title; set `target_metric_found: bool` on `ExtractionSummary`.
  2. Include `target_metric_found` in `ReviewItemsResponse`.
  3. In `ReviewPage.tsx`, render dismissible amber banner when `target_metric_found === false`.
- **Acceptance Criteria:** User alerted when target metric could not be matched to document tables.
- **Verification:** Integration test with non-GAAP mismatch.

---

### Ticket 9.5 — Surface PyMuPDF fallback degraded quality warning

- **Files:** `backend/app/review/router.py`, `frontend/src/components/review/ReviewPage.tsx`
- **Problem:** Users are unaware when Docling failed and PyMuPDF fallback was used.
- **Implementation:**
  1. Expose `parser_used` in `ReviewItemsResponse`.
  2. In `ReviewPage.tsx`, render dismissible banner: *"⚠ Extraction used PyMuPDF fallback — PDF highlights may be less accurate than usual."*
- **Acceptance Criteria:** Warning banner appears only when PyMuPDF or mixed parser was used.
- **Verification:** Test ReviewPage with mocked PyMuPDF response.

---

### Ticket 9.6 — Make CORS origin configurable via `ALLOWED_ORIGINS`

- **File:** `backend/app/main.py`
- **Problem:** Hardcoded `allow_origins=["http://localhost:5173"]` breaks when Vite runs on alternative ports.
- **Implementation:**
  1. Read from env: `_cors_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:5174")`.
  2. Parse into list and pass to `CORSMiddleware`.
  3. Document in `README.md`.
- **Acceptance Criteria:** CORS accepts origins configured in `ALLOWED_ORIGINS`.
- **Verification:** Test API request with custom Origin header.

---

## Step 10 — P2 — Fix Route Duplication and Dependency Injection Consistency

- **Objective:** Remove route duplication in `drift/` and eliminate untestable module-level singletons in `narrative/`, `footnote/`, `excel_export/`, and `drift/` using FastAPI `Depends()`.
- **Priority:** P2

### Tickets

| Ticket ID | Title | Target File | Status |
|---|---|---|:---:|
| Ticket 10.1 | Remove duplicate drift mark-relabeled route | `backend/app/drift/router.py` | `[ ]` |
| Ticket 10.2 | Migrate `narrative/router.py` to FastAPI `Depends()` | `backend/app/narrative/router.py` | `[ ]` |
| Ticket 10.3 | Migrate `footnote/router.py` to FastAPI `Depends()` | `backend/app/footnote/router.py` | `[ ]` |
| Ticket 10.4 | Eliminate mutable globals in `excel_export/router.py` | `backend/app/excel_export/router.py` | `[ ]` |
| Ticket 10.5 | Eliminate mutable globals in `drift/router.py` | `backend/app/drift/router.py` | `[ ]` |

---

### Ticket 10.1 — Remove duplicate drift mark-relabeled route

- **File:** `backend/app/drift/router.py`
- **Problem:** `POST /{job_id}/mark-relabeled` and `POST /jobs/{job_id}/mark-relabeled` both registered.
- **Implementation:**
  1. Remove the un-namespaced `/{job_id}/mark-relabeled` route.
  2. Keep only `/jobs/{job_id}/mark-relabeled`.
- **Acceptance Criteria:** Only one canonical endpoint exists in OpenAPI schema.
- **Verification:** Check OpenAPI schema generation via pytest.

---

### Ticket 10.2 — Migrate `narrative/router.py` to FastAPI `Depends()`

- **File:** `backend/app/narrative/router.py`
- **Problem:** Module-level singleton repositories bypass `app.dependency_overrides`, preventing mock testing.
- **Implementation:**
  1. Define dependency providers `get_job_repo()` and `get_narrative_repo()`.
  2. Inject in route signatures via `Annotated[..., Depends(...)]`.
- **Acceptance Criteria:** Router uses pure dependency injection; test overrides function properly.
- **Verification:** Run `pytest backend/tests/test_narrative_router.py`.

---

### Ticket 10.3 — Migrate `footnote/router.py` to FastAPI `Depends()`

- **File:** `backend/app/footnote/router.py`
- **Problem:** Singleton pattern used for `_default_job_repo`, `_default_schedule_repo`, `_default_lease_repo`.
- **Implementation:**
  1. Define dependency provider functions for each repository.
  2. Inject via `Depends()` in all endpoints.
- **Acceptance Criteria:** Zero module-level singleton repository instances in `footnote/router.py`.
- **Verification:** Run `pytest backend/tests/test_footnote_router.py`.

---

### Ticket 10.4 — Eliminate mutable globals in `excel_export/router.py`

- **File:** `backend/app/excel_export/router.py`
- **Problem:** `set_model_repository()` mutates module global `_model_repo`.
- **Implementation:**
  1. Replace with `get_model_repository()` dependency provider.
  2. Remove `set_model_repository()`.
- **Acceptance Criteria:** Repository resolved via dependency injection in route handler.
- **Verification:** Run `pytest backend/tests/test_excel_export_router.py`.

---

### Ticket 10.5 — Eliminate mutable globals in `drift/router.py`

- **File:** `backend/app/drift/router.py`
- **Problem:** Global setters `set_drift_repository()`, `set_job_repository()`, `set_review_repository()` mutate global state.
- **Implementation:**
  1. Replace with FastAPI `Depends()` providers.
- **Acceptance Criteria:** Clean dependency injection without global state mutation.
- **Verification:** Run `pytest backend/tests/test_drift_router.py`.

---

## Step 11 — P3 — Fix Health Check Logic Inversion

- **Objective:** Fix logic inversion where database connection failure mistakenly reports `db_ok = True`.
- **Priority:** P3

### Tickets

| Ticket ID | Title | Target File | Status |
|---|---|---|:---:|
| Ticket 11.1 | Invert `db_ok` exception handler logic to `False` | `backend/app/main.py` | `[ ]` |

---

### Ticket 11.1 — Invert `db_ok` exception handler logic to `False`

- **File:** `backend/app/main.py` (line 104)
- **Problem:** `except (sqlite3.Error, OSError): db_ok = True` reports DB as healthy when it crashes.
- **Implementation:**
  1. Change line 104 to `except (sqlite3.Error, OSError): db_ok = False`.
- **Acceptance Criteria:** Health check returns `db_ok = False` when database query raises an exception.
- **Verification:** Unit test with mocked failing SQLite connection.

---

## Step 12 — P3 — Normalize Audit Report Route Prefix

- **Objective:** Standardize audit report endpoint URLs to eliminate confusing duplicate `/api/` prefix.
- **Priority:** P3

### Tickets

| Ticket ID | Title | Target File | Status |
|---|---|---|:---:|
| Ticket 12.1 | Standardize audit report route to `/jobs/{id}/audit-report` | `backend/app/audit_report/router.py`, `frontend/src/components/audit/AuditTrailView.tsx` | `[ ]` |

---

### Ticket 12.1 — Standardize audit report route to `/jobs/{id}/audit-report`

- **Files:** `backend/app/audit_report/router.py`, `frontend/src/components/audit/AuditTrailView.tsx`
- **Problem:** Routes registered as `/api/jobs/{id}/audit-report` while all other routers use un-prefixed `/jobs/...`.
- **Implementation:**
  1. Remove duplicate prefix in router definition.
  2. Update frontend API client paths in `AuditTrailView.tsx`.
- **Acceptance Criteria:** Single canonical endpoint `/jobs/{id}/audit-report` documented and active.
- **Verification:** Test download endpoint with client request.

---

## Step 13 — P3 — Freeze the Evaluation Harness

- **Objective:** Prevent premature maintenance of evaluation infrastructure until ground-truth pilot corpus is established.
- **Priority:** P3

### Tickets

| Ticket ID | Title | Target File | Status |
|---|---|---|:---:|
| Ticket 13.1 | Add freeze notice and documentation to `eval/` | `eval/README.md` | `[ ]` |

---

### Ticket 13.1 — Add freeze notice and documentation to `eval/`

- **File:** `eval/README.md` (New File)
- **Problem:** ~80KB of evaluation harness code exists without any ground-truth corpus.
- **Implementation:**
  1. Add `eval/README.md` explaining freeze status per `docs/business_alignment.md` §1.1.
  2. Add note: "Frozen pending pilot client confirmation. Do not extend until real 10-K ground-truth annotations are provided."
- **Acceptance Criteria:** Eval module documentation clarifies harness is on standby.
- **Verification:** Verify file exists and is committed.

---

## Step 14 — P3 — Wire `footnote/` as Workflow Pack 2 and Defer `narrative/`

- **Objective:** Wire orphaned debt/lease schedule modules into production as Workflow Pack 2 (Capital Structure), and isolate narrative text diffing.
- **Priority:** P3

### Tickets

| Ticket ID | Title | Target File | Status |
|---|---|---|:---:|
| Ticket 14.1 | Wire `footnote/` extractor & debt schedule generator into pipeline | `backend/app/job_runner.py`, `backend/app/footnote/` | `[ ]` |
| Ticket 14.2 | Defer `narrative/` module from primary pipeline bundle | `backend/app/main.py`, `backend/app/job_runner.py` | `[ ]` |

---

### Ticket 14.1 — Wire `footnote/` extractor & debt schedule generator into pipeline

- **Files:** `backend/app/job_runner.py`, `backend/app/footnote/extractor.py`, `backend/app/excel_export/debt_schedule_generator.py`
- **Problem:** `footnote/` module has working debt and lease models but is never triggered by `job_runner.py`.
- **Implementation:**
  1. In `job_runner.py`, when `workflow_pack == "capital_structure"`, invoke `footnote/extractor.py`.
  2. Create clean 2-tab `debt_schedule_generator.py` (Debt Tranches & Spreads + Lease Waterfall) and trigger it upon model generation.
- **Acceptance Criteria:** Jobs uploaded under "Capital Structure & Debt Sizing" extract Note 8 debt schedules and generate Excel models.
- **Verification:** End-to-end integration test with debt disclosure fixture.

---

### Ticket 14.2 — Defer `narrative/` module from primary pipeline bundle

- **Files:** `backend/app/main.py`, `backend/app/job_runner.py`
- **Problem:** Narrative diffing distracts team bandwidth from core numeric spreading reliability.
- **Implementation:**
  1. Isolate `narrative/` routes under an optional router mount.
  2. Ensure `job_runner.py` does not invoke narrative parsing in numeric spreading workflows.
- **Acceptance Criteria:** Core numeric pipeline runs cleanly without dependencies on narrative diffing.
- **Verification:** Run test suite verifying independence of numeric workflows.
