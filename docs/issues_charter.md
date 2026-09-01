# Footnote — Issues Implementation Charter

> **Source:** `issues.md` (2026-08-26 audit). This charter supersedes that file.  
> Each **Step** = one issue from the audit. Each **Ticket** = one atomic task implemented
> and tested in isolation. Tickets within a Step are ordered by dependency.

---

## Completion Status

> Update the checkboxes below as tickets are resolved. Steps 7, 10, and 14 are subsumed
> by Steps 3 and 1 respectively — they have no standalone tickets.

| Step | Description | Status |
|---|---|---|
| Step 1 | Fix PDF Highlight Positions (bbox wrong) | `[ ]` |
| Step 2 | Fix Audit PDF Download Always Failing | `[ ]` |
| Step 3 | Reduce Review Queue to Only Genuinely Uncertain Items | `[ ]` |
| Step 4 | Audit Trail Empty State: Actionable Path | `[ ]` |
| Step 5 | Warn User When PyMuPDF Fallback Is Used | `[ ]` |
| Step 6 | Improve Confidence Scoring with Document-Structure Context | `[ ]` |
| Step 7 | Fix `isFlagged` Filter | _(Covered by Step 3 Ticket 3.4)_ |
| Step 8 | Audit Trail Sheet Selector: Derive Dynamically | `[ ]` |
| Step 9 | Empty Flagged Tab: Add Generate Model Guidance | `[ ]` |
| Step 10 | Auto-Lock High-Confidence Taxonomy-Matched Items | _(Covered by Step 3 Ticket 3.1)_ |
| Step 11 | Formula Engine: Surface Failure Clearly | `[ ]` |
| Step 12 | Fix Review Item IDs: Content-Based Hash | `[ ]` |
| Step 13 | Fix Isolation Violation: audit_report imports excel_export | `[ ]` |
| Step 14 | Fix PyMuPDF Cell Index Off-By-One | _(Covered by Step 1 Ticket 1.1)_ |
| Step 15 | Standardize PDF Render Scale | `[ ]` |
| Step 16 | Fix Canvas Size Read Using clientWidth | `[ ]` |
| Step 17 | Add Extraction Progress Indicator | `[ ]` |
| Step 18 | Replace alert() with Inline Error State | `[ ]` |
| Step 19 | Validate Target Metric Against Document Content | `[ ]` |
| Step 20 | Make CORS Origin Configurable | `[ ]` |

---


## Step 1 — Fix PDF Highlight Positions (Issue 1: Bbox Wrong)

**Root cause summary:**
1. PyMuPDF fallback (`_parse_pdf_with_pymupdf`) assigns the entire *table* bbox to every cell instead of per-cell coordinates, because the flat-index formula (`row_idx * len(row) + col_idx`) starts at 1×1 instead of 0×0, skipping the actual first cell and falling out of bounds for all others.
2. Docling uses a **bottom-left origin** (PDF coordinate space, y=0 at bottom), while PyMuPDF's `page.rect` and the canvas both use a **top-left origin** (y=0 at top). The normalizer maps `y0 → y0_norm` directly, so vertical positions are inverted on-screen.

---

### Ticket 1.1 — Fix PyMuPDF fallback per-cell bbox indexing

**File:** `backend/app/extraction/docling_parser.py` — `_parse_pdf_with_pymupdf()`

**Change:** The loop iterates `row_idx` from `1` and `col_idx` from `1`, producing `flat_idx = row_idx * len(row) + col_idx`. This skips the `(0, 0)` position and overruns into wrong cells. Replace with `flat_idx = (row_idx - 1) * len(row) + (col_idx - 1)` to map to the actual data-cell position in `table.cells`. Also verify that `table.cells` is a flat list of `(x0, y0, x1, y1)` tuples before accessing by index.

**AC:** For a test PDF, each extracted value's bbox must match the coordinates of its cell, not the whole table rectangle.

---

### Ticket 1.2 — Add Y-axis inversion for Docling-native coordinates in normalizer

**File:** `backend/app/extraction/coordinate_normalizer.py` — `normalize_item_bbox()`

