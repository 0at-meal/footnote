# Footnote — Phase 3 Updates: Institutional Multi-Statement Valuation Engine

**Produced by:** Architectural analysis + grill-me interview session (2026-08-24).
**Execution model:** Each ticket is implemented one at a time using the standard 7-step development loop from `handoff.md` (Explore ? Plan ? Implement ? Verify ? Review ? Test ? Commit). No phase begins until every ticket in the prior phase passes `mypy --strict`, `pytest`, `npm test`, `ruff`, and `eslint`.

---

## Architecture Decisions

| Decision | Answer |
|---|---|
| Document structure | Separate `updates.md` — does not touch `refinement.md` (Phase 0/1/2 history) |
| Taxonomy migration | New Master Taxonomy (60–80 GAAP/IFRS items) completely replaces the old 10-item flat seed |
| Taxonomy data model | Structured `TaxonomyItem` with `canonical_name`, `statement_type`, `display_order`, `is_debit`, `aliases` — no longer a flat `list[str]` |
| Groq classifier role | Two-level: GAAP items matched deterministically via alias engine; Groq only called for items that fail deterministic matching entirely |
| Formula engine behavior | All 4 statement trees built simultaneously for every filing; no user-selected target metric |
| `target_metric` field | Removed from the upload form; field becomes informational-only on `JobRecord` for backward compatibility with existing persisted data |
| Excel output format | New `multi_statement_generator.py` replaces `generator.py` and `multi_year_generator.py`; single filing ? 6 tabs (1 year column); multi-year ? same 6 tabs (N year columns) |
| Old generators | `generator.py` and `multi_year_generator.py` deprecated (kept on disk but no longer called) |
| Review UI | `ReviewPage.tsx` completely rewritten with statement-triage tabs |
| Phase order | Strictly sequential: A ? B ? C ? D ? E |
| CONSTITUTION amendments | Required — see Phase A, Step A.0 for justification and approval gate before any code changes |

---

## Phase A — Master Financial Taxonomy & Statement Classification

**Goal:** Replace the 10-item flat non-GAAP taxonomy with a structured 60–80 item Master Financial Taxonomy (GAAP/IFRS), grouped by `StatementType`. Introduce a two-level classification pipeline: deterministic alias matching first, Groq for genuine unknowns only.

**Gate:** No Phase B work begins until all Phase A tickets pass `mypy --strict`, `pytest tests/ -v`, `ruff check`, `npx tsc --noEmit`, `npm test`, and a manual smoke test confirming that uploading a real Google 10-Q reduces review flags from ~440 to <15.

---

### Step A.0 — CONSTITUTION Amendment Gate

**Purpose:** Before touching any code, identify and justify every CONSTITUTION rule that the new architecture requires amending. The amendment is written up in detail here, presented to the user for approval, and only merged into `CONSTITUTION.md` after explicit approval.

#### Ticket A.0.1 — Draft CONSTITUTION amendments and obtain user approval
* **File:** `docs/CONSTITUTION.md` (only after approval)
* **Rules requiring amendment:**
  1. **§3.x module boundaries for `classification/models.py`** — The current rules treat `classification/` as an LLM-isolation boundary. The new `StatementType` enum and `TaxonomyItem` model need to be importable by `review/` (for `statement_type` on `ReviewItem`) and `formula_engine/` (for statement-level DAG grouping). Proposed addition: *"`classification/models.py` (Pydantic data models only) may be imported by `review/`, `formula_engine/`, and `excel_export/` for the purpose of reading `StatementType` and `TaxonomyItem` types. The LLM client (`classification/client.py`) and dispatcher (`classification/dispatcher.py`) remain fully isolated from all downstream modules."*
  2. **§1.1 (module typing scope)** — Extend `mypy --strict` requirement to explicitly cover `classification/models.py` since it is now a shared data-model layer.
* **Action:** Write the draft amendment text, present it to the user, wait for explicit approval before touching `CONSTITUTION.md`.
* **Acceptance Criteria:** User reviews and approves the amendment text. `CONSTITUTION.md` is updated only after approval.

