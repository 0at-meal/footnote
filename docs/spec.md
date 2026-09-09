# Footnote — spec.md (Volume 4)

> **Version:** 4.0 — Re-baselined 2026-09-09  
> **Governed by:** `CONSTITUTION.md` (Volume 4). On conflict, the Constitution wins.  
> **Provenance:** Each section includes its source document(s) and the commit(s) that established or last modified this requirement. Archived feature specs live in `docs/archive/specs/`. The full requirements timeline is in `docs/_archive/TIMELINE.md`.

---

## 1. Functional Requirements

| ID | Requirement | Last Established |
|---|---|---|
| FR1 | Accept multi-file PDF uploads, queue for extraction, with `workflow_pack` selection | `plan.md` + `fixes.md` 2026-09-02 |
| FR2 | Parse PDFs and extract line items preserving multi-level headers, footnote references, exact page/bbox coordinates | `plan.md` `8ee5b497` 2026-08-10 |
| FR3 | Classify extracted line items against the Master Financial Taxonomy (60–80 GAAP/IFRS items); two-level pipeline: deterministic alias matching first, Groq for genuine unknowns only | `updates.md` `20d18eee` 2026-08-24 (supersedes 10-item seed from `plan.md`) |
| FR4 | Detect when a company redefines or renames a metric year-over-year and link the new definition to its historical baseline | `plan.md` `8ee5b497` 2026-08-10 |
| FR5 | Generate a native `.xlsx` workbook where every derived value is a real Excel formula | `plan.md` + ADR-002 2026-09-01 |
| FR6 | Bind provenance metadata (page, bbox, source file) to every generated cell | `plan.md` `8ee5b497` 2026-08-10 |
| FR7 | Provide a side-by-side review UI to confirm, correct, or flag each extracted item. Default view: only genuinely uncertain items (status-based filter, not confidence score threshold) | `plan.md` + issues_charter Step 3 2026-08-26 |
| FR8 | Allow a user to select any cell and retrieve its full source chain | `plan.md` `8ee5b497` 2026-08-10 |
| FR9 | Produce a downloadable, human-readable audit report (PDF) | `plan.md` `8ee5b497` 2026-08-10 |
| FR10 | Accept a `workflow_pack` field at upload time (`non_gaap_bridge` / `capital_structure` / `cash_conversion`); route extraction, generation, and output format accordingly | `fixes.md` `88072dad` 2026-09-02 |

## 2. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR1 | Identical input filings shall always produce identical formulas and structure. |
| NFR2 | 100% of generated numeric cells shall be traceable to a source location or explicitly marked as a manual hardcode. |
| NFR3 | A single 200-page 10-K shall complete extraction and model generation in under 5 minutes on local/free-tier compute. |
| NFR4 | The system shall run within free-tier or local-machine resource limits for MVP. |
| NFR5 | The architecture shall support a fully local/offline inference path (design principle, not MVP-enforced). |
| NFR6 | Adding a new target metric or workflow pack shall not require re-architecting the extraction or formula-generation layers. |
| NFR7 | Cross-year drift history shall survive a backend restart. |

## 3. Locked Decisions

| Decision | Value | Source |
|---|---|---|
| Phase 1 workflow pack | `non_gaap_bridge` (Adjusted EBITDA bridge) | `plan.md` §1.3; ADR-003 |
| Extraction execution environment | Local machine (not a hosted notebook) | `plan.md` §1.3 |
| LLM classifier provider | Groq API, `openai/gpt-oss-120b` | `plan.md` §1.3 |
| Excel output (non_gaap_bridge pack) | 2-tab: `Source_Inputs` + `Reconciliation`, plain numeric values + cross-sheet references. No `=HYPERLINK()` wrappers | ADR-002, ADR-003 |
| 6-tab generator | Frozen as beta feature — NOT default pipeline | ADR-003 |
| `narrative/` module | Deferred from automated pipeline | `fixes.md` §14.2 |
| Eval harness | Frozen pending pilot client confirmation. Corpus does not yet exist | `business_alignment.md` §1.1; `plan.md` §4 deferral note |

---

## 4. Feature Specifications

### Feature 1 — Multi-File PDF Upload & Job Queueing (FR1)

**Provenance:** `docs/archive/specs/spec_feature1.md` (original); `docs/workbook/feature-1-ingestion.md` (workbook); extended by `fixes.md` §7.1 (workflow_pack field addition, 2026-09-02).