**Change:** Docling outputs `bbox.t` (top) and `bbox.b` (bottom) in bottom-left origin space (y increases upward). PyMuPDF's `page.rect.height` is in top-left space. After scaling, invert: `y0_screen = 1000.0 - y1_norm` and `y1_screen = 1000.0 - y0_norm`. Apply this inversion only when the source coordinates came from Docling (i.e., when `item.bbox.y0 < item.bbox.y1` after raw extraction — confirm by logging the raw vs. inverted values). Add a module-level docstring note clarifying which coordinate space each function expects.

**AC:** A known cell near the bottom of a PDF page must produce a `y0_norm` value close to `1000` (near the bottom of the 0–1000 space), not close to `0`.

---

### Ticket 1.3 — Add `parser_used` metadata field to `DoclingItem` and propagate to job result

**File:** `backend/app/extraction/models.py`, `backend/app/extraction/docling_parser.py`

**Change:** Add `parser_used: Literal["docling", "pymupdf"] = "docling"` to `DoclingItem`. Set `parser_used = "pymupdf"` on every item created in `_parse_pdf_with_pymupdf()`. This allows the normalizer and downstream stages to know which coordinate space applies, enabling the conditional inversion in Ticket 1.2 to be applied correctly based on actual parser used rather than heuristic.

**AC:** `docling_items` JSON written to disk has `parser_used` populated for every item.

---

### Ticket 1.4 — Write unit tests for both bbox paths with fixture data

**File:** `backend/tests/test_coordinate_normalizer.py` (new or extend existing)

**Change:** Write parametrized unit tests:
1. Docling path: given `y0=50, y1=100` on a 792pt-tall page, assert normalized `y0_norm ≈ 937` (inverted) and `y1_norm ≈ 937 - delta`.
2. PyMuPDF path: given top-left coordinates `y0=50, y1=100` on a 792pt-tall page, assert normalized `y0_norm ≈ 63` and `y1_norm ≈ 126`.
3. Per-cell flat_idx test: mock a 3-row × 4-col table, assert each cell receives the correct bbox from `table.cells`.

**AC:** All new tests pass with `pytest -x`.

---

## Step 2 — Fix Audit PDF Download Always Failing (Issue 2)

**Root cause summary:** The "Export Audit PDF" button in `AuditTrailView.tsx` always renders as an active `<a href>` link, regardless of `job.model_ready`. The backend correctly raises `ModelNotCompleteError` (HTTP 400) but the UI gives no pre-check or explanation, so users get an opaque download failure. The compiler's on-the-fly fallback also fails silently when no items are confirmed.

---

### Ticket 2.1 — Frontend: gate the Audit PDF button on `model_ready` job flag

**File:** `frontend/src/components/audit/AuditTrailView.tsx`

**Change:** Accept a `jobRecord: JobRecord` (or at minimum `modelReady: boolean`) prop. Change the "Export Audit PDF" `<a>` element to a `<button>` when `!modelReady`, rendering a tooltip: *"Generate a model first: go to Review and click 'Approve & Generate'"*. If `modelReady` is true, keep the `<a download>` link. Update `App.tsx` to pass the `JobRecord` when navigating to `AuditTrailView`.

**AC:** For a job where `model_ready = false`, the export button is visually disabled and shows the tooltip; for `model_ready = true`, it triggers a normal download.

---

### Ticket 2.2 — Frontend: add "Generate Model" CTA to the audit trail empty state

**File:** `frontend/src/components/audit/AuditTrailView.tsx` (lines 308–341 empty state banner)

**Change:** Extend the empty-state banner to include a clear 2-step instruction and a "Go to Review → Approve & Generate" button that calls `onReview(jobId)`. Change the banner copy from *"Model not yet generated"* to *"No model yet — go to Review, approve the reconciliation bridge items, then click 'Approve & Generate Complete Financial Model'"*.

**AC:** Users who land on audit trail before generating a model see an actionable path with a single button click to get back to review.

---

### Ticket 2.3 — Backend: add `/api/jobs/{job_id}/audit-report/status` polling to `AuditTrailView`

**File:** `frontend/src/components/audit/AuditTrailView.tsx`

**Change:** On mount (alongside the provenance records fetch), call `GET /api/jobs/{job_id}/audit-report/status`. Store `isReportReady: boolean`. Use this flag (in addition to `model_ready`) to decide whether the download button is active. If `!isReportReady`, display a subtle note: *"Report will be generated on first download request"*.