---

### Step A.1 — Master Taxonomy Schema & Seed Data

#### Ticket A.1.1 — Define `StatementType` enum and `TaxonomyItem` model
* **File:** `backend/app/classification/models.py`
* **Action:**
  1. Add `StatementType(str, Enum)` with values: `income_statement`, `balance_sheet`, `cash_flow`, `non_gaap_bridge`, `kpi`.
  2. Add `TaxonomyItem(BaseModel)` with fields: `canonical_name: str`, `statement_type: StatementType`, `display_order: int`, `is_debit: bool`, `aliases: list[str]`.
  3. Add `MasterTaxonomy(BaseModel)` with `items: list[TaxonomyItem]`.
  4. Keep `mypy --strict` compliance.
* **Acceptance Criteria:** `MasterTaxonomy` model round-trips through JSON. `mypy --strict` on `classification/` passes.

#### Ticket A.1.2 — Seed `taxonomy.json` with 60–80 GAAP/IFRS canonical items
* **File:** `backend/data/taxonomy.json`
* **Action:** Write the full seed data file covering:
  - *Income Statement (15 items):* Revenue/Net Revenue, Cost of Revenue, Gross Profit, R&D, Sales & Marketing, G&A, Total Operating Expenses, Operating Income (EBIT), Interest Income, Interest Expense, Other Income/Expense Net, Income Before Tax, Income Tax Provision, Net Income, EPS Diluted.
  - *Cash Flow (10 items):* Net Income (CF), D&A, SBC (CF), Changes in Working Capital, Operating Cash Flow, CapEx, Free Cash Flow, Debt Issuance/Repayment, Share Repurchases, Dividends Paid.
  - *Balance Sheet (15 items):* Cash & Equivalents, Short-Term Investments, Accounts Receivable, Inventory, Other Current Assets, Total Current Assets, PP&E Net, Goodwill, Intangibles Net, Total Assets, Accounts Payable, Short-Term Debt, Long-Term Debt, Total Stockholders Equity, Total Liabilities & Equity.
  - *Non-GAAP Bridge (10 items):* Stock-Based Compensation, Restructuring Charges, Litigation Charges, Lease Adjustments, Amortization of Intangibles, Acquisition-Related Expenses, Impairment of Assets, Gain/Loss on Divestitures, Foreign Currency Adjustments, Other Non-Operating Expenses.
  - Each item includes 3–8 `aliases` for common company-specific wordings.
* **Acceptance Criteria:** `MasterTaxonomy.model_validate(data)` succeeds with no validation errors.

---

### Step A.2 — Taxonomy Repository Migration

#### Ticket A.2.1 — Rewrite `TaxonomyRepository` to use `MasterTaxonomy`
* **File:** `backend/app/classification/taxonomy.py`
* **Action:**
  1. Replace `SEED_TAXONOMY: list[str]` with `SEED_MASTER_TAXONOMY: MasterTaxonomy`.
  2. Rewrite `load_taxonomy() -> MasterTaxonomy`.
  3. Rewrite `save_taxonomy(master: MasterTaxonomy) -> Path`.
  4. Add `get_items_by_statement(statement_type: StatementType) -> list[TaxonomyItem]`.
  5. Add `get_all_canonical_names() -> list[str]` for backward compatibility.
  6. Keep atomic write via `os.replace` (CONSTITUTION §1.9).
* **Acceptance Criteria:** Repository reads `taxonomy.json` as `MasterTaxonomy`. `mypy --strict` passes.

#### Ticket A.2.2 — Rewrite deterministic alias matcher against `MasterTaxonomy`
* **File:** `backend/app/classification/taxonomy.py`
* **Action:**
  1. Replace `match_canonical_taxonomy()` with `match_master_taxonomy(candidate_label: str, master: MasterTaxonomy) -> TaxonomyItem | None`.
  2. Matching priority: (1) exact canonical_name match, (2) exact alias match, (3) canonicalized alias match.
  3. Remove old `synonym_rules` list — aliases in `taxonomy.json` serve this purpose.
  4. Update `check_label_against_taxonomy()` to return `matched_item: TaxonomyItem | None`.
