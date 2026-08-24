# Footnote — Pipeline Scoping & Usability Corrections

**Handoff Document:** Instructions and executable tickets to eliminate review fatigue, implement target-metric-scoped table filtering, and enable 1-click deterministic Excel model generation.

---

## Architecture Context & Objective

The goal of Footnote is to automate financial statement reconciliation for junior investment bankers and private equity analysts. 

Currently, the extraction layer parses all tables across an entire 200+ page filing without scoping to the selected `target_metric` (e.g. *Adjusted EBITDA*), forcing the user to manually review hundreds of irrelevant items (Balance Sheet, PPE, Debt schedules, document titles).

These 5 numbered steps provide an exact implementation blueprint to:
1. Filter out structural noise and isolate Non-GAAP reconciliation tables.
2. Tag items by target metric relevance.
3. Triage the Review UI so analysts only see relevant candidates by default.
4. Provide a 1-click batch approval for high-confidence reconciliation items.
5. Generate a draft `.xlsx` model automatically during initial extraction.

---

# Step 1: Structural Table Relevance & Noise Suppression

Eliminate non-financial noise (section headers, table titles, unit declarations) and capture table-level contextual metadata to identify Non-GAAP reconciliation tables.

### Ticket 1.1 — Implement Noise Suppression Pre-Filter in Docling Parser
* **File:** [`backend/app/extraction/docling_parser.py`](file:///c:/footnote/backend/app/extraction/docling_parser.py)
* **Action:**
  1. Add a pre-filter function `_is_noise_cell(cell_text: str, row_idx: int, col_idx: int) -> bool` that identifies and drops non-data cells:
     - Cells matching SEC document boilerplate (e.g. `"Item 7."`, `"Table of Contents"`, `"PART I"`, `"Management's Discussion"`).
     - Currency and unit qualifier declarations (e.g. `"in millions, except per share amounts"`, `"(in thousands)"`, `"unaudited"`).
     - Cells containing zero numeric digits that are not valid structural headers.
  2. Skip emitting these noise items as data cells in `parse_pdf`.
* **Acceptance Criteria:** Document title banners and unit strings are suppressed from becoming data records.

### Ticket 1.2 — Capture Table Titles & Header Hierarchy
* **File:** [`backend/app/extraction/docling_parser.py`](file:///c:/footnote/backend/app/extraction/docling_parser.py) & [`backend/app/extraction/models.py`](file:///c:/footnote/backend/app/extraction/models.py)
* **Action:**
  1. In `docling_parser.py`, extract the enclosing table or section title (e.g., `"Reconciliation of Net Income to Adjusted EBITDA"`, `"Non-GAAP Financial Measures"`, `"Consolidated Balance Sheets"`).
  2. Attach `table_name: str` to `DoclingItem` and pass it through to `ExtractedRecord` metadata.
  3. Ensure the frozen 5-field schema (`value`, `label`, `page`, `bbox`, `source_file`) remains strictly preserved per CONSTITUTION §2.3.
* **Acceptance Criteria:** Every extracted line item carries its parent table title in its structural metadata.

### Ticket 1.3 — Update Extraction Unit Tests
* **File:** [`backend/tests/extraction/test_docling_parser.py`](file:///c:/footnote/backend/tests/extraction/test_docling_parser.py) & [`backend/tests/extraction/test_assembler.py`](file:///c:/footnote/backend/tests/extraction/test_assembler.py)
* **Action:**
  1. Add tests verifying that boilerplate text and unit declaration strings are filtered out.
  2. Add tests verifying table titles are correctly extracted and passed to downstream records.
* **Acceptance Criteria:** `pytest tests/extraction/` passes 100%.

---

# Step 2: Metric Relevance Tagging in Classification & Review

Tag extracted line items based on whether they belong to the Non-GAAP reconciliation bridge for the job's `target_metric`.

### Ticket 2.1 — Implement Target Metric Candidate Classifier
* **File:** [`backend/app/classification/normalizer.py`](file:///c:/footnote/backend/app/classification/normalizer.py)
* **Action:**
  1. In `normalize_records`, accept `target_metric: str` (default: `"Adjusted EBITDA"`).
  2. Classify each record as a **Target Metric Candidate** (`is_target_metric_candidate: bool = True`) if:
     - The item originated from a table whose title matches the target metric (e.g. contains `"Adjusted EBITDA"`, `"Non-GAAP"`, or `"Reconciliation"`), OR
     - The item's normalized label or raw label matches the seed taxonomy reconciliation components (e.g. Net Income, Stock-Based Compensation, Depreciation & Amortization, Restructuring, Impairment, Acquisition Costs).
  3. Tag all other unrelated tables (Balance Sheet, Leases, PPE) with `is_target_metric_candidate: bool = False`.
* **Acceptance Criteria:** All line items belonging to the target reconciliation bridge are flagged as target metric candidates.

### Ticket 2.2 — Extend Review Repository with Metric Relevance Metadata
* **File:** [`backend/app/review/models.py`](file:///c:/footnote/backend/app/review/models.py) & [`backend/app/review/repository.py`](file:///c:/footnote/backend/app/review/repository.py)
* **Action:**
  1. Add optional fields to `ReviewItem`:
     - `is_target_metric_candidate: bool = True`
     - `table_name: str | None = None`
  2. In `ReviewRepository._from_classified_records` and `_from_scored_records`, populate `is_target_metric_candidate` and `table_name`.
  3. Persist these fields cleanly to `data/results/<job_id>_review.json`.
* **Acceptance Criteria:** Review items contain metric relevance tags for UI filtering.

### Ticket 2.3 — Test Metric Relevance Tagging
* **File:** [`backend/tests/classification/test_normalizer.py`](file:///c:/footnote/backend/tests/classification/test_normalizer.py) & [`backend/tests/review/test_repository.py`](file:///c:/footnote/backend/tests/review/test_repository.py)
* **Action:**
  1. Add unit tests asserting reconciliation items (SBC, D&A, Restructuring) receive `is_target_metric_candidate = True`.
  2. Add unit tests asserting balance sheet items receive `is_target_metric_candidate = False`.
* **Acceptance Criteria:** `pytest tests/classification/ tests/review/` passes.

---

# Step 3: Triaged, Scoped Review UI

Provide a focused, dynamic Review UI that defaults to the target metric bridge candidates regardless of item count, relegating unrelated filing tables to a secondary drawer.

### Ticket 3.1 — Add Scoped Filter Tabs in Review Page
* **File:** [`frontend/src/components/review/ReviewPage.tsx`](file:///c:/footnote/frontend/src/components/review/ReviewPage.tsx)
* **Action:**
  1. Add a filter tab bar above the item sidebar with 4 views:
     - 🟢 **Target Metric Bridge (Default):** Displays all items where `is_target_metric_candidate === true`. Handles any dynamic item count from the filing.
     - 🟡 **Needs Review:** Displays items across the document with status `needs_review`, `manual_required`, or `pending_taxonomy_confirmation`.
     - 🔵 **Confirmed / Locked:** Displays all currently locked items.
     - ⚪ **All Filing Tables:** Displays all extracted items across the document for comprehensive reference.
  2. Update the search/filter state so switching tabs filters the displayed list instantly.
* **Acceptance Criteria:** When the analyst opens Review UI, only the candidate items for the selected target metric are displayed by default.

### Ticket 3.2 — Add Table Grouping & Breadcrumb Headers in Item List
* **File:** [`frontend/src/components/review/ReviewPage.tsx`](file:///c:/footnote/frontend/src/components/review/ReviewPage.tsx) & [`frontend/src/components/review/ReviewPage.css`](file:///c:/footnote/frontend/src/components/review/ReviewPage.css)
* **Action:**
  1. Group review items visually by `table_name` when available.
  2. Render a distinct table header badge (e.g., *"Table: Non-GAAP Adjusted EBITDA Reconciliation"*) above each group.
  3. Highlight target metric candidate items with a distinct subtle left border accent.
* **Acceptance Criteria:** Extracted items are clearly grouped by source table rather than an unorganized flat list.

### Ticket 3.3 — Update Frontend Review Component Tests
* **File:** [`frontend/src/components/review/ReviewPage.test.tsx`](file:///c:/footnote/frontend/src/components/review/ReviewPage.test.tsx)
* **Action:**
  1. Add tests verifying the "Target Metric Bridge" tab is selected by default.
  2. Add tests verifying that items are filtered according to the selected tab.
* **Acceptance Criteria:** `npm test` passes with 0 failures.

---

# Step 4: One-Click "Approve Reconciliation" & Batch Confirmation

Allow analysts to approve and lock all high-confidence target metric candidate items in a single click, reducing manual clicks from hundreds to one.

### Ticket 4.1 — Implement Batch Confirmation API Endpoint
* **File:** [`backend/app/review/router.py`](file:///c:/footnote/backend/app/review/router.py) & [`backend/app/review/repository.py`](file:///c:/footnote/backend/app/review/repository.py)
* **Action:**
  1. Add endpoint `POST /review/{job_id}/confirm-batch` accepting an optional list of `item_ids: list[str] | None`.
  2. In `ReviewRepository.confirm_batch(job_id, item_ids)`:
     - If `item_ids` is provided, confirm and lock the specified items.
     - If `item_ids` is omitted/null, confirm and lock all items where `is_target_metric_candidate == True` and `status != 'extraction_error'`.
     - Automatically resolve taxonomy match status for recognized taxonomy strings.
     - Atomically save updated review items to `data/results/<job_id>_review.json`.
  3. Return the updated list of `ReviewItem`s.
* **Acceptance Criteria:** Calling `POST /review/{job_id}/confirm-batch` locks all target metric candidate items in one request.

### Ticket 4.2 — Add "Approve Bridge & Generate Model" Action in Review UI
* **File:** [`frontend/src/components/review/ReviewPage.tsx`](file:///c:/footnote/frontend/src/components/review/ReviewPage.tsx)
* **Action:**
  1. Add a primary action button in the Review header: **"Approve Reconciliation & Generate Model"**.
  2. On click:
     - Call `POST ${apiBase}/review/${jobId}/confirm-batch` to lock all candidate items.
     - Call `POST ${apiBase}/models/${jobId}/generate` to build the `.xlsx` workbook.
     - Display a success notification: *"Reconciliation approved — Excel model generated with N items"*.
  3. If low-confidence or unrecognized items exist in the bridge, show a brief prompt allowing the user to approve all or inspect flagged items first.
* **Acceptance Criteria:** Single-click approval locks all candidate items and produces the `.xlsx` model immediately.

### Ticket 4.3 — Add Batch Confirmation Integration Tests
* **File:** [`backend/tests/review/test_router.py`](file:///c:/footnote/backend/tests/review/test_router.py)
* **Action:**
  1. Test `POST /review/{job_id}/confirm-batch` with explicit IDs and default all-candidate mode.
  2. Verify that locked status is persisted and locked items cannot be overwritten.
* **Acceptance Criteria:** `pytest tests/review/` passes 100%.

---

# Step 5: Direct Initial Draft Model Generation & End-to-End Handshake

Ensure a valid draft Excel model is compiled automatically during the initial extraction pass so the user can immediately download the workbook upon upload completion.

### Ticket 5.1 — Auto-Compile Draft Model on Initial Extraction
* **File:** [`backend/app/job_runner.py`](file:///c:/footnote/backend/app/job_runner.py)
* **Action:**
  1. In `process_queued_job`, after classification and normalizer tagging:
     - Filter confirmed items belonging to `is_target_metric_candidate == True` (or high-confidence auto-accepted items).
     - If candidate items exist, construct the `FormulaTree` and call `generate_workbook`.
     - Save provenance records to `ModelRepository`.
  2. If zero items match initially, log generation as deferred pending review.
* **Acceptance Criteria:** Jobs with clean Non-GAAP reconciliation tables have a valid `.xlsx` workbook generated on initial extraction.

### Ticket 5.2 — Update Job Table with Model Download & Status Badges
* **File:** [`frontend/src/components/JobList.tsx`](file:///c:/footnote/frontend/src/components/JobList.tsx)
* **Action:**
  1. In `JobList.tsx`, for jobs in `done` status, render:
     - 📊 **Excel (.xlsx)** download button linking to `/models/${job.job_id}/download`.
     - 🔍 **Review** button to inspect/edit the extraction bridge.
     - 📑 **Audit PDF** button to export compliance report.
  2. Add visual indicator if the model is ready or awaiting review.
* **Acceptance Criteria:** User can download the `.xlsx` workbook directly from the upload queue.

### Ticket 5.3 — End-to-End Benchmark & Verification Test
* **File:** [`backend/tests/eval/test_e2e_benchmark.py`](file:///c:/footnote/backend/tests/eval/test_e2e_benchmark.py)
* **Action:**
  1. Write a complete end-to-end test against a real 10-K filing fixture:
     - Execute `POST /upload/jobs` with `target_metric: "Adjusted EBITDA"`.
     - Verify background runner completes extraction, tags reconciliation candidates, and creates `<job_id>_model.xlsx`.
     - Verify `POST /review/{job_id}/confirm-batch` updates review state.
     - Verify `GET /models/{job_id}/download` returns a valid `.xlsx` file containing valid formula strings (`=SUM(...)`, `=HYPERLINK(...)`).
     - Verify `GET /audit-report/{job_id}/pdf` produces a valid PDF.
* **Acceptance Criteria:** Full end-to-end test passes with 0 errors and validates all 5 pipeline features.

---

## Handoff Checklist for Executing Agent

- [ ] Execute Step 1 (Tickets 1.1 $\to$ 1.3) — Noise suppression and table context.
- [ ] Execute Step 2 (Tickets 2.1 $\to$ 2.3) — Metric relevance tagging.
- [ ] Execute Step 3 (Tickets 3.1 $\to$ 3.3) — Dynamic scoped Review UI.
- [ ] Execute Step 4 (Tickets 4.1 $\to$ 4.3) — 1-click batch approval and model compilation.
- [ ] Execute Step 5 (Tickets 5.1 $\to$ 5.3) — Initial draft generation and E2E verification.
- [ ] Run `mypy --strict` on all backend modules.
- [ ] Run `pytest` across all backend test suites.
- [ ] Run `npm test` across frontend suites.