**AC:** After a model is generated, the export button activates without requiring a page reload.

---

### Ticket 2.4 — Backend: surface clear error when audit report generation fails mid-compilation

**File:** `backend/app/audit_report/service.py`, `backend/app/audit_report/router.py`

**Change:** Catch `ModelNotCompleteError` in `download_audit_report` and return HTTP 400 with a structured JSON body `{ "detail": "...", "hint": "Confirm at least one line item in the Review tab, then click Generate Model." }`. Log the specific failure reason (no provenance records vs. formula tree invalid vs. no confirmed items) at `WARNING` level with the job_id.

**AC:** A `curl` to `/api/jobs/{job_id}/audit-report` on a job with no model returns `{ "detail": "...", "hint": "..." }` rather than a generic 400 response.

---

## Step 3 — Reduce Review Queue to Only Genuinely Uncertain Items (Issue 3)

**Root cause summary:** Three compounding bugs: (A) `is_target_metric_candidate_item()` matches too broadly via keyword scan of raw labels; (B) auto-accepted + taxonomy-matched items are still emitted into the review list instead of being silently locked; (C) confidence scoring penalises simple flat labels even from clean reconciliation tables.

---

### Ticket 3.1 — Auto-lock items that are `auto_accepted` + `taxonomy_status == matched` during review initialization

**File:** `backend/app/review/repository.py` — `_from_classified_records()`

**Change:** In the classification → review conversion loop, add a guard: if `sr.confidence_band == ConfidenceBand.auto_accepted` AND `cr.taxonomy_status == TaxonomyStatus.matched`, set `status = ReviewStatus.locked` instead of `ReviewStatus.auto_accepted`. These items still appear in the `items` list (for completeness) but are pre-locked, keeping them off the analyst's radar. Update the `isFlagged` computation accordingly.

**AC:** A job where all reconciliation items score ≥ 0.95 and match taxonomy results in `0` items on the `Flagged` tab with an empty-state CTA to generate the model.

---

### Ticket 3.2 — Tighten `is_target_metric_candidate_item()` to require table-level reconciliation signal

**File:** `backend/app/classification/normalizer.py` — `is_target_metric_candidate_item()`

**Change:** The current logic returns `True` for any item whose label matches a reconciliation keyword, even from unrelated tables. Change the logic hierarchy:
1. **Explicit reconciliation table** (`is_reconciliation_candidate == True` from the parser): always `True`.
2. **Named target metric in table title** (`metric_lower in table_lower`): `True`.
3. **Keyword match on normalized label** — only count this if `is_reconciliation_candidate` is also `True` on the `ScoredRecord`. Remove the broad fallback `return not (table_name and ...)` at line 113.

Pass `record.is_reconciliation_candidate` (already on `ScoredRecord`) as the primary gate. This ensures only items the parser identified as reconciliation table members are considered candidates.

**AC:** Items from P&L, balance sheet, and footnote tables no longer appear as `is_target_metric_candidate` when the document has an explicit Non-GAAP reconciliation table.

---

### Ticket 3.3 — Improve confidence scoring for items from reconciliation-candidate tables

**File:** `backend/app/extraction/confidence.py` — `compute_confidence_score()`

**Change:** Add a new scoring signal: if the associated `NormalizedItem.is_reconciliation_candidate == True`, apply a `+0.15` bonus before clamping. This offsets the `-0.15` `missing_header_hierarchy` deduction that fires for simple flat labels commonly found in reconciliation tables (e.g., `"Stock-based compensation"` without a ` / ` separator). Update `score_record()` to accept and pass through the `is_reconciliation_candidate` flag to `compute_confidence_score`.

**AC:** Items from reconciliation tables with flat labels score ≥ 0.95 (auto_accepted) when they have no other confidence penalties. Items from non-reconciliation tables remain unaffected.

---

### Ticket 3.4 — Fix `isFlagged` frontend filter to use `confidence_band`, not raw score

**File:** `frontend/src/components/review/ReviewPage.tsx` (lines 97–103)

**Change:** Remove the `item.confidence_score < 0.95` condition from `isFlagged()`. Replace the full predicate with:

```ts
const isFlagged = (item: ReviewItem) =>
  item.status === 'needs_review' ||
  item.status === 'manual_required' ||
  item.status === 'extraction_error' ||
  item.status === 'pending_taxonomy_confirmation' ||
  item.status === 'flagged'
```

Items with `status === 'auto_accepted'` or `status === 'locked'` are never flagged. Update the `flaggedCount` computation to use this corrected predicate.

**AC:** The `Flagged` tab count equals the count of items with status in `{needs_review, manual_required, extraction_error, pending_taxonomy_confirmation, flagged}` only.

---

## Step 4 — Audit Trail Empty State: Provide Actionable Path Forward (Issue 4)

**Root cause summary:** When no provenance records exist, `AuditTrailView` shows a banner but the only action is "Go to Review Tab →". There is no explanation of what to do in the review tab, and no way to trigger model generation from the audit screen.

---

### Ticket 4.1 — Enrich audit trail empty state with step-by-step guidance

**File:** `frontend/src/components/audit/AuditTrailView.tsx` (empty-state card, lines 444–461)

**Change:** Replace the terse "No Model Generated" card with a numbered checklist:
1. "Go to the Review tab"
2. "Review any flagged items (if any)"
3. "Click 'Approve & Generate Complete Financial Model'"
4. "Return here to view the cell-level audit trail"

Include a prominent "Go to Review Tab →" button (already exists) and optionally a secondary "Refresh" button to re-poll provenance without leaving the page.

**AC:** A first-time user on the audit trail screen understands in under 10 seconds exactly what they need to do.

---

### Ticket 4.2 — Add "Refresh" button to audit trail that re-polls provenance without page reload

**File:** `frontend/src/components/audit/AuditTrailView.tsx`

**Change:** Extract the `fetchMetadataAndInitialChain` effect into a callable `loadProvenance()` function. Add a "↻ Refresh" button in the header that calls `loadProvenance()`. This allows users who have generated the model in the Review tab to switch back to Audit Trail and refresh without navigating away.

**AC:** After generating a model in the Review tab and switching to Audit Trail, clicking "Refresh" loads the provenance records without a full page reload.

---

## Step 5 — Warn User When PyMuPDF Fallback Is Used (Issue 5)

**Root cause summary:** Docling failures are caught and silently rerouted to PyMuPDF. Users see no indication that the lower-quality parser was used, which degrades highlight accuracy without any warning.

---

### Ticket 5.1 — Store `parser_used` on the `ExtractionSummary` and expose via API

**File:** `backend/app/extraction/models.py` (`ExtractionSummary`), `backend/app/extraction/flagger.py` (`create_extraction_summary`), `backend/app/job_runner.py`

**Change:** Add `parser_used: Literal["docling", "pymupdf", "mixed"] = "docling"` to `ExtractionSummary`. In `job_runner.py`, after `parse_pdf()` returns, compute `parser_used` by checking if any `DoclingItem` has `parser_used == "pymupdf"`. Pass this to `create_extraction_summary()`. The extraction summary is already written to disk; no new endpoint needed.

**AC:** `data/results/{job_id}_summary.json` contains `"parser_used": "pymupdf"` when the fallback was used.

---

### Ticket 5.2 — Surface a degraded-quality warning banner in the Review Page when PyMuPDF fallback was used

**File:** `backend/app/review/router.py` (add `parser_used` to `ReviewItemsResponse`), `frontend/src/components/review/ReviewPage.tsx`

**Change:** Extend `ReviewItemsResponse` with `parser_used: str | None = None`. Populate it from the stored `ExtractionSummary` in `get_review_items()`. In `ReviewPage.tsx`, after fetching items, if `data.parser_used === "pymupdf"` or `"mixed"`, render a dismissible amber warning banner: *"⚠ Extraction used PyMuPDF fallback — PDF highlights may be less accurate than usual."*

**AC:** For a job where Docling was unavailable, the review page shows the warning banner automatically on load.

---

## Step 6 — Improve Confidence Scoring with Document-Structure Context (Issue 6)

> **Note:** Ticket 3.3 from Step 3 already addresses the reconciliation table bonus. This step adds two further signals.

---

### Ticket 6.1 — Add numeric value signal to confidence scoring

**File:** `backend/app/extraction/confidence.py` — `compute_confidence_score()`

