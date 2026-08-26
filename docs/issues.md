# Footnote — End-to-End Issues Audit

> Diagnosed: 2026-08-26 | Scope: full stack (PDF parsing → extraction → classification → review UI → audit trail → audit report)

---

## 🔴 Critical / Broken Features

### 1. PDF Highlight Positions Are Wrong (Review & Audit Trail)

**Location:** `backend/app/extraction/docling_parser.py` → `_parse_pdf_with_pymupdf()` (lines 504–520), `backend/app/extraction/coordinate_normalizer.py`

**Root cause (two bugs, compound):**

- **Bug A — PyMuPDF fallback uses table-level bbox for every cell.** When Docling is unavailable/fails and PyMuPDF's fallback path runs, the bounding box assigned to each data cell defaults to `table.bbox` (the entire table rectangle), not the individual cell's coordinates. The `table.cells` fallback (`flat_idx = row_idx * len(row) + col_idx`) uses a flat index that does **not** account for the fact that `table.cells` in PyMuPDF is a list of `(x0, y0, x1, y1)` tuples indexed by cell position, so misaligned items get the whole-table bbox.
- **Bug B — Docling's native coordinate system uses a bottom-left origin (PDF-native), but PyMuPDF's page rect uses a top-left origin.** The `coordinate_normalizer.py` maps `y0 → y0_norm` directly without Y-axis inversion. When Docling returns `bbox.t` / `bbox.b`, the top (`t`) is actually a smaller Y value in Docling's space but a larger Y value in screen/canvas space. Result: items appear near the top of the canvas when they should be near the bottom, and vice versa.

**Effect:** Highlights cover the entire table rectangle or appear at wrong vertical positions — consistent with the reported "right page but shifted/covers whole table" behavior.

---

### 2. Audit PDF Download Fails or Returns an Error

**Location:** `backend/app/audit_report/router.py` → `download_audit_report()`, `backend/app/audit_report/compiler.py`

**Root cause(s):**

- **Dependency: model must be generated first.** The compiler raises `ModelNotCompleteError` if no provenance records exist. If the pipeline's Stage 7/8 (formula engine + Excel export) failed silently (e.g., no `auto_accepted` records, empty `formula_inputs.nodes`), there are no provenance records, so the audit report always errors with HTTP 400 — even for a completed job. The job runner sets `model_ready=False` but the UI's "Export Audit PDF" button (in `AuditTrailView.tsx` line 284–303) always renders the download link regardless of `model_ready` status, giving users the false impression it should work.
- **On-the-fly re-compilation path has silent gaps.** The compiler tries to regenerate the model on-the-fly (lines 92–117 in `compiler.py`) if provenance is absent, but only succeeds if at least one item is confirmed/locked. With 300+ items in review and no guidance to confirm them, users likely click "Export Audit PDF" before any items are confirmed, causing a guaranteed `ModelNotCompleteError`.
- **No user-visible pre-check.** The audit report status endpoint (`/api/jobs/{job_id}/audit-report/status`) exists but the frontend never polls it to disable or grey out the download button — it always shows as clickable.

---

### 3. Review Section Shows 300+ Items — Should Show Only Genuinely Uncertain Items

**Location:** `backend/app/review/repository.py` → `_from_classified_records()`, `backend/app/classification/normalizer.py` → `is_target_metric_candidate_item()`

**Root cause (three interacting issues):**

- **Issue A — Weak reconciliation candidate filtering.** `is_target_metric_candidate_item()` returns `True` for almost every item: any item whose raw label contains words like `"revenue"`, `"depreciation"`, `"ebit"`, `"net income"` etc. will be flagged as a target metric candidate, regardless of which table it comes from. This means items from P&L tables, footnotes, and segment tables all pass through as candidates.
- **Issue B — Auto-accepted + taxonomy-matched items still shown in review.** Items with `confidence_band == auto_accepted` AND `taxonomy_status == matched` are included in the review list. Per the intended UX, these should be silently auto-locked after the pipeline — they should never reach the analyst's review queue. Currently `_from_classified_records()` emits `ReviewStatus.auto_accepted` items into the list.
- **Issue C — Confidence scoring is too coarse / gives too many items a `needs_review` band.** The scoring engine (`confidence.py`) deducts 0.15 for `missing_header_hierarchy` (triggered when the label has no ` / ` separator). A very large share of PyMuPDF-extracted labels from tables with simple row/column structure will trigger this, landing them in `needs_review` (0.65–0.95) rather than `auto_accepted`.