* **Acceptance Criteria:** `match_master_taxonomy("Cost of sales", master)` returns `TaxonomyItem` for "Cost of Revenue". `match_master_taxonomy("zzzunknown", master)` returns `None`.

---

### Step A.3 — Two-Level Classification Pipeline

#### Ticket A.3.1 — Add pre-classifier deterministic dispatch stage
* **File:** `backend/app/classification/dispatcher.py`
* **Action:**
  1. Add `pre_classify_records(scored_records: list[ScoredRecord], master: MasterTaxonomy) -> tuple[list[ClassifiedRecord], list[ScoredRecord]]`.
  2. On match: create `ClassifiedRecord` with `normalized_label=item.canonical_name`, `taxonomy_status=TaxonomyStatus.matched`, `is_confirmed=True`, `classifier_confidence=1.0`, `statement_type` from matched `TaxonomyItem`.
  3. Return `(deterministically_classified, unmatched_records)`.
* **Acceptance Criteria:** Items matching aliases are classified without a Groq API call.

#### Ticket A.3.2 — Update `normalize_records` to merge pre-classified items
* **File:** `backend/app/classification/normalizer.py`
* **Action:**
  1. Update signature to accept `pre_classified: list[ClassifiedRecord]` alongside `groq_batch_result`.
  2. Merge both lists in deterministic order matching original `scored_records` order by `record_index`.
  3. Groq-classified items that happen to match the taxonomy get `statement_type` resolved.
* **Acceptance Criteria:** Final `classified_records` list is in original `scored_records` order.

#### Ticket A.3.3 — Update `job_runner.py` to use two-level classification
* **File:** `backend/app/job_runner.py`
* **Action:**
  1. After Stage 5, load `master = taxonomy_repo.load_taxonomy()`.
  2. Run `pre_classified, unmatched = pre_classify_records(reconciliation_candidates, master)`.
  3. Only dispatch `unmatched` to Groq.
  4. Call updated `normalize_records(unmatched, batch_result, master, pre_classified=pre_classified)`.
  5. Remove `target_metric` from formula engine calls.
  6. Log counts: pre-classified, dispatched to Groq, total classified.
* **Acceptance Criteria:** Groq NOT called for deterministically-matched items.

---

### Step A.4 — `statement_type` on `ReviewItem` & `ClassifiedRecord`

#### Ticket A.4.1 — Add `statement_type` to `ClassifiedRecord`
* **File:** `backend/app/classification/models.py`
* **Action:** Add `statement_type: StatementType | None = None` to `ClassifiedRecord`. Populated during pre-classification and Groq normalization.
* **Acceptance Criteria:** `ClassifiedRecord.statement_type` is non-None for all taxonomy-matched items.

#### Ticket A.4.2 — Add `statement_type` to `ReviewItem`
* **File:** `backend/app/review/models.py`
* **Action:**
  1. Add `statement_type: StatementType | None = Field(default=None)` to `ReviewItem`.
  2. Update `ReviewRepository._from_classified_records` to propagate `statement_type`.
* **Acceptance Criteria:** `GET /review/{job_id}/items` includes `statement_type` on each item.

---

### Step A.5 — Taxonomy Unit Tests

#### Ticket A.5.1 — Unit tests for Master Taxonomy
* **File:** `backend/tests/classification/test_taxonomy.py`
* **Action:**
  1. Test `MasterTaxonomy` validates from seed `taxonomy.json`.
  2. Test `load_taxonomy()` returns `MasterTaxonomy`.
  3. Test `match_master_taxonomy` hits and misses.
  4. Test `get_items_by_statement` filtering.
  5. Test `pre_classify_records` classifies alias-matching records without Groq.
  6. Test unmatched records are returned for Groq dispatch.
* **Acceptance Criteria:** `pytest tests/classification/ -v` passes 100%.

---