**Change:** Add Signal 4: if the value is a well-formed number (e.g., parses as `float` after stripping `$`, `,`, `(`, `)`, `%`), apply `+0.05` bonus. Financial table cells with clean numeric values are structurally reliable. Add `value_is_numeric` to the diagnostic flags list.

**AC:** A cell with value `"(123,456)"` (parenthetical negative) scores 0.05 higher than an identical cell with a non-numeric value.

---

### Ticket 6.2 — Add table-consistency signal: boost items when their neighbours are high-confidence

**File:** `backend/app/extraction/confidence.py` — `score_records()` (post-pass)

**Change:** After individual scoring, add a second pass: group scored records by `table_name`. If ≥ 70% of items in a table scored ≥ 0.80, boost all remaining items in that table by `+0.10` (clamped to 1.0). This captures the intuition that a well-structured table is consistently good. Log a debug message per table where the boost is applied.

**AC:** In a table where most cells score 0.85+, a cell that scored 0.78 gets boosted to 0.88, moving to `needs_review` if it was `manual_required`.

---

## Step 7 — Fix `isFlagged` Filter (Issue 7)

> **Covered by Ticket 3.4.** No additional tickets needed.

---

## Step 8 — Audit Trail Sheet Selector: Derive from Provenance Records (Issue 8)

**Root cause summary:** The sheet dropdown is hardcoded to `["Reconciliation", "Source_Inputs"]`. Other sheets from the multi-statement workbook (e.g., `Model_Summary`) are inaccessible via the lookup UI.

---

### Ticket 8.1 — Derive sheet options dynamically from loaded provenance records

**File:** `frontend/src/components/audit/AuditTrailView.tsx` (lines 358–367)

**Change:** Replace the hardcoded `<option>` elements with a derived set from `provenanceRecords`. After loading:

```ts
const availableSheets = [...new Set(provenanceRecords.map(r => r.sheet_name))].sort()
```

Render one `<option>` per unique sheet name. Default `selectedSheet` to the first sheet in the list (or `'Reconciliation'` if present). If `provenanceRecords` is empty, fall back to the two hardcoded options so the form remains usable.

**AC:** For a multi-statement workbook with sheets `[Reconciliation, Source_Inputs, Model_Summary]`, all three appear as selectable options in the dropdown.

---

## Step 9 — Empty Flagged Tab: Add "Generate Model" Next-Step Guidance (Issue 9)

**Root cause summary:** When the `Flagged` tab is empty (all items locked), the empty-state paragraph just says "All reconciliation items auto-accepted (confidence >= 95%). Ready to generate model." but there is no button to trigger model generation.

---

### Ticket 9.1 — Add "Generate Model" action button to the empty `Flagged` tab state

**File:** `frontend/src/components/review/ReviewPage.tsx` (lines 709–717)

**Change:** Extend the empty state for `activeTab === 'flagged'`:

```tsx
{activeTab === 'flagged' && (
  <div>
    <p>All items reviewed. Ready to generate the financial model.</p>
    <button onClick={() => void handleApproveBridgeAndGenerateModel()}>
      Approve & Generate Complete Financial Model (6 Tabs) →
    </button>
  </div>
)}
```

Use the existing `handleApproveBridgeAndGenerateModel` handler. This gives users a zero-friction path from "all reviewed" to "model generated".

**AC:** A user who has confirmed all items lands on the Flagged tab, sees an empty state with a generate button, and can generate the model without scrolling back to the header.

---

## Step 10 — Auto-Lock High-Confidence Taxonomy-Matched Items in Pipeline (Issue 10)

> **Covered by Ticket 3.1.** `_from_classified_records()` now pre-locks `auto_accepted + matched` items. No additional tickets needed.

---

## Step 11 — Formula Engine: Surface Model Generation Failure Clearly (Issue 11)

**Root cause summary:** When formula_inputs.nodes is empty (because nothing is auto-accepted), `model_ready` stays `False` but the job status shows `done` without explanation.

---

### Ticket 11.1 — Add `model_skip_reason` field to `JobRecord` and populate in job_runner

**File:** `backend/app/ingestion/models.py` (`JobRecord`), `backend/app/ingestion/repository.py`, `backend/app/job_runner.py`