**Effect:** An analyst is presented with 300+ items to verify when the reconciliation bridge itself typically contains far fewer line items. This defeats the product's core friction-reduction purpose.

---

## 🟡 Significant / Degraded Features

### 4. Audit Trail Cell Lookup Shows Empty "Model Not Yet Generated" With No Actionable Path Forward

**Location:** `frontend/src/components/audit/AuditTrailView.tsx` (lines 308–341)

The `AuditTrailView` fetches `/models/{jobId}/provenance` on mount. If the Excel model was never generated (because Stage 7/8 failed, see Issue 2), this returns empty and renders the "Model not yet generated" banner. But the banner only links back to the Review Tab — there is no "Generate Model" button in the audit screen, and no explanation of why the model wasn't built.

---

### 5. PyMuPDF Fallback Is Used Silently Without Warning the User

**Location:** `backend/app/extraction/docling_parser.py` (lines 254–260)

Docling failures silently fall back to PyMuPDF with only a server-side log message. If Docling is unavailable (not installed, timeout, etc.), the entire extraction runs on the fallback path — which has worse bbox accuracy (Issue 1). Users have no UI indication that extraction quality may be degraded.

---

### 6. Confidence Scoring Does Not Use Document-Structure Context

**Location:** `backend/app/extraction/confidence.py`

The confidence scorer only uses three local signals: missing header hierarchy, label ambiguity, and footnote markers. It never considers whether the item comes from a reconciliation/non-GAAP table (which is structurally reliable), whether the value is numeric and well-formed, or whether multiple items in the same table share consistent structure. Items from clean, well-structured reconciliation tables are penalized 0.15 points simply for lacking a ` / ` separator in their label, pushing them into `needs_review` and inflating the review queue (Issue 3).

---

### 7. Review Page `isFlagged` Filter Is Overly Broad

**Location:** `frontend/src/components/review/ReviewPage.tsx` (lines 97–103)

```ts
item.confidence_score < 0.95   // catches auto_accepted items with score 0.85–0.94
```

The last condition in `isFlagged()` flags any item with a score just below 0.95, even if its `status` is already `auto_accepted`. This leaks items into the `Flagged` tab that should not require review. The filter should use `confidence_band` or `status`, not the raw numeric score.

---

### 8. Audit Trail Sheet Selector Is Hardcoded to Only Two Sheets

**Location:** `frontend/src/components/audit/AuditTrailView.tsx` (lines 365–367)

The dropdown only offers `Reconciliation` and `Source_Inputs`. The Excel model can contain additional sheets (e.g., `Model_Summary`). If a provenance record belongs to another sheet, the cell lookup form cannot target it, so parts of the audit trail are inaccessible through the UI.

---

### 9. After All Items Are Locked, Review Page Shows Empty Flagged Tab With No Next-Step Guidance

**Location:** `frontend/src/components/review/ReviewPage.tsx`

After all items are confirmed/locked, the default `Flagged` tab shows 0 items with no empty-state message directing the user to generate the model. There is no "Generate Model" prompt on the empty state, leaving users stranded.

---

### 10. No Auto-Lock After Pipeline for High-Confidence, Taxonomy-Matched Items

**Location:** `backend/app/job_runner.py` (post-classification stage), `backend/app/review/repository.py`

After classification, items that are both `auto_accepted` and `taxonomy_status == matched` are not automatically locked. They remain in `auto_accepted` review state and still appear in the analyst's queue. These should be silently auto-locked by the pipeline — only items with genuine uncertainty should ever surface for analyst review.

---

### 11. Formula Engine Silently Skips Model Generation If No Records Are Auto-Accepted

**Location:** `backend/app/job_runner.py` (lines 169–211)

The formula tree is only built from `auto_accepted` or confirmed records. If confidence scoring leaves most records in `needs_review` (common, given Issue 6), `formula_inputs.nodes` will be empty, the Excel model won't be generated, and `model_ready` will be `False`. The job completes as `done` but with no model — yet the UI shows `done` without prominently surfacing the absence of a model.