## Phase B — Multi-Statement Formula Tree Architecture

**Goal:** Build deterministic DAGs for all financial statements simultaneously.

**Gate:** No Phase C work begins until all Phase B tickets pass all quality gates.

---

### Step B.1 — `FormulaTree` Model Expansion

#### Ticket B.1.1 — Add `ComprehensiveModelTree` model
* **File:** `backend/app/formula_engine/models.py`
* **Action:**
  1. Add `StatementTree(BaseModel)` with `statement_type: StatementType`, `tree: FormulaTree`.
  2. Add `ComprehensiveModelTree(BaseModel)` with `statement_trees: list[StatementTree]`, `is_valid: bool`, `error_message: str | None`, and computed properties for each statement tree.
* **Acceptance Criteria:** Fully typed, passes `mypy --strict`.

---

### Step B.2 — Multi-Statement DAG Builders

#### Ticket B.2.1 — Implement `build_income_statement_tree`
* **File:** `backend/app/formula_engine/tree.py`
* **Action:** Groups nodes with `statement_type == income_statement` into Revenue ? (-COGS) ? Gross Profit ? (-OpEx) ? EBIT ? (±Interest/Tax) ? Net Income. Sign conventions: COGS and OpEx subtracted. Missing nodes produce blank-cell markers.
* **Acceptance Criteria:** Correct DAG structure, correct sign conventions, blank not zero for missing nodes.

#### Ticket B.2.2 — Implement `build_ebitda_bridge_tree`
* **File:** `backend/app/formula_engine/tree.py`
* **Action:** Starts from EBIT as `FormulaNodeType.cross_reference` (renders as `='Income_Statement'!{cell}`), adds D&A + non-GAAP add-backs ? Adjusted EBITDA.
* **Acceptance Criteria:** EBIT node renders as cross-sheet formula.

#### Ticket B.2.3 — Implement `build_free_cash_flow_tree`
* **File:** `backend/app/formula_engine/tree.py`
* **Action:** Operating Cash Flow - CapEx ? FCFF; FCFF - Interest - Debt Repayment ? FCFE. Sign conventions: CapEx is subtraction (outflow).
* **Acceptance Criteria:** FCFF = OCF - CapEx formula structure correct.

#### Ticket B.2.4 — Implement `build_net_debt_tree`
* **File:** `backend/app/formula_engine/tree.py`
* **Action:** (Short-Term Debt + Long-Term Debt) - (Cash + Marketable Securities) ? Net Debt.
* **Acceptance Criteria:** Net Debt formula matches `=SUM(debt_cells) - SUM(cash_cells)` structure.

#### Ticket B.2.5 — Implement `build_comprehensive_model_tree`
* **File:** `backend/app/formula_engine/tree.py`
* **Action:**
  1. Groups `FormulaInputBatch.nodes` by `statement_type`, calls all 4 builders.
  2. Returns `ComprehensiveModelTree` with all trees.
  3. Remove `SUPPORTED_TARGET_METRICS` guard.
* **Acceptance Criteria:** Produces 4 valid statement trees from a mixed batch.

---

### Step B.3 — Formula Engine Tests

#### Ticket B.3.1 — Deterministic unit tests for all statement tree builders
* **File:** `backend/tests/formula_engine/test_statement_trees.py`
* **Action:** Tests for each builder: correct DAG structure, sign conventions, missing-node blanks, EBIT cross-reference, FCFF formula, Net Debt formula, comprehensive builder produces all 4 trees, zero-hallucination (all leaf values bound to `FormulaInputNode`).
* **Acceptance Criteria:** `pytest tests/formula_engine/ -v` passes 100%.

---

## Phase C — 6-Tab Multi-Statement Excel Compiler

**Goal:** Write `multi_statement_generator.py` — unified generator for single-year and multi-year outputs. Deprecate `generator.py` and `multi_year_generator.py`.

**Gate:** No Phase D work begins until all Phase C tickets pass all quality gates.

---

### Step C.1 — New `multi_statement_generator.py`