1. Drag/drop or file-select upload zone (frontend). Multiple PDFs per session.
2. Server-side file type/size validation before a job is accepted. Invalid file → rejected with descriptive error, never silently dropped.
3. Job metadata (filename, size, status) persisted to a visible job list.
4. **Workflow pack selector** per job at upload time. Options:
   - `non_gaap_bridge` — Earnings Quality / Non-GAAP Bridge (default)
   - `capital_structure` — Capital Structure & Debt Sizing (debt tranches, ASC 842 leases)
   - `cash_conversion` — Cash Flow & Valuation Inputs (deferred — not yet fully implemented)
5. Optional: Assign to Company (name + fiscal year), for multi-year model building.
6. Job submission triggers the extraction pipeline routed by `workflow_pack`.

**Model changes from Volume 1:**
- `target_metric` field retained on `JobRecord` for backward compatibility but is informational only — the upload form no longer requires it as a primary selector.
- `workflow_pack: Literal["non_gaap_bridge", "capital_structure", "cash_conversion"] = "non_gaap_bridge"` added to `JobRecord`.
- `filing_year: int | None` and `company_id: str | None` added to `JobRecord` (Refinement Phase 2).
- `model_skip_reason: str | None` added to `JobRecord` — populated when model generation does not produce output.

**Acceptance criteria:**
- Multiple PDFs can be queued in one session.
- Invalid file rejected with clear error, not silently dropped.
- `workflow_pack` selection persisted and visible in job list.
- `model_skip_reason` visible in UI when `status == 'done' AND model_ready == false`.

---

### Feature 2 — Layout-Aware Extraction (FR2)

**Provenance:** `docs/archive/specs/spec_feature2.md`; `docs/workbook/feature-2-extraction.md`; `docs/issues_charter.md` Steps 1, 5, 6; `docs/fixes.md` §1 (bbox bug fixes, 2026-09-02).

1. Docling structural parse (tables, headers, footnote markers) per PDF.
2. PyMuPDF bounding-box extraction per identified value.
3. Assemble each value into: `{value, label, page, bbox, source_file}` (frozen 5-field schema, Constitution §2.3).
4. Structural-confidence scoring; low-confidence items flagged, not guessed. Confidence-band definitions: **auto-accept ≥ 0.95**, **human-review 0.65–0.95**, **manual entry < 0.65**.
5. `is_reconciliation_candidate: bool` tag on each `DoclingItem` — set by deterministic `_is_reconciliation_table()` pure function. Only `is_reconciliation_candidate == True` items proceed to classification for `non_gaap_bridge` pack.
6. `parser_used: Literal["docling", "pymupdf"]` field on `DoclingItem` — determines coordinate space for normalization.
7. Y-axis inversion applied for Docling-native coordinates (Docling uses bottom-left origin; canvas uses top-left origin). Condition: `item.parser_used == "docling"`.
8. PyMuPDF fallback: per-cell bbox uses 0-based loop indexing (`flat_idx = row_idx * num_cols + col_idx`), not 1-based.
9. Confidence scoring: `+0.15` bonus for items from reconciliation tables; `+0.05` for well-formed numeric values; table-consistency second pass.
10. Workflow-pack routing: `non_gaap_bridge` → filter to reconciliation tables (Item 7 MD&A). `capital_structure` → route directly to `footnote/extractor.py` for Note 8 debt/lease tables. `cash_conversion` → Statement of Cash Flows and related CapEx/WC notes.

**Acceptance criteria:**
- Runs against 3–5 real 10-Ks, locally, without crashing.
- Every extracted value carries a resolvable page and bbox.
- Items below auto-accept confidence are visibly flagged.
- `parser_used` field populated for every item.
- PyMuPDF fallback per-cell indexing uses 0-based formula.

---

### Feature 3 — Classification & Normalization (FR3)

**Provenance:** `docs/archive/specs/spec_feature3.md`; `docs/workbook/feature-3-classification.md`; `docs/updates.md` (Master Taxonomy, 2026-08-24); `docs/adr/ADR-001-target-metric-scoped-review.md`.

