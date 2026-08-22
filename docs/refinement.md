# Footnote -- Refinement Roadmap

**Produced by:** Strategic diagnosis + grill-me interview session (2026-08-20).
**Execution model:** Each ticket is implemented one at a time using the standard 7-step development loop from handoff.md (Explore -> Plan -> Implement -> Verify -> Review -> Test -> Commit). No phase begins until every ticket in the prior phase passes mypy --strict, pytest, npm test, ruff, and eslint.

---

## Resolved Architecture Decisions

| Decision | Answer |
|---|---|
| Multi-year xlsx layout | Option B -- one sheet, fiscal years as columns, line items as rows (standard IB model format) |
| Company identity / grouping | Option A -- user manually groups filings. The upload form gets an Assign to Company dropdown; user selects an existing company or types a new name to create one on the fly |
| Filing year source | User selects/types fiscal year (e.g. 2023) when uploading, alongside target metric. New field on JobRecord. |
| Template support | Footnote-formatted model only. User manually incorporates. openpyxl migration acceptable if required but not triggered until templates are in scope. |
| Multi-year model trigger | Manual -- a Build Multi-Year Model button on the company view, appears once 2+ jobs are done |
| Excel output structure | Source_Inputs sheet: plain numeric values + cell comments with provenance. Reconciliation sheet: =Source_Inputs!F{row} cross-sheet references per line item, =SUM(C4:C12) for the total row. No =HYPERLINK wrappers on value cells. |
| Phase execution order | Strictly sequential. P0 fully done -> P1 fully done -> P2. |

---

## Phase 0 -- Unblock the Core Loop

Goal: An uploaded PDF produces a downloadable .xlsx workbook. Nothing else matters until this works end-to-end.

---

### Step 0.1 -- Fix Model Generation Gating

Problem: read_formula_inputs drops all unconfirmed records, so build_formula_tree receives an empty batch. The workbook is never written. The job silently reports done with no model.

#### Ticket 0.1.1 -- Auto-accept high-confidence records without requiring explicit review confirmation
* File: backend/app/formula_engine/reader.py
* Action:
  1. In read_formula_inputs(classified_records), change the inclusion predicate: include any record where confidence_band == ConfidenceBand.auto_accepted OR is_confirmed == True, regardless of taxonomy confirmation status.
  2. For auto-accepted records with normalized_label is None, fall back to using the raw label field from the ExtractedRecord as the normalized label. Log a DEBUG entry for each such passthrough.
  3. Preserve the existing strict path for explicitly confirmed records.
* Acceptance Criteria: Calling read_formula_inputs with a list of auto-accepted records (confidence >= 0.95, not explicitly confirmed) returns a non-empty FormulaInputBatch with error_message=None.

#### Ticket 0.1.2 -- Add review-to-formula adapter for confirmed/locked review items
* File: backend/app/formula_engine/reader.py
* Action:
  1. Add a new pure function read_formula_inputs_from_review(items: list[ReviewItem]) -> FormulaInputBatch.
  2. Include all ReviewItems where status == ReviewStatus.locked. Skip extraction_error items.
  3. Use item.normalized_label or item.label as the normalized_label for each FormulaInputNode.
  4. Enforce the same 0-1000 coordinate bounds and non-empty label validation as the existing reader (CONSTITUTION 1.4).
* Acceptance Criteria: Confirmed ReviewItems correctly convert to a valid, non-empty FormulaInputBatch.

#### Ticket 0.1.3 -- Update formula engine unit tests
* File: backend/tests/formula_engine/test_reader.py
* Action:
  1. Test: read_formula_inputs with all auto-accepted, non-confirmed records returns a non-empty batch.
  2. Test: read_formula_inputs with all pending_taxonomy_confirmation records at auto-accept confidence returns non-empty batch using raw labels.
  3. Test: read_formula_inputs_from_review with locked ReviewItems returns a valid batch.
  4. Test: read_formula_inputs_from_review with zero locked items returns empty batch with error message.
* Acceptance Criteria: pytest tests/formula_engine/ passes 100%.

---

### Step 0.2 -- Add Model Generation API Endpoint

Problem: After review confirmation, there is no API endpoint to trigger xlsx generation from locked review items.