#### Ticket C.1.1 — Implement 6-tab workbook structure
* **File:** `backend/app/excel_export/multi_statement_generator.py` (NEW)
* **Action:**
  1. `generate_multi_statement_workbook(company: CompanyRecord, year_trees: list[tuple[JobRecord, ComprehensiveModelTree]], output_dir: Path | None) -> WorkbookGenerationResult`.
  2. Single-year = list of length 1. Multi-year = list of N, sorted by `filing_year` ascending.
  3. 6 sheets in order: `Executive_Summary`, `Income_Statement`, `EBITDA_Bridge`, `Cash_Flow`, `Balance_Sheet`, `Audit_Trail`.
  4. Col A = line item label. Cols B+ = one per year (FY2022, FY2023, ...).
  5. xlsxwriter only (CONSTITUTION §4.2). All formulas as uppercase Excel formulas.
  6. Space-free sheet names (underscores).
* **Acceptance Criteria:** Valid 6-sheet `.xlsx`. Single-year ? 1 data column. Multi-year ? N data columns.

#### Ticket C.1.2 — Live cross-sheet formula compilation
* **File:** `backend/app/excel_export/multi_statement_generator.py`
* **Action:**
  1. `EBITDA_Bridge` EBIT cell: `='Income_Statement'!{cell_coord}`.
  2. `Executive_Summary` KPIs: all reference downstream tabs.
  3. Total rows: `=SUM({col}{start}:{col}{end})`.
  4. Formula cells: green font (`#15803d`). Hardcode cells: blue font (`#0000FF`). Total rows: black bold double-underline. All per CONSTITUTION §2.5.
  5. Margin % cells: `=B{numerator}/B{revenue}` with percentage format.
* **Acceptance Criteria:** All cross-sheet formulas resolve. Zero formula errors.

#### Ticket C.1.3 — Cell-level PDF provenance notes on all tabs
* **File:** `backend/app/excel_export/multi_statement_generator.py`
* **Action:**
  1. Every non-formula value cell: xlsxwriter comment with `Source: {filename} | Page: {page} | Box: [{x0}, {y0}, {x1}, {y1}] | Score: {confidence:.2f}`.
  2. `Audit_Trail` tab: plain table — Sheet, Cell, Line Item, Value, Page, BBox, Score, Filing.
  3. Provenance records written to `data/models/{job_id}_provenance.json`.
* **Acceptance Criteria:** Every value cell has a comment. `Audit_Trail` has one row per value cell.

#### Ticket C.1.4 — Deprecate `generator.py` and `multi_year_generator.py`
* **Files:** `backend/app/excel_export/generator.py`, `backend/app/excel_export/multi_year_generator.py`
* **Action:**
  1. Add deprecation notice to both files: `# DEPRECATED: Replaced by multi_statement_generator.py (Phase 3). Do not add new callers.`
  2. Do NOT delete — keep for reference.
  3. Update `job_runner.py` to call `generate_multi_statement_workbook`.
  4. Update `company_router.py` to call `generate_multi_statement_workbook`.
  5. Remove all production imports of the deprecated generators.
* **Acceptance Criteria:** No production code imports from deprecated generators.

---

### Step C.2 — API Endpoint Updates

#### Ticket C.2.1 — Add `POST /companies/{company_id}/full-model` endpoint
* **File:** `backend/app/ingestion/company_router.py`
* **Action:**
  1. Loads all completed jobs for company ? builds `ComprehensiveModelTree` per job ? calls `generate_multi_statement_workbook`.
  2. Accepts single-job companies (no minimum of 2 required).
  3. Returns `WorkbookGenerationResult`.
* **Acceptance Criteria:** 1-job company produces a 6-tab `.xlsx`.

#### Ticket C.2.2 — Add `GET /companies/{company_id}/full-model/download` endpoint
* **File:** `backend/app/ingestion/company_router.py`
* **Action:** Resolves path via `ModelRepository`, returns `FileResponse`. 404 if no model exists.
* **Acceptance Criteria:** Streams valid `.xlsx` file.