---

### 12. Review Item IDs Use Sequential Loop Index, Breaking Audit Trail Cross-References on Re-Run

**Location:** `backend/app/review/repository.py` (line 428)

```python
id=f"{job_id}_{idx}",
```

Review item IDs are assigned as `{job_id}_{sequential_index}`. If classification is re-run or the list is reordered, IDs change. The audit trail resolver (`resolver.py` line 182) extracts the record index from `leaf_{record_index}_{slug}` to look up review items — if these indices desync, the resolver silently returns `[missing]` components for valid records.

---

### 13. Audit Report Compiler Imports `generate_workbook` from `excel_export` — Isolation Violation

**Location:** `backend/app/audit_report/compiler.py` (line 31)

```python
from app.excel_export.generator import generate_workbook
```

CONSTITUTION §3.8 / §3.10 prohibits `audit_report/` from importing `excel_export/`. This creates a dependency cycle risk and violates the isolation constraint, which also makes this module harder to unit-test in isolation.

---

### 14. PyMuPDF Fallback Bbox Uses Incorrect Cell Index Calculation (Off-By-One)

**Location:** `backend/app/extraction/docling_parser.py` (lines 511–520)

```python
flat_idx = row_idx * len(row) + col_idx
```

`row_idx` starts at `1` (from `range(1, len(extracted))`) and `col_idx` starts at `1` as well. The flat index formula skips the header row and first column, causing systematic misalignment between the extracted value and the bbox retrieved from `table.cells`. Most cells will silently fall back to the whole-table bbox.

---

### 15. Scale Mismatch Between ReviewPage (1.5×) and AuditTrailView (1.3×) PDF Renderers

**Location:** `frontend/src/components/review/ReviewPage.tsx` (line 229) vs `frontend/src/components/audit/AuditTrailView.tsx` (line 235)

`ReviewPage` renders at scale `1.5` (default); `AuditTrailView` renders at `1.3`. Canvas dimensions differ between the two views for the same PDF, causing bounding box pixel calculations to land at different positions. Highlights will be visually inconsistent for the same item when viewed across the two screens.

---

### 16. `canvasSize` Falls Back to `clientWidth`, Which May Include CSS Padding

**Location:** `frontend/src/components/review/ReviewPage.tsx` (lines 234–236)

```tsx
const width = parseInt(canvasRef.current.style.width, 10) || canvasRef.current.clientWidth
```

If `style.width` parses to `NaN`, `clientWidth` is used as a fallback — but `clientWidth` includes padding/borders and differs from the actual rendered canvas content width. This produces a ratio mismatch in `normalizeBboxToPixels`, causing highlights to shift slightly off-target.

---

## 🟢 Minor / UX Issues

### 17. No Loading Indicator During Long Extraction Jobs

**Location:** `frontend/src/components/JobList.tsx`

The job list displays `"extracting"` status text but provides no progress bar, step label, or ETA. For large PDFs, extraction can take 30+ seconds with no user feedback.

---

### 18. `alert()` Used for Confirmation Error Messages

**Location:** `frontend/src/components/review/ReviewPage.tsx` (line 333)

```tsx
alert(err instanceof Error ? err.message : 'Confirmation failed')
```

The native browser `alert()` is blocking, unstyled, and inaccessible. This should be replaced with an inline error banner consistent with the rest of the review UI.

---

### 19. Default Target Metric Silently Applied With No Validation Against Document Content

**Location:** `backend/app/job_runner.py` (line 85)

```python
target_metric = job.target_metric or "Adjusted EBITDA"
```

If a user submits without selecting a target metric, the pipeline silently defaults to `"Adjusted EBITDA"`. There is no warning if this metric does not appear in the document, nor any feedback in the UI about which metric was used for filtering.

---

### 20. CORS Origin Hardcoded — Breaks If Vite Runs on a Non-Default Port

**Location:** `backend/app/main.py` (line 40)

```python
allow_origins=["http://localhost:5173"],
```

If the Vite dev server starts on a different port (due to port conflict), all API calls are silently blocked by CORS. The origin should be configurable via an environment variable (e.g., `ALLOWED_ORIGINS`).

---

*End of issues — 20 items catalogued: 3 critical, 9 significant, 8 minor/UX*