#### Ticket 0.2.1 -- Implement POST /models/{job_id}/generate endpoint
* File: backend/app/excel_export/router.py
* Action:
  1. Add endpoint POST /models/{job_id}/generate returning WorkbookGenerationResult.
  2. Load the job via JobRepository.get_job(job_id). Return 404 if not found.
  3. If review items exist: convert via read_formula_inputs_from_review. Otherwise fall back to ClassificationRepository and use read_formula_inputs.
  4. Call build_formula_tree(batch, target_metric=job.target_metric).
  5. Call generate_workbook(tree, job_id=job_id, output_dir=repo.data_dir).
  6. Save provenance records via ModelRepository.
  7. Return WorkbookGenerationResult (HTTP 200 on success; HTTP 400 with error_detail if no confirmed records exist).
* Acceptance Criteria: POST /models/{job_id}/generate creates data/models/{job_id}_model.xlsx when locked review items exist.

#### Ticket 0.2.2 -- Implement GET /models/{job_id}/download endpoint
* File: backend/app/excel_export/router.py
* Action:
  1. Add endpoint GET /models/{job_id}/download.
  2. Resolve path via ModelRepository.get_workbook_path(job_id). Return 404 if no file exists.
  3. Return FileResponse with media_type application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.
* Acceptance Criteria: A valid .xlsx file is served and opens in Excel without errors.

#### Ticket 0.2.3 -- Add model generation and download integration tests
* File: backend/tests/excel_export/test_router.py
* Action:
  1. Test POST generate with mock locked ReviewItems: assert file created, is_success=True.
  2. Test POST generate with zero locked items: assert 400 with error_detail.
  3. Test GET download with existing model: assert 200, correct content-type.
  4. Test GET download with no model: assert 404.
* Acceptance Criteria: pytest tests/excel_export/ passes 100%.

---

### Step 0.3 -- Wire Model Download into Frontend Job List