#### Ticket C.2.3 — Update single-job generate endpoint
* **File:** `backend/app/excel_export/router.py`
* **Action:**
  1. `POST /models/{job_id}/generate` builds `ComprehensiveModelTree` and calls `generate_multi_statement_workbook`.
  2. Wraps single job in synthetic `CompanyRecord` if none exists.
* **Acceptance Criteria:** Single-job generate produces a 6-tab workbook.

---

### Step C.3 — Excel Compiler Tests

#### Ticket C.3.1 — Unit tests for `multi_statement_generator.py`
* **File:** `backend/tests/excel_export/test_multi_statement_generator.py` (NEW)
* **Action:**
  1. Test single-year ? 6 sheets, 1 data column.
  2. Test multi-year (3 jobs) ? 6 sheets, 3 data columns.
  3. Test `EBITDA_Bridge` EBIT formula contains `'Income_Statement'!`.
  4. Test total rows contain `=SUM(...)`.
  5. Test absent-in-year cells are blank (not zero).
  6. Test `Audit_Trail` row count = total value cells.
  7. Test zero formula errors (via openpyxl read-only validation).
* **Acceptance Criteria:** `pytest tests/excel_export/ -v` passes 100%.

---

## Phase D — Frontend Statement Views & Triage Experience

**Goal:** Rewrite `ReviewPage.tsx` with statement-triage tabs. Remove `target_metric` from upload form. Wire 6-tab model generation into UI.

**Gate:** No Phase E work begins until all Phase D tickets pass all quality gates.

---

### Step D.1 — Remove `target_metric` from Upload Form

#### Ticket D.1.1 — Remove target_metric selector from frontend
* **Files:** `frontend/src/components/JobList.tsx`, `frontend/src/App.tsx`, `frontend/src/types/job.ts`
* **Action:**
  1. Remove `target_metric` dropdown from staged file row in `JobList.tsx`.
  2. Remove `target_metric` from `StagedFile` TypeScript type.
  3. Remove `target_metrics` from `POST /upload/jobs` form body.
  4. Keep `target_metric: string | null` on `JobRecord` TypeScript type for backward compat.
* **Acceptance Criteria:** Upload form has no target metric dropdown. Submission works.

#### Ticket D.1.2 — Update backend to not require `target_metric` on upload
* **Files:** `backend/app/ingestion/router.py`, `backend/app/ingestion/models.py`, `backend/app/job_runner.py`
* **Action:**
  1. Make `target_metrics` optional in `POST /upload/jobs` (defaults to null).
  2. `JobRecord.target_metric` defaults to `"Full Model"` if not provided.
  3. `job_runner.py`: call `build_comprehensive_model_tree` unconditionally (no target_metric parameter).
* **Acceptance Criteria:** Upload without `target_metrics` creates jobs. Job runner builds all statement trees.

---

### Step D.2 — Rewrite `ReviewPage.tsx` with Statement Triage

#### Ticket D.2.1 — Rewrite `ReviewPage.tsx` with statement filter tabs
* **File:** `frontend/src/components/review/ReviewPage.tsx`
* **Action:**
  1. Statement Navigation Bar: `[ All ({n}) ] [ Income Statement ({n}) ] [ Cash Flow ({n}) ] [ EBITDA Bridge ({n}) ] [ Balance Sheet ({n}) ] [ Flagged Only ({n}) ]`.
  2. Default active tab: `Flagged Only`.
  3. Items with `statement_type === null` appear only in `All` and `Flagged Only` (if flagged).
  4. Preserve: PDF.js split-screen viewer, inline editing, flag/confirm actions, taxonomy prompt.
  5. Update `FilterTab` type to cover all statement types.
* **Acceptance Criteria:** Correct item counts per tab. Tab switching filters correctly.

#### Ticket D.2.2 — Add statement readiness indicators
* **File:** `frontend/src/components/review/ReviewPage.tsx`
* **Action:**
  1. Per-statement chips below nav bar: `? Income Statement: Ready` or `? EBITDA Bridge: 3 items need review`.
  2. "Ready" = all items are `auto_accepted` or `locked`. Green dot for Ready, amber warning for not ready.