**Change:** Add `model_skip_reason: str | None = None` to `JobRecord`. In `job_runner.py`, when `len(formula_inputs.nodes) == 0`, set `model_skip_reason = formula_inputs.error_message or "No auto-accepted or confirmed records available"`. When `comp_tree.is_valid == False`, set it to `comp_tree.error_message`. Pass the reason to `repo.update_job_status()` and persist it in `jobs.json`.

**AC:** A job where formula inputs are empty has `model_skip_reason` populated in the API response from `GET /upload/jobs`.

---

### Ticket 11.2 — Surface `model_skip_reason` in the `JobList` UI as a tooltip or inline note

**File:** `frontend/src/components/JobList.tsx`, `frontend/src/types/job.ts`

**Change:** Add `model_skip_reason?: string` to the `JobRecord` TypeScript type. In `JobList.tsx`, in the `StatusBadge` for `done + !modelReady`, render a `ⓘ` icon with a `title` attribute showing `model_skip_reason`. Example tooltip: *"No auto-accepted records — review and confirm items to generate model."*

**AC:** A user can hover over the "Awaiting Review" badge and see the exact reason the model wasn't auto-generated.

---

## Step 12 — Fix Review Item IDs: Use Content-Based Hash Instead of Loop Index (Issue 12)

**Root cause summary:** `id=f"{job_id}_{idx}"` creates fragile sequential IDs. If classification re-runs or record order shifts, audit trail cross-references break silently.

---

### Ticket 12.1 — Replace sequential index IDs with deterministic content-based IDs

**File:** `backend/app/review/repository.py` — `_from_classified_records()` and `_from_scored_records()`

**Change:** Replace `id=f"{job_id}_{idx}"` with a deterministic hash of stable record fields:

```python
import hashlib
def _make_review_id(job_id: str, source_file: str, page: int, bbox: dict) -> str:
    key = f"{job_id}:{source_file}:{page}:{bbox.get('x0',0):.0f}:{bbox.get('y0',0):.0f}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
```

Use `_make_review_id(job_id, er.source_file, er.page, er.bbox)` as the item ID. This ensures the same physical cell always gets the same ID regardless of list order.

**AC:** Re-running classification on the same document produces identical `id` values for the same cells, verified by comparing two runs of `_review.json`.

---

### Ticket 12.2 — Update audit trail resolver to use content-based ID matching

**File:** `backend/app/audit_trail/resolver.py` — `_resolve_record_chain()` (line 182)

**Change:** The resolver currently extracts the record index from `leaf_{record_index}_{slug}` (regex `r"^leaf_(\d+)_"`). After Ticket 12.1, review item IDs are no longer `{job_id}_{idx}`. Update the resolver to build a lookup `review_item_by_hash: dict[str, ReviewItem]` keyed by the same content-hash formula. Extract `source_file`, `page`, and `bbox` from the `leaf_record.target.selector` and compute the hash to find the matching review item.

**AC:** After re-classification, the audit trail still correctly resolves source chains and enriches them with live review status.

---

## Step 13 — Fix Isolation Violation: `audit_report` Imports `excel_export` (Issue 13)

**Root cause summary:** `audit_report/compiler.py` imports `generate_workbook` from `excel_export/generator.py`, violating CONSTITUTION §3.8/§3.10.

---

### Ticket 13.1 — Extract on-the-fly model generation into a shared `model_compilation_service.py`

**File:** `backend/app/model_compilation_service.py` (new file at app root level, same tier as `job_runner.py`)

**Change:** Move the on-the-fly model compilation logic from `audit_report/compiler.py` (lines 92–117) into a new pure-function:

```python
def try_compile_model_on_the_fly(
    job_id: str,
    review_items: list[ReviewItem] | None,
    classified_records: list[ClassifiedRecord] | None,
    data_dir: Path,
) -> list[W3CAnnotationRecord] | None:
```

This function imports from both `excel_export/` and `formula_engine/` — allowed at the app-root level, same as `job_runner.py`.

**AC:** `audit_report/compiler.py` no longer imports anything from `excel_export/`. All cross-layer orchestration lives in `model_compilation_service.py`.

---

### Ticket 13.2 — Update `audit_report/compiler.py` to call the new service

**File:** `backend/app/audit_report/compiler.py`