#### Ticket 0.3.1 -- Add Excel download button for completed jobs in JobList.tsx
* File: frontend/src/components/JobList.tsx
* Action:
  1. For jobs with status === done, render an Excel (.xlsx) download anchor linking to /models//download with download attribute.
  2. Style with IB green (#15803d background, white text) per CONSTITUTION 2.5.
  3. Place as leftmost action button. Absent for non-done jobs.
* Acceptance Criteria: A completed job row shows an Excel download link.

#### Ticket 0.3.2 -- Add Generate Excel Model action button in ReviewPage.tsx
* File: frontend/src/components/review/ReviewPage.tsx
* Action:
  1. Compute lockedCount = items.filter(i => i.status === locked).length.
  2. Add primary button Generate Excel Model in review header, enabled when lockedCount > 0.
  3. On click: POST /models//generate.
  4. On success: show banner with direct download link. On failure: show error_detail inline.
* Acceptance Criteria: Clicking Generate Excel Model after confirming items produces xlsx and presents download link.

#### Ticket 0.3.3 -- Update frontend component tests
* Files: frontend/src/components/JobList.test.tsx, frontend/src/components/review/ReviewPage.test.tsx
* Action:
  1. Test done job row renders anchor with href matching /models/{job_id}/download.
  2. Test non-done job row does NOT render Excel download anchor.
  3. Test Generate Excel Model button present when lockedCount > 0, absent when 0.
  4. Test clicking button dispatches POST /models/{jobId}/generate.
* Acceptance Criteria: npm test passes 0 failures.

---

### Step 0.4 -- Auto-Generate Draft Model in Job Runner

#### Ticket 0.4.1 -- Auto-generate draft xlsx from auto-accepted items after classification
* File: backend/app/job_runner.py
* Action:
  1. After Stage 6 (classification), call read_formula_inputs(classified_records) using updated logic from Ticket 0.1.1.
  2. If batch non-empty: build formula tree and generate workbook.
  3. If batch empty: log WARNING, do NOT mark job as failed.
  4. Add model_ready: bool = False to JobRecord. Set True when workbook generated successfully.
* Acceptance Criteria: Job with clean auto-accepted items has .xlsx when runner completes.

#### Ticket 0.4.2 -- Propagate model_ready to frontend via GET /upload/jobs response
* Files: backend/app/ingestion/models.py, backend/app/ingestion/repository.py
* Action:
  1. Add model_ready: bool = False to JobRecord.
  2. Update JobRepository to persist and retrieve this field.
  3. In job_runner.py: call repo.update_job_status(job_id, JobStatus.done, model_ready=generation_result.is_success).
* Acceptance Criteria: GET /upload/jobs includes model_ready: true for jobs with workbooks generated.

#### Ticket 0.4.3 -- Show Model Ready vs Awaiting Review badge in JobList.tsx
* Files: frontend/src/components/JobList.tsx, frontend/src/types/job.ts
* Action:
  1. Add model_ready: boolean to JobRecord TypeScript type.
  2. done + model_ready=true: green Model Ready badge + Excel download button.
  3. done + model_ready=false: amber Awaiting Review badge + Review button only.
* Acceptance Criteria: Job rows accurately reflect whether model is downloadable.

#### Ticket 0.4.4 -- Add unit and integration tests for job runner draft generation
* File: backend/tests/test_job_runner.py
* Action:
  1. Test: job runner with mock auto-accepted records produces model_ready=True on JobRecord.
  2. Test: job runner with zero auto-accepted records produces model_ready=False and no .xlsx file.
  3. Test: model_ready field survives a JobRepository round-trip.
* Acceptance Criteria: pytest tests/ passes 100%.

---

## Phase 1 -- Business Model Alignment

Goal: The tool does the right thing by default. Upload -> reconciliation-only extraction -> auto-generate -> download. Review is optional for flagged items only.

IMPORTANT: Phase 1 begins only after all Phase 0 tickets are merged and verified.

---

### Step 1.1 -- Filter to Reconciliation Tables Before Classification

Problem: Every extracted item from all 50+ tables is dispatched to Groq. The 1,000 RPD free-tier cap is wasted on balance sheet rows the user never sees.

#### Ticket 1.1.1 -- Add deterministic reconciliation table detector
* File: backend/app/extraction/docling_parser.py
* Action:
  1. Add pure function _is_reconciliation_table(table_title: str, target_metric: str) -> bool. Returns True if title contains target_metric (case-insensitive) OR any of: non-gaap, reconciliation, adjusted, non gaap, bridge.
  2. Add is_reconciliation_candidate: bool = False to DoclingItem model.
  3. Set flag on each item based on its parent table title. Tables that do not match are still extracted but marked False.
* Acceptance Criteria: DoclingItem objects from balance sheet tables marked is_reconciliation_candidate=False. Items from reconciliation tables marked True.

#### Ticket 1.1.2 -- Propagate is_reconciliation_candidate through extraction pipeline
* Files: backend/app/extraction/models.py, backend/app/extraction/assembler.py, backend/app/extraction/confidence.py
* Action:
  1. Add is_reconciliation_candidate: bool = False to ExtractedRecord and ScoredRecord (metadata field, not one of the frozen 5 schema fields -- CONSTITUTION 2.3 unchanged).
  2. Propagate the flag: DoclingItem -> ExtractedRecord -> ScoredRecord.
* Acceptance Criteria: ScoredRecord carries is_reconciliation_candidate correctly.

#### Ticket 1.1.3 -- Filter to reconciliation candidates before Groq dispatch
* File: backend/app/job_runner.py
* Action:
  1. Between Stage 5 (summary) and Stage 6 (classification), filter scored_records to only is_reconciliation_candidate == True.
  2. Store filtered-out count in the extraction summary.
  3. Pass filtered list to dispatch_records_to_classifier. Full list remains persisted in data/results/{job_id}_scored.json unchanged.
* Acceptance Criteria: Groq API is called only for reconciliation table items.

#### Ticket 1.1.4 -- Update extraction and classification unit tests
* Files: backend/tests/extraction/test_docling_parser.py, backend/tests/classification/test_dispatcher.py
* Action:
  1. Test: reconciliation table title -> is_reconciliation_candidate=True.
  2. Test: balance sheet title -> is_reconciliation_candidate=False.
  3. Test: dispatcher receives only is_reconciliation_candidate=True records after job runner filter.
* Acceptance Criteria: pytest tests/extraction/ tests/classification/ passes 100%.

---

### Step 1.2 -- Scope Review UI to Flagged Reconciliation Items Only

Problem: The review UI shows all extracted items. Out-of-scope items should not appear. Only reconciliation items with confidence < 0.95 belong in the review queue.

#### Ticket 1.2.1 -- Filter review items in ReviewRepository to reconciliation candidates
* File: backend/app/review/repository.py
* Action:
  1. In _from_classified_records: skip items where is_reconciliation_candidate == False.
  2. In _from_scored_records: same.
  3. Auto-accepted reconciliation items are still created as ReviewItems with status=ReviewStatus.auto_accepted.
* Acceptance Criteria: get_review_items returns only reconciliation-candidate items. Filing with 300 extracted items produces review list of <= 20 items.

#### Ticket 1.2.2 -- Simplify Review UI to two tabs: Flagged (default) and All Reconciliation Items
* File: frontend/src/components/review/ReviewPage.tsx
* Action:
  1. Flagged (default): items with status in needs_review, manual_required, pending_taxonomy_confirmation.
  2. All Reconciliation Items: all items (auto-accepted + flagged).
  3. Remove All Filing Tables tab entirely.
  4. Display dynamic count badge per tab: Flagged (3), All Reconciliation Items (12).
* Acceptance Criteria: Opening Review UI by default shows only flagged reconciliation items.

#### Ticket 1.2.3 -- Add Approve All and Generate Model one-click action
* Files: frontend/src/components/review/ReviewPage.tsx, backend/app/review/router.py
* Action:
  1. Add primary header button Approve All & Generate Model.
  2. On click: POST /review//confirm-batch (confirms all target candidates), then POST /models//generate.
  3. On success: show banner with download link.
  4. Verify POST /review/{job_id}/confirm-batch works with target_candidates_only=True.
* Acceptance Criteria: One click approves all flagged reconciliation items and produces downloadable xlsx.

#### Ticket 1.2.4 -- Update review frontend tests
* File: frontend/src/components/review/ReviewPage.test.tsx
* Action:
  1. Test Flagged tab is default active.
  2. Test switching to All Reconciliation Items shows all items.
  3. Test Approve All & Generate Model present when flaggedCount > 0.
  4. Test button dispatches confirm-batch then generate in sequence.
* Acceptance Criteria: npm test passes 0 failures.

---

### Step 1.3 -- Redesign Excel Output to Banker-Editable Format

Problem: Reconciliation sheet uses =HYPERLINK(url, Source_Inputs!F{row}) -- fragile wrappers. Source cells use write_url wrapping values in hyperlinks. Neither produces plain-editable Excel output.

Agreed output design:
- Source_Inputs sheet: plain numeric values (blue font = hardcode per CONSTITUTION 2.5) + cell comments with provenance text. No hyperlink on source cells.
- Reconciliation sheet: =Source_Inputs!F{row} cross-sheet reference per line item (green font). Total row: =SUM(C{start}:C{end}) (black bold, double-underline).

#### Ticket 1.3.1 -- Rewrite Source_Inputs sheet to use plain values + comments
* File: backend/app/excel_export/generator.py
* Action:
  1. Replace ws_inputs.write_url() with ws_inputs.write_number(row_idx, val_col, parsed_num, val_format) for numeric values, or ws_inputs.write() for non-parseable strings.
  2. Keep ws_inputs.write_comment(). Comment text: Source: {source_file} / Page: {page} / BBox: ({x0}, {y0}) -> ({x1}, {y1}) / Label: {label}.
  3. Remove all hyperlink URL generation for source input cells.
  4. Keep fmt_hardcode_num (blue) for is_hardcode=True, fmt_source_num (black) for others.
* Acceptance Criteria: Source_Inputs!F{row} contains plain numeric value (not formula), with provenance comment.

#### Ticket 1.3.2 -- Rewrite Reconciliation sheet to use cross-sheet refs and plain SUM
* File: backend/app/excel_export/generator.py
* Action:
  1. For each leaf node, write =Source_Inputs!F{input_row + 1} as formula using write_formula, styled with fmt_sheet_link (green).
  2. Track contiguous range of component cells. Total row: =SUM(C{start}:C{end}), styled with fmt_total (bold double-underline).
  3. For aggregate groups, write sub-total =SUM(C{sub_start}:C{sub_end}) before the next group.
  4. Keep write_comment on every cell. Remove all =HYPERLINK wrappers.
  5. W3CAnnotationRecord objects still generated and persisted to data/results/{job_id}_provenance.json.
* Acceptance Criteria: Total row contains =SUM(C4:C12) format. Zero formula errors in Excel. Banker can insert a row without breaking references.

#### Ticket 1.3.3 -- Update Excel generator unit tests
* File: backend/tests/excel_export/test_generator.py
* Action:
  1. Test source cell has is_formula=False in cell_refs.
  2. Test Reconciliation line item cells contain =Source_Inputs!F{row} (not =HYPERLINK).
  3. Test total row formula is =SUM(C{start}:C{end}) format.
  4. Test provenance records are still generated with the new structure.
* Acceptance Criteria: pytest tests/excel_export/ passes 100%.

---

### Step 1.4 -- Fix Audit Trail Empty State

#### Ticket 1.4.1 -- Add pre-generation guidance to AuditTrailView
* File: frontend/src/components/audit/AuditTrailView.tsx
* Action:
  1. When provenanceRecords.length === 0, display banner: No Excel model has been generated yet for this filing. Review and confirm extracted items to generate a model with full provenance.
  2. Add Go to Review button calling the onReview(jobId) prop.
* Acceptance Criteria: Opening Audit Trail before model generation shows helpful message with navigation button.

---

## Phase 2 -- Multi-Year Company Architecture

Goal: A banker can group multiple filings for one company and generate a single multi-year xlsx (line items as rows, fiscal years as columns).

IMPORTANT: Phase 2 begins only after all Phase 1 tickets are merged and verified.

---

### Step 2.1 -- Introduce Company Data Model

#### Ticket 2.1.1 -- Add CompanyRecord Pydantic model and CompanyRepository
* Files: backend/app/ingestion/models.py, NEW: backend/app/ingestion/company_repository.py
* Action:
  1. Add CompanyRecord to models.py with fields: company_id (UUIDv4), name (str), ticker (str | None = None), created_at (ISO 8601 UTC), job_ids (list[str] = []).
  2. Create company_repository.py with: save_company, list_companies, get_company, add_job_to_company (idempotent). Storage: data/companies.json.
  3. mypy --strict required (CONSTITUTION 1.1).
* Acceptance Criteria: CompanyRecord round-trips through CompanyRepository. add_job_to_company is idempotent.

#### Ticket 2.1.2 -- Add filing_year and company_id fields to JobRecord
* Files: backend/app/ingestion/models.py, backend/app/ingestion/repository.py, backend/app/ingestion/router.py
* Action:
  1. Add to JobRecord: filing_year: int | None = None and company_id: str | None = None.
  2. Update POST /upload/jobs to accept optional filing_years: list[int | None] and company_name: str | None. Zip filing_years by index same as target_metrics.
  3. If company_name is provided, create or look up CompanyRecord and set company_id on each created JobRecord.
* Acceptance Criteria: Job created with filing_year=2023 and company name persists those fields and returns them in GET /upload/jobs.

#### Ticket 2.1.3 -- Add Company API endpoints
* File: NEW: backend/app/ingestion/company_router.py
* Action:
  1. POST /companies -- create company (body: name, optional ticker). Returns CompanyRecord.
  2. GET /companies -- list all with associated job summaries.
  3. GET /companies/{company_id} -- get one company with full job list.
  4. POST /companies/{company_id}/jobs/{job_id} -- assign existing job to company.
  5. Register in main.py with prefix /companies.
* Acceptance Criteria: All 4 endpoints return correct data and handle missing-entity 404s.

#### Ticket 2.1.4 -- Update frontend upload form with Company and Filing Year fields
* Files: NEW: frontend/src/components/CompanySelector.tsx, frontend/src/App.tsx, frontend/src/types/job.ts
* Action:
  1. Add Assign to Company combobox above staged file list: fetch GET /companies on mount, allow selecting existing or typing new name.
  2. Add Fiscal Year numeric input per staged file row alongside target metric dropdown.
  3. Include company_name and filing_years in POST /upload/jobs form body.
  4. Add filing_year: number | null and company_id: string | null to JobRecord TypeScript type.
* Acceptance Criteria: Upload form sends company name and fiscal years. Jobs display fiscal year in job list.

#### Ticket 2.1.5 -- Add Company and filing_year unit + integration tests
* Files: NEW: backend/tests/ingestion/test_company_repository.py, backend/tests/ingestion/test_router.py
* Action:
  1. Test CompanyRepository: create, list, get, add_job (idempotent).
  2. Test POST /companies creates and returns CompanyRecord.
  3. Test POST /upload/jobs with filing_years=[2023] creates JobRecord with filing_year=2023.
  4. Test POST /companies/{company_id}/jobs/{job_id} links job to company.
* Acceptance Criteria: pytest tests/ingestion/ passes 100%.

---

### Step 2.2 -- Multi-Year Excel Model Generator

#### Ticket 2.2.1 -- Implement multi-year workbook generator
* File: NEW: backend/app/excel_export/multi_year_generator.py
* Action:
  1. Pure function generate_multi_year_workbook(company: CompanyRecord, jobs: list[tuple[JobRecord, FormulaTree]], output_dir: Path) -> WorkbookGenerationResult.
  2. Layout: Row 1 company name title. Row 2 column headers: Line Item (col A), then FY{year} per job ordered by filing_year ascending. Rows 3+ one row per unique normalized_label across all years. Absent-in-year cells left blank (not zero). Final row target_metric Total with =SUM(B{start}:B{end}) per year column.
  3. Value cells: plain numeric (blue hardcode per CONSTITUTION 2.5) + provenance comment.
  4. Total cells: =SUM(col_start:col_end) formula (black bold double-underline).
  5. Pure function: no I/O beyond output_dir write, no global state (CONSTITUTION 1.4).
* Acceptance Criteria: 3 FormulaTree inputs -> single xlsx with 3 year columns, zero formula errors. Absent-year cells are blank.

#### Ticket 2.2.2 -- Add POST /companies/{company_id}/multi-year-model endpoint
* File: backend/app/ingestion/company_router.py
* Action:
  1. Load CompanyRecord and all associated JobRecords.
  2. For each job: load review items -> read_formula_inputs_from_review -> build_formula_tree. Skip jobs with invalid trees.
  3. If fewer than 2 valid jobs: return 400 with At least 2 completed jobs with confirmed items are required.
  4. Call generate_multi_year_workbook(company, valid_jobs, output_dir).
  5. Return WorkbookGenerationResult.
* Acceptance Criteria: Endpoint with 2+ completed jobs produces data/models/{company_id}_multi_year.xlsx.

#### Ticket 2.2.3 -- Add Build Multi-Year Model button in frontend company view
* Files: NEW: frontend/src/components/CompanyView.tsx, frontend/src/App.tsx
* Action:
  1. Create CompanyView.tsx: shows company name, ticker, associated jobs with year/status/model_ready badges.
  2. Show Build Multi-Year Model primary button, enabled when doneJobsWithModels.length >= 2.
  3. On click: POST /companies//multi-year-model. On success: download link.
  4. Wire into App.tsx: add activeCompanyId state; clicking a company badge on job list opens company view.
* Acceptance Criteria: Company with 2+ done+model_ready jobs shows the button. Clicking it downloads the multi-year xlsx.

#### Ticket 2.2.4 -- Connect drift detection to Company filing history
* Files: backend/app/drift/service.py, backend/app/drift/router.py
* Action:
  1. In evaluate_job_drift, if entity not explicitly passed, resolve from JobRecord.company_id -> CompanyRecord.name.
  2. If filing_year not explicitly passed, resolve from JobRecord.filing_year.
  3. POST /drift/jobs/{job_id}/evaluate (no body) automatically uses company name and filing year.
* Acceptance Criteria: Drift evaluation without explicit body uses job company and year correctly.

#### Ticket 2.2.5 -- Add multi-year generator and company endpoint tests
* Files: NEW: backend/tests/excel_export/test_multi_year_generator.py, NEW: backend/tests/ingestion/test_company_router.py
* Action:
  1. Test generate_multi_year_workbook with 3 mock trees -> valid xlsx with 3 year columns.
  2. Test absent labels in a year produce blank cells, not zeros.
  3. Test endpoint with 1 valid job returns 400.
  4. Test endpoint with 2 valid jobs returns 200 and creates xlsx.
* Acceptance Criteria: pytest tests/excel_export/ tests/ingestion/ passes 100%.

---

## Implementation Checklist

Phase 0 -- Unblock Core Loop
  Step 0.1 -- Fix model generation gating
    [x] Ticket 0.1.1 -- Auto-accept high-confidence records in reader
    [x] Ticket 0.1.2 -- review-to-formula adapter
    [x] Ticket 0.1.3 -- formula engine unit tests
  Step 0.2 -- Model generation API
    [x] Ticket 0.2.1 -- POST /models/{job_id}/generate
    [x] Ticket 0.2.2 -- GET /models/{job_id}/download
    [x] Ticket 0.2.3 -- model generation integration tests
  Step 0.3 -- Frontend download wiring
    [x] Ticket 0.3.1 -- Excel download button in JobList
    [x] Ticket 0.3.2 -- Generate Model button in ReviewPage
    [x] Ticket 0.3.3 -- frontend component tests
  Step 0.4 -- Auto-generate draft in job runner
    [x] Ticket 0.4.1 -- Auto-generate from auto-accepted items
    [x] Ticket 0.4.2 -- Propagate model_ready to frontend
    [x] Ticket 0.4.3 -- model_ready badge in JobList
    [x] Ticket 0.4.4 -- job runner integration tests

Phase 1 -- Business Model Alignment
  Step 1.1 -- Filter to reconciliation tables before classification
    [x] Ticket 1.1.1 -- Reconciliation table detector
    [x] Ticket 1.1.2 -- Propagate is_reconciliation_candidate
    [x] Ticket 1.1.3 -- Filter before Groq dispatch in job runner
    [x] Ticket 1.1.4 -- Extraction and classification tests
  Step 1.2 -- Scope review UI to flagged reconciliation items
    [x] Ticket 1.2.1 -- Filter ReviewRepository to candidates only
    [x] Ticket 1.2.2 -- Simplify review UI tabs
    [x] Ticket 1.2.3 -- Approve All and Generate Model button
    [x] Ticket 1.2.4 -- Review UI frontend tests
  Step 1.3 -- Redesign Excel output to banker-editable format
    [x] Ticket 1.3.1 -- Source_Inputs: plain values + comments
    [x] Ticket 1.3.2 -- Reconciliation: cross-sheet refs + SUM
    [x] Ticket 1.3.3 -- Excel generator tests
  Step 1.4 -- Fix Audit Trail empty state
    [ ] Ticket 1.4.1 -- Pre-generation guidance in AuditTrailView

Phase 2 -- Multi-Year Company Architecture
  Step 2.1 -- Company data model
    [ ] Ticket 2.1.1 -- CompanyRecord + CompanyRepository
    [ ] Ticket 2.1.2 -- filing_year + company_id on JobRecord
    [ ] Ticket 2.1.3 -- Company API endpoints
    [ ] Ticket 2.1.4 -- Frontend Company + Filing Year fields
    [ ] Ticket 2.1.5 -- Company + filing_year tests
  Step 2.2 -- Multi-year Excel model
    [ ] Ticket 2.2.1 -- multi_year_generator.py
    [ ] Ticket 2.2.2 -- POST /companies/{id}/multi-year-model
    [ ] Ticket 2.2.3 -- Build Multi-Year Model UI button
    [ ] Ticket 2.2.4 -- Connect drift to Company filing history
    [ ] Ticket 2.2.5 -- Multi-year generator + company endpoint tests

---

## Gate Criteria Per Phase

Each phase is complete only when all of the following pass:
1. mypy --strict on all modified backend modules -- 0 errors
2. pytest tests/ -v -- 100% pass
3. ruff check app/ -- 0 warnings
4. npx tsc --noEmit -- 0 errors
5. npm test -- 0 failures
6. npx eslint src/ -- 0 warnings
7. Manual smoke test: upload a real 10-K, verify the phase acceptance criteria end-to-end