* **Acceptance Criteria:** Chips reflect actual statuses. Confirming items updates chips.

#### Ticket D.2.3 — Add "Approve & Generate Complete Financial Model" CTA
* **File:** `frontend/src/components/review/ReviewPage.tsx`
* **Action:**
  1. Primary header button: **"Approve & Generate Complete Financial Model (6 Tabs)"**.
  2. Enabled when: =1 item exists AND no `manual_required` items remain.
  3. On click: `POST /review/{jobId}/confirm-batch` ? `POST /models/{jobId}/generate`.
  4. On success: banner with `.xlsx` download link + "View Audit Trail" link.
  5. On failure: show `error_detail` inline.
* **Acceptance Criteria:** One click generates 6-tab model and presents download.

---

### Step D.3 — Frontend Tests

#### Ticket D.3.1 — Update review page tests
* **File:** `frontend/src/components/review/ReviewPage.test.tsx`
* **Action:** Tests for: statement tabs render with counts, Flagged Only is default, tab switching filters correctly, readiness chips show correct status, CTA present and enabled/disabled correctly, CTA dispatches confirm-batch then generate, success banner renders with download link.
* **Acceptance Criteria:** `npm test` passes 0 failures.

#### Ticket D.3.2 — Update upload form tests
* **File:** `frontend/src/components/JobList.test.tsx`
* **Action:** Tests for: no target metric dropdown in staged row, submission sends no `target_metrics`, `JobRecord` type accepts `target_metric: null`.
* **Acceptance Criteria:** `npm test` passes 0 failures.

---

## Phase E — End-to-End Verification & Quality Gates

---

### Step E.1 — Backend Verification

#### Ticket E.1.1 — Full backend quality gate run
```bash
pytest backend/tests/ -v
mypy backend/app
ruff check backend/app
black --check backend/app
```
* **Acceptance Criteria:** 0 test failures, 0 mypy errors, 0 ruff warnings, 0 formatting issues.

---

### Step E.2 — Frontend Verification

#### Ticket E.2.1 — Full frontend quality gate run
```bash
cd frontend
npm run test:run
npm run build
npm run lint
npx tsc --noEmit
npx eslint src/
```
* **Acceptance Criteria:** 0 test failures, successful build, 0 lint/TS errors.

---

### Step E.3 — Acceptance Gate Verification

#### Ticket E.3.1 — Real-world smoke test: Google 10-Q
* **Action:** Upload a real GOOGL 10-Q PDF. Wait for job completion. Open Review UI. Count flags. Click "Approve & Generate Complete Financial Model (6 Tabs)". Download and open `.xlsx`.
* **Acceptance Criteria (all 4 must pass):**
  1. **Flag Reduction:** Review flags < 15 items (down from ~440).
  2. **Auto-Acceptance Rate:** > 90% of standard GAAP/IFRS items auto-accepted.
  3. **Workbook Completeness:** 6 tabs present. Zero `#REF!` or `#VALUE!` errors.
  4. **Provenance Coverage:** 100% of value cells have PDF bounding box provenance comments.

---

## Implementation Checklist

### Phase A — Master Financial Taxonomy & Statement Classification
  Step A.0 — CONSTITUTION Amendment Gate
    [ ] Ticket A.0.1 — Draft amendments and obtain user approval
  Step A.1 — Master Taxonomy Schema & Seed Data
    [ ] Ticket A.1.1 — `StatementType` enum and `TaxonomyItem` model
    [ ] Ticket A.1.2 — Seed `taxonomy.json` with 60–80 items
  Step A.2 — Taxonomy Repository Migration
    [ ] Ticket A.2.1 — Rewrite `TaxonomyRepository` for `MasterTaxonomy`
    [ ] Ticket A.2.2 — Rewrite deterministic alias matcher
  Step A.3 — Two-Level Classification Pipeline
    [ ] Ticket A.3.1 — Pre-classifier deterministic dispatch stage
    [ ] Ticket A.3.2 — Update `normalize_records` to merge pre-classified items
    [ ] Ticket A.3.3 — Update `job_runner.py` for two-level classification
  Step A.4 — `statement_type` on `ReviewItem` & `ClassifiedRecord`
    [ ] Ticket A.4.1 — `statement_type` on `ClassifiedRecord`
    [ ] Ticket A.4.2 — `statement_type` on `ReviewItem`
  Step A.5 — Taxonomy Unit Tests
    [ ] Ticket A.5.1 — Master Taxonomy model, repository, alias matcher, pre-classifier tests