**Change:** Replace the inline on-the-fly compilation block (lines 92–117) with a call to `try_compile_model_on_the_fly(...)` imported from `app.model_compilation_service`. Remove the direct import of `app.excel_export.generator`.

**AC:** `ruff check backend/app/audit_report/` reports no import isolation violations. The `mypy --strict` type check passes.

---

## Step 14 — Fix PyMuPDF Cell Index Off-By-One (Issue 14)

> **Covered by Ticket 1.1.** The cell index fix is identical to Issue 1 Bug A. No additional tickets.

---

## Step 15 — Standardize PDF Render Scale Across Review and Audit Trail (Issue 15)

**Root cause summary:** `ReviewPage` uses scale `1.5` (default) and `AuditTrailView` uses scale `1.3`, causing inconsistent canvas dimensions and bbox pixel placement.

---

### Ticket 15.1 — Export a shared `PDF_RENDER_SCALE` constant from `renderer.ts`

**File:** `frontend/src/lib/pdf/renderer.ts`

**Change:** Add `export const PDF_RENDER_SCALE = 1.5` and use it as the default in `renderPage(... scale: number = PDF_RENDER_SCALE)`. Update `AuditTrailView.tsx` to import and use `PDF_RENDER_SCALE` from `renderer.ts` instead of the hardcoded `1.3`.

**AC:** Both `ReviewPage` and `AuditTrailView` render PDFs at the same scale. Bounding box highlights for the same item appear at the same pixel position in both views.

---

## Step 16 — Fix Canvas Size Read Using `clientWidth` (Issue 16)

**Root cause summary:** `canvasSize` falls back to `clientWidth`/`clientHeight`, which include CSS padding and may differ from the rendered canvas content area.

---

### Ticket 16.1 — Use `canvas.style.width` parsed as integer directly, fall back to `canvas.getBoundingClientRect()`

**File:** `frontend/src/components/review/ReviewPage.tsx` (lines 233–236), `frontend/src/components/audit/AuditTrailView.tsx` (lines 239–242)

**Change:** Replace both canvas size reads with:

```ts
const rect = canvasRef.current.getBoundingClientRect()
setCanvasSize({ width: Math.round(rect.width), height: Math.round(rect.height) })
```

`getBoundingClientRect()` returns the actual rendered content dimensions (matching CSS `style.width`/`style.height` set by `renderPage`) without padding or border offsets. Apply the same fix in both `ReviewPage` and `AuditTrailView`.

**AC:** `normalizeBboxToPixels` receives the exact same width/height values that `renderPage` set on `canvas.style`, ensuring 1:1 coordinate mapping.

---

## Step 17 — Add Extraction Progress Indicator (Issue 17)

**Root cause summary:** The job list shows `"Extracting"` status text with no progress granularity. For large PDFs, users wait with no feedback.

---

### Ticket 17.1 — Add a pulsing progress indicator to the `Extracting` status badge in `JobList`

**File:** `frontend/src/components/JobList.tsx`, `frontend/src/App.css`

**Change:** In `StatusBadge`, when `status === 'extracting'`, add a CSS `@keyframes` pulse animation to the badge element and prefix the text with an animated spinner character. Add a `title` attribute: `"Processing PDF — this may take 30–60 seconds for large documents"`. No backend changes needed.

**AC:** A job in `extracting` status shows a visually distinct animated badge, making it clear the system is working.

---

## Step 18 — Replace `alert()` with Inline Error State (Issue 18)

**Root cause summary:** `handleConfirm()` in `ReviewPage` uses `alert()` on error, which is blocking and inaccessible.

---

### Ticket 18.1 — Replace `alert()` with an inline `editError` state display in the review item action area

**File:** `frontend/src/components/review/ReviewPage.tsx` (line 333)

**Change:** Replace `alert(err ...)` with `setEditError(err instanceof Error ? err.message : 'Confirmation failed')`. The `editError` state is already rendered as an inline error element below the action buttons. This keeps error feedback in-context and non-blocking.

**AC:** Triggering a confirmation error displays an inline red error message in the item card, not a browser alert dialog.

---

## Step 19 — Validate Target Metric Against Document Content (Issue 19)

**Root cause summary:** If no target metric is selected, the pipeline defaults silently to `"Adjusted EBITDA"`. No feedback is given if the metric isn't found in the document.