1. **Two-level classification pipeline** (supersedes Volume 1's Groq-first approach):
   - Level 1: Deterministic alias matching via `match_master_taxonomy(candidate_label, master_taxonomy)`. Priority: exact canonical_name → exact alias → canonicalized alias match.
   - Level 2: Groq classifier (`openai/gpt-oss-120b`) called only for items that fail Level 1 matching entirely.
2. Master Financial Taxonomy: structured 60–80 item taxonomy (`backend/data/taxonomy.json`), with `TaxonomyItem` fields: `canonical_name`, `statement_type: StatementType`, `display_order`, `is_debit`, `aliases: list[str]`.
3. `StatementType` enum: `income_statement`, `balance_sheet`, `cash_flow`, `non_gaap_bridge`, `kpi`.
4. Classifier's return type structurally cannot carry a numeric field (Constitution §4.7, §6.2).
5. Unrecognized labels (Level 1 miss AND Level 2 low-confidence) queued for user confirmation, never auto-accepted.
6. Confirmed, normalized label attached to the item's record.
7. Every classifier call logged: input context, returned label, confidence — exportable, machine-readable.
8. `is_target_metric_candidate_item()` predicate gates on `is_reconciliation_candidate == True` as primary signal; keyword fallback does NOT apply to items from P&L, balance sheet, or footnote tables when a reconciliation table exists.

**Acceptance criteria:**
- Classifier calls stay within Groq's published free-tier limits under realistic batch sizes.
- No code path allows classifier response to populate a numeric field.
- Decision log for every item is retrievable.
- Level 1 deterministic matching handles known aliases without Groq call.

---

### Feature 4 — Deterministic Model Generation (FR5, FR6)

**Provenance:** `docs/archive/specs/spec_feature4.md`; `docs/workbook/feature-4-model-generation.md`; ADR-002; ADR-003; `docs/fixes.md` §7.3 (Workflow Pack generator routing, 2026-09-02).

**Generator routing by workflow_pack:**
- `non_gaap_bridge` → `excel_export/bridge_generator.py` (2-tab: Source_Inputs + Reconciliation). Formula tree: `build_formula_tree(batch, target_metric)`.
- `capital_structure` → `excel_export/debt_schedule_generator.py` (2-tab: Debt Tranches & Spreads + Lease Waterfall). Data from `footnote/extractor.py`.
- `cash_conversion` → deferred / not yet implemented.
- Multi-year (company-level) → `excel_export/multi_year_generator.py` (fiscal years as columns, triggered manually from CompanyView).
- `multi_statement_generator.py` (6-tab) → beta/legacy only; NOT default pipeline.

**Excel output specification (non_gaap_bridge and capital_structure packs):**
1. Source_Inputs sheet: plain numeric values (`write_number()`), blue font (IB hardcode convention), cell comments with provenance: `Source: {source_file} / Page: {page} / BBox: ({x0}, {y0}) → ({x1}, {y1}) / Label: {label}`. No `write_url()` or `=HYPERLINK()`.
2. Reconciliation sheet: `=Source_Inputs!F{row}` cross-sheet references (`write_formula()`), green font (sheet-link). Total: `=SUM(C{start}:C{end})` (black bold, double-underline).
3. W3C Web Annotation provenance records generated and persisted to `data/results/{job_id}_provenance.json`.
4. Formula tree built as pure function — no I/O, no randomness (Constitution §1.4).

**Acceptance criteria:**
- Identical input → byte-identical formula structure on repeated runs (NFR1).
- 100% of generated formulas open and recalculate in Excel with zero broken references.
- Every non-hardcoded cell resolves to a source record.
- `multi_statement_generator.py` not imported from `job_runner.py` for `non_gaap_bridge` pack.

---

### Feature 5 — Extraction Review UI (FR7)

**Provenance:** `docs/archive/specs/spec_feature5.md`; `docs/workbook/feature-5-review-ui.md`; `docs/issues_charter.md` Steps 3, 9, 12, 15, 16, 17, 18, 19; ADR-001; `docs/fixes.md` §2, §9.

1. Source PDF page rendered via PDF.js using `PDF_RENDER_SCALE = 1.5` (constant from `lib/pdf/renderer.ts` — same constant used by both ReviewPage and AuditTrailView).
2. Canvas size read via `getBoundingClientRect().width/height` (not `clientWidth/clientHeight`).
3. Extracted items displayed alongside, each highlighted to its source bounding box.
4. **Default tab: Flagged items only** (`isFlagged` predicate is status-based: `status ∈ {needs_review, manual_required, extraction_error, pending_taxonomy_confirmation, flagged}`). Auto-accepted and locked items do not appear in Flagged tab.
5. Auto-accepted AND taxonomy-matched items are **pre-locked** on import (not shown in Flagged tab — they never needed review).
6. Confirm / edit / flag actions per item.
7. Confirmed items locked against further silent modification.
8. Review item IDs: content-based hash of `(job_id, source_file, page, bbox)` — stable across re-runs.
9. Dismissible amber banner when `parser_used === "pymupdf"` or `"mixed"`.
10. Dismissible amber banner when `target_metric_found === false` (target metric not found in document content).
11. Progress pulse animation on "Extracting" status badge.
12. Inline error state (not `alert()`) for confirm/flag/edit failures.
13. Empty Flagged tab shows "Generate Model" guidance button when no flagged items exist.

**Acceptance criteria:**
- Every extracted item is reachable from the review UI.
- A locked item cannot be altered by any code path except an explicit user unlock action.
- Flagged tab shows zero items for a clean, high-confidence extraction.

---

### Feature 6 — Audit Trail Lookup (FR8)

**Provenance:** `docs/archive/specs/spec_feature6.md`; `docs/workbook/feature-6-audit-trail.md`; `docs/issues_charter.md` Steps 2, 4, 8; `docs/fixes.md` §5.

1. Cell selection (workbook or exported metadata) resolves to its full source chain.
2. Source chain displayed with direct link to originating PDF page.
3. Verified/flagged status shown per component.
4. **Export Audit PDF button**: gated on `model_ready` flag. When `!model_ready`, disabled button with tooltip "Generate a model first."
5. Audit trail sheet selector derived dynamically from provenance records (not hardcoded `["Reconciliation", "Source_Inputs"]`).
6. Refresh button to reload provenance.
7. Audit trail resolver uses content-based review IDs (matching Feature 5 §8) — stable across re-runs.
8. Uses `PDF_RENDER_SCALE = 1.5` (same constant as ReviewPage).
9. Canvas size read via `getBoundingClientRect().width/height`.

**Acceptance criteria:**
- Reviewer can trace any flagged number back to its source PDF page in under 10 seconds.
- Export PDF button disabled until model is ready.

---

### Feature 7 — Cross-Year Drift Detection (FR4)

**Provenance:** `docs/archive/specs/spec_feature7.md`; `docs/workbook/feature-7-drift-detection.md`; `docs/business_alignment.md` §2.3 (economic substance drift noted as future concern — NOT yet implemented).

1. Current filing's normalized labels compared against prior-year graph entries using exact string equality on `normalized_label`.
2. Discrepancy flagged when a metric's definition or components changed.
3. New definition linked to the historical graph node.
4. Graph persisted to SQLite/JSON after every update (NFR7).
5. Drift endpoint: single route `POST /drift/jobs/{job_id}/mark-relabeled` (duplicate bare route `POST /drift/{job_id}/mark-relabeled` removed).

**Open Question:** `business_alignment.md` §2.3 notes that exact-string drift detection cries wolf on label cosmetics (economic substance is unchanged). A semantic similarity layer has been proposed but not specified in detail. See `OPEN_QUESTIONS.md` OQ-3.

**Acceptance criteria:**
- Drift history survives a backend restart.
- A known year-over-year redefinition in the benchmark corpus is correctly flagged.
- No duplicate drift routes exist.

---

### Feature 8 — Audit Report Export (FR9)

**Provenance:** `docs/archive/specs/spec_feature8.md`; `docs/workbook/feature-8-audit-report.md`; `docs/issues_charter.md` Steps 2, 13; `docs/fixes.md` §5.3.

1. Compile all cell-level provenance for a completed model via `model_compilation_service.get_or_compile_provenance()` (not directly from `excel_export/` — §3.13 isolation).
2. Render as a structured PDF via ReportLab/WeasyPrint.
3. Include summary of manually overridden items.
4. Expose as a downloadable file from the UI.
5. Route path: `GET /jobs/{job_id}/audit-report` (no `/api/` prefix — consistent with all other routes).

**Acceptance criteria:**
- Report generation succeeds for any model that passed Feature 4/6.
- Every summarized value links back to a real source chain.
- `audit_report/compiler.py` imports nothing from `excel_export/` or `formula_engine/`.

---

### Feature 9 — Evaluation Harness (DEFERRED)

**Provenance:** `docs/spec_feature9.md` (full spec); `docs/business_alignment.md` §1.1; `docs/plan.md` §4 deferral note.

**Status: FROZEN.** The benchmark corpus does not exist. No ground-truth annotations have been produced. Do not add to this harness until a pilot client confirms the pipeline handles their primary use case end-to-end.

The full specification is preserved in `docs/spec_feature9.md`.

---

### Feature 10 — Workflow Pack 2: Capital Structure & Debt Sizing

**Provenance:** `docs/fixes.md` §7, §14.1 (2026-09-02); `docs/business_alignment.md` Steps D, E, F; code commit `2378d0a1` (2026-09-03 — wire footnote debt schedule into capital structure workflow pack).

1. When `workflow_pack == "capital_structure"`, `job_runner.py` invokes `footnote/extractor.py` to extract:
   - Debt schedule tables from Note 8 (Item 8): tranche-by-tranche with coupon rates, maturity dates, outstanding principal, SOFR spreads.
   - ASC 842 lease schedules: operating vs. finance lease split, discount rates, undiscounted future minimum payments by year.
2. Excel output: `debt_schedule_generator.py` — 2-tab: Debt Tranches & Spreads + Lease Waterfall.
3. IB formatting applies (Constitution §2.5): blue = hardcode, black = formula, green = sheet-link.

**Acceptance criteria:**
- Upload with `workflow_pack == "capital_structure"` triggers `footnote/extractor.py`, not the bridge extraction path.
- `footnote/` module endpoints return structured DebtSchedule and LeaseSchedule data.

---

### Feature 11 — EDGAR Direct Integration (Future / Not Yet Implemented)

**Provenance:** `docs/business_alignment.md` §3.2, Step D.

Type a ticker or CIK, select filing period → tool fetches filing directly from EDGAR (EFTS search API, `data.sec.gov/submissions/{CIK}.json`). No PDF download by analyst.

**Status:** Specified in `business_alignment.md` Step D as P1 — Pilot Prerequisite. Not yet implemented. No code exists for this feature.

---

## 5. Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Backend framework | FastAPI | |
| PDF layout parsing | Docling 2.119 | ≥2GB RAM — runs locally, not hosted |
| PDF coordinate utility | PyMuPDF 1.28 | |
| LLM (classification only) | Groq API, `openai/gpt-oss-120b` | Free tier: 30 RPM / 1,000 RPD / 8,000 TPM / 200,000 TPD |
| Formula engine | Custom Python, deterministic pure functions | |
| Excel generation | xlsxwriter 3.2.9 | Creates new workbooks only |
| Graph/state persistence | NetworkX 3.6 + SQLite/JSON | |
| Frontend framework | React 19 + TypeScript | |
| PDF rendering (frontend) | PDF.js (pdfjs-dist 4.10) | `PDF_RENDER_SCALE = 1.5` — shared constant |
| Audit report export | ReportLab 5.0 + WeasyPrint 69 | |
| Type checking | mypy 2.3 (`--strict` on all non-LLM modules) | |
| Linting | ruff 0.16.2, eslint 10 | |
| Testing | pytest 9.1, vitest 4.1 | |
| Build | Vite 8.2 | |

---

## 6. Architecture

### 6.1 Pipeline Stages (by workflow_pack)

**non_gaap_bridge:**
```
Upload → validation → job queue (workflow_pack=non_gaap_bridge)
  → Docling parse → filter is_reconciliation_candidate → confidence score
  → Level 1 alias match → Level 2 Groq (unknowns only)
  → Review UI (flagged items only)
  → read_formula_inputs_from_review (locked items)
  → build_formula_tree (Adjusted EBITDA)
  → bridge_generator.py → 2-tab .xlsx
  → audit_trail, drift, audit_report
```

**capital_structure:**
```
Upload → validation → job queue (workflow_pack=capital_structure)
  → footnote/extractor.py (Note 8 debt + ASC 842 lease tables)
  → Review UI (flagged items)
  → debt_schedule_generator.py → 2-tab .xlsx (Debt Tranches + Lease Waterfall)
```

### 6.2 Module Dependency Rules (per Constitution §3)

```
ingestion/ ← (main.py only)
extraction/ ← ingestion/
classification/ ← extraction/ [models.py only importable downstream]
formula_engine/ ← classification/models.py, extraction/
excel_export/ ← formula_engine/, classification/models.py, extraction/
review/ ← ingestion/, extraction/, classification/
audit_trail/ ← ingestion/, extraction/, review/
drift/ ← ingestion/, review/ [not extraction/, not excel_export/]
audit_report/ ← audit_trail/, extraction/, ingestion/, review/, drift/
                 [via model_compilation_service for excel_export/formula_engine access]
footnote/ ← ingestion/, extraction/
narrative/ ← ingestion/ [deferred from pipeline]
```

### 6.3 Data Models (frozen fields)

**Frozen 5-field schema (Constitution §2.3):**
`value | label | page | bbox | source_file`

**ExtractedRecord additional fields:**
`confidence_score | confidence_band | is_reconciliation_candidate | parser_used`

**JobRecord fields:**
`job_id | filename | file_size_bytes | status | target_metric | workflow_pack | filing_year | company_id | model_ready | model_skip_reason`

**CompanyRecord fields:**
`company_id | name | ticker | created_at | job_ids`