### Phase B — Multi-Statement Formula Tree Architecture
  Step B.1 — `FormulaTree` Model Expansion
    [ ] Ticket B.1.1 — `ComprehensiveModelTree` model
  Step B.2 — Multi-Statement DAG Builders
    [ ] Ticket B.2.1 — `build_income_statement_tree`
    [ ] Ticket B.2.2 — `build_ebitda_bridge_tree`
    [ ] Ticket B.2.3 — `build_free_cash_flow_tree`
    [ ] Ticket B.2.4 — `build_net_debt_tree`
    [ ] Ticket B.2.5 — `build_comprehensive_model_tree`
  Step B.3 — Formula Engine Tests
    [ ] Ticket B.3.1 — All statement tree builder deterministic tests

### Phase C — 6-Tab Multi-Statement Excel Compiler
  Step C.1 — New `multi_statement_generator.py`
    [ ] Ticket C.1.1 — 6-tab workbook structure
    [ ] Ticket C.1.2 — Live cross-sheet formula compilation
    [ ] Ticket C.1.3 — Cell-level PDF provenance notes on all tabs
    [ ] Ticket C.1.4 — Deprecate `generator.py` and `multi_year_generator.py`
  Step C.2 — API Endpoint Updates
    [ ] Ticket C.2.1 — `POST /companies/{id}/full-model` endpoint
    [ ] Ticket C.2.2 — `GET /companies/{id}/full-model/download` endpoint
    [ ] Ticket C.2.3 — Update single-job generate endpoint
  Step C.3 — Excel Compiler Tests
    [ ] Ticket C.3.1 — `multi_statement_generator.py` unit tests

### Phase D — Frontend Statement Views & Triage Experience
  Step D.1 — Remove `target_metric` from Upload Form
    [ ] Ticket D.1.1 — Remove target_metric from frontend upload form
    [ ] Ticket D.1.2 — Update backend to not require target_metric
  Step D.2 — Rewrite `ReviewPage.tsx` with Statement Triage
    [ ] Ticket D.2.1 — Rewrite `ReviewPage.tsx` with statement filter tabs
    [ ] Ticket D.2.2 — Add statement readiness indicators
    [ ] Ticket D.2.3 — Add "Approve & Generate Complete Financial Model" CTA
  Step D.3 — Frontend Tests
    [ ] Ticket D.3.1 — Update review page tests
    [ ] Ticket D.3.2 — Update upload form tests

### Phase E — End-to-End Verification & Quality Gates
  Step E.1 — Backend Verification
    [ ] Ticket E.1.1 — Full backend quality gate run
  Step E.2 — Frontend Verification
    [ ] Ticket E.2.1 — Full frontend quality gate run
  Step E.3 — Acceptance Gate Verification
    [ ] Ticket E.3.1 — Real-world smoke test (Google 10-Q, all 4 gates)

---

## Gate Criteria Per Phase

Each phase is complete only when ALL of the following pass:
1. `mypy --strict` on all modified backend modules — 0 errors
2. `pytest tests/ -v` — 100% pass
3. `ruff check app/` — 0 warnings
4. `black --check app/` — 0 formatting issues
5. `npx tsc --noEmit` — 0 TypeScript errors
6. `npm test` — 0 failures
7. `npx eslint src/` — 0 warnings
8. Manual smoke test: upload a real 10-Q, verify the phase acceptance criteria end-to-end