---

### Ticket 19.1 — Detect and log when the target metric appears in zero extracted table titles

**File:** `backend/app/job_runner.py`

**Change:** After `parse_pdf()` returns `docling_items`, check: `metric_found = any(item.table_name and target_metric.lower() in (item.table_name or "").lower() for item in docling_items)`. If `not metric_found`, log `WARNING: "Target metric '{target_metric}' was not found in any extracted table title for job {job_id}."` and set a new flag `target_metric_found: bool` on the `ExtractionSummary`.

**AC:** For a document with no "Adjusted EBITDA" reconciliation table, `_summary.json` contains `"target_metric_found": false`.

---

### Ticket 19.2 — Surface a "metric not found" warning banner in the Review Page

**File:** `backend/app/review/router.py`, `frontend/src/components/review/ReviewPage.tsx`

**Change:** Include `target_metric_found: bool | None` in `ReviewItemsResponse` (read from the stored `ExtractionSummary`). In `ReviewPage.tsx`, if `data.target_metric_found === false`, render a dismissible amber warning: *"⚠ The target metric '{target_metric}' was not found in any table title. Items shown may not correspond to the intended reconciliation bridge."*

**AC:** For a mismatch between the selected metric and the document, the review page shows the warning on load; the warning is dismissible.

---

## Step 20 — Make CORS Origin Configurable (Issue 20)

**Root cause summary:** `allow_origins=["http://localhost:5173"]` is hardcoded. If Vite starts on a different port, all API calls fail with CORS errors.

---

### Ticket 20.1 — Read CORS allowed origins from an environment variable with a sensible default

**File:** `backend/app/main.py`

**Change:**

```python
import os
_cors_origins_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:5174")
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    ...
)
```

Document in the project `README.md` that `ALLOWED_ORIGINS` can be set as a comma-separated list of origins.

**AC:** Starting the backend with `ALLOWED_ORIGINS=http://localhost:3000` allows requests from port 3000 without code changes.

---

## Execution Order (Priority-Ranked)

| Priority | Step | Rationale |
|---|---|---|
| 1 | **Step 3** (Tickets 3.1, 3.2, 3.3, 3.4) | Biggest UX win — reduces review burden from 300+ to actionable queue |
| 2 | **Step 1** (Tickets 1.1, 1.2, 1.3, 1.4) | Core correctness — highlights are the primary spatial UI feature |
| 3 | **Step 2** (Tickets 2.1, 2.2, 2.3, 2.4) | Unblocks audit trail — currently broken for all users |
| 4 | **Step 6** (Tickets 6.1, 6.2) | Strengthens confidence scores, feeds Step 3 improvements |
| 5 | **Step 11** (Tickets 11.1, 11.2) | Surfaces silent pipeline failures explicitly |
| 6 | **Step 12** (Tickets 12.1, 12.2) | Prevents audit trail cross-ref breakage on re-run |
| 7 | **Step 4** (Tickets 4.1, 4.2) | UX polish on audit trail empty state |
| 8 | **Step 9** (Ticket 9.1) | Zero-friction path from review to model generation |
| 9 | **Step 13** (Tickets 13.1, 13.2) | Architecture hygiene — isolation violation |
| 10 | **Step 5** (Tickets 5.1, 5.2) | Transparency — parser fallback visibility |
| 11 | **Step 8** (Ticket 8.1) | Audit trail completeness for multi-statement workbooks |
| 12 | **Step 15** (Ticket 15.1) | Rendering consistency between views |
| 13 | **Step 16** (Ticket 16.1) | Bbox pixel accuracy fix |
| 14 | **Step 19** (Tickets 19.1, 19.2) | Target metric mismatch feedback |
| 15 | **Step 17** (Ticket 17.1) | UX polish — loading feedback |
| 16 | **Step 18** (Ticket 18.1) | Accessibility — remove alert() |
| 17 | **Step 20** (Ticket 20.1) | DevX — CORS portability |

> Steps 7, 10, 14 are subsumed by tickets in Steps 3 and 1 respectively — no standalone work needed.

---

*Total tickets: 34 across 20 steps. Each ticket is self-contained and can be implemented, reviewed, and tested independently.*
