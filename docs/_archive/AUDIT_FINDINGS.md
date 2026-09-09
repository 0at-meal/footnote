# AUDIT_FINDINGS.md — Code vs. Spec vs. Broken Dependencies

> **Audit Date:** 2026-09-09  
> **Spec Reference:** Volume 4 `spec.md` (in `docs/_archive/`)  
> **Code state:** commit `740e17fb` (2026-09-08 23:58) — HEAD  
> **Methodology:** Per-feature inspection of actual code against Volume 4 spec. Requirement drift and implementation breakage diagnosed separately.

---

## Legend

| Symbol | Meaning |
|---|---|
| ✅ | Matches current spec, working |
| ⚠️ | Matches current spec requirement, but broken/buggy (implementation issue) |
| ❌ | Does NOT match current spec (implements older/wrong requirement) |
| ➕ | Exists in code but not in any spec version (undocumented scope creep) |
| ➖ | Specified but not yet implemented |
| 🔧 | Partially matches spec — some sub-requirements met, others not |

---

## Part 1 — Feature Audit

### Feature 1: Multi-File PDF Upload & Job Queueing

| Sub-Requirement | Code Status | Evidence | Severity |
|---|---|---|---|
| Drag/drop + file-select upload zone | ✅ Working | `UploadZone.tsx` | — |
| Server-side PDF validation + error message | ✅ Working | `ingestion/router.py` | — |
| Job persistence (filename, size, status) | ✅ Working | `ingestion/repository.py`, `data/jobs.json` | — |
| `workflow_pack` field on JobRecord (spec FR10) | ✅ Working | `ingestion/models.py`; `job_runner.py` uses `getattr(job, "workflow_pack", "non_gaap_bridge")` | — |
| Workflow Pack Selector UI (upload form) | 🔧 Partial | Backend supports `workflow_pack`; frontend `UploadZone.tsx` may not yet expose three-option selector — `fixes.md` §7.4 ticket not confirmed as implemented | Degraded |
| Company/fiscal year assignment at upload | ✅ Working | ADR-004 implemented; `CompanySelector.tsx`, `filing_year` on `JobRecord` | — |
| `model_skip_reason` populated in job | 🔧 Partial | Field exists on `JobRecord`; `job_runner.py` appears to set it (see code §6.1 context) — not confirmed visible in `JobList.tsx` | Degraded |
| Target metric field — informational only | ✅ Working | `updates.md` taxonomy migration done; `target_metric` retained for backward compat | — |

**Overall F1 Status: 🔧 — mostly working but workflow_pack UI exposure unconfirmed**

---

### Feature 2: Layout-Aware Extraction

| Sub-Requirement | Code Status | Evidence | Severity |
|---|---|---|---|
| Docling structural parse | ✅ Working | `extraction/docling_parser.py` — Docling integrated | — |
| PyMuPDF bounding box extraction | ⚠️ Buggy | `_parse_pdf_with_pymupdf()` loop uses `range(1, len(extracted))` AND `range(1, len(row))` — 1-based. `flat_idx = row_idx * num_cols + col_idx` with `row_idx` starting at 1: first data row idx=1, first col idx=1 → flat_idx=1*n+1. This skips cell at index 0 and produces wrong indices. **This bug is confirmed still present in HEAD (not fixed despite Issues Charter Step 1, Ticket 1.1).** | **Blocking** |
| Y-axis inversion for Docling coordinates | ✅ Working | `coordinate_normalizer.py` implements `y0_screen = 1000.0 - y1_raw` conditioned on `item.parser_used == "docling"` | — |
| `parser_used` field on DoclingItem | ✅ Working | Field present; set to `"docling"` or `"pymupdf"` in parser | — |
| `is_reconciliation_candidate` tag | ✅ Working | ADR-001 implemented; `_is_reconciliation_table()` pure function; field propagated | — |
| 3-tier confidence bands (0.95/0.65) | ✅ Working | `extraction/confidence.py` | — |
| Reconciliation table confidence bonus (+0.15) | ✅ Working | `issues_charter.md` Ticket 3.3 — bonus applied in `confidence.py` | — |
| Workflow-pack routing for extraction | ✅ Working | `job_runner.py` line 87: reads `workflow_pack`; routes `capital_structure` to `footnote/extractor.py` | — |
| `parser_used` warning banner in Review UI | ➖ Not confirmed | `ReviewPage.tsx` has the import of `PDF_RENDER_SCALE` but the `parser_used` banner (Issues Charter Step 5) is not confirmed implemented | Cosmetic |

**Overall F2 Status: ⚠️ — Y-inversion fixed, but PyMuPDF cell indexing bug is STILL PRESENT (blocking)**

---

### Feature 3: Classification & Normalization

| Sub-Requirement | Code Status | Evidence | Severity |
|---|---|---|---|
| Master Financial Taxonomy (60–80 items) | ✅ Working | `classification/models.py` has `StatementType`, `TaxonomyItem`, `MasterTaxonomy`. `backend/data/taxonomy.json` exists | — |
| Two-level pipeline (alias match first) | ✅ Working | `classification/dispatcher.py` + `taxonomy.py` — `match_master_taxonomy()` implemented | — |
| Groq for unknowns only | ✅ Working | `dispatcher.py` — Groq call gated on Level 1 miss | — |
| Classifier return type — no numeric field | ✅ Working | `ClassifiedRecord` model has no numeric output field | — |
| JSONL decision log | ✅ Working | `classification/decision_log.py` | — |
| Unrecognized labels → pending_taxonomy_confirmation | ✅ Working | `classification/normalizer.py` | — |
| `is_target_metric_candidate_item()` tightened | ❌ Mismatch | Spec F3.8 requires: gate on `is_reconciliation_candidate` as primary signal; remove broad keyword fallback. **Current code: the function gates on `is_reconciliation_candidate` first (✅) but then falls through to a keyword check on `table_name` (returns True for any table with "reconciliation", "non-gaap", "non gaap", "bridge" in its name). This keyword fallback was supposed to be REMOVED per issues_charter.md Ticket 3.2.** The fallback is narrowed compared to original, but still applies even when `is_reconciliation_candidate == False`. | Degraded |
| `isFlagged` frontend predicate (status-based) | ✅ Working | `ReviewPage.tsx` uses status-based predicate (confirmed in code inspection) | — |

**Overall F3 Status: 🔧 — core working, but `is_target_metric_candidate_item()` keyword fallback not fully removed (Ticket 3.2 incomplete)**

---

### Feature 4: Deterministic Model Generation

| Sub-Requirement | Code Status | Evidence | Severity |
|---|---|---|---|
| 2-tab Excel output for non_gaap_bridge | ✅ Working | `bridge_generator.py` exists and is routed from `job_runner.py` when `workflow_pack == "non_gaap_bridge"` | — |
| `bridge_generator.py` is default pipeline path | ✅ Working | `job_runner.py` line 265: `generate_bridge_workbook()` called for `non_gaap_bridge` | — |
| `multi_statement_generator.py` NOT default | ❌ Mismatch | `job_runner.py` line 295: when `workflow_pack != "non_gaap_bridge"` AND `workflow_pack != "capital_structure"`, falls through to `generate_multi_statement_workbook()`. For the `cash_conversion` pack (not yet fully spec'd), the 6-tab generator is the fallback. **ADR-003 guard rail violation for `cash_conversion` pack.** | Degraded |
| Plain numeric values + cell comments (ADR-002) | ✅ Working | `bridge_generator.py` uses `write_number()` + `write_comment()` | — |
| Cross-sheet references on Reconciliation sheet | ✅ Working | `bridge_generator.py` uses `write_formula("=Source_Inputs!...")` | — |
| W3C provenance records persisted | ✅ Working | `excel_export/provenance.py`; records saved to `data/results/{job_id}_provenance.json` | — |
| `debt_schedule_generator.py` for capital_structure | ✅ Working | `job_runner.py` routes capital_structure to `debt_schedule_generator.py` via `footnote/extractor.py` | — |
| `_parse_numeric_value()` deduplicated | ❌ Mismatch | `fixes.md` §8.1 calls for deduplication. `excel_export/utils.py` exists but it is NOT confirmed that all three generators import from it. `generator.py` and `multi_year_generator.py` still exist with original copies. | Cosmetic |

**Overall F4 Status: 🔧 — non_gaap_bridge path correct; multi_statement fallback for cash_conversion violates ADR-003**

---

### Feature 5: Extraction Review UI

| Sub-Requirement | Code Status | Evidence | Severity |
|---|---|---|---|
| PDF.js page rendering | ✅ Working | `ReviewPage.tsx` uses `renderPage()` from `lib/pdf/renderer.ts` | — |
| `PDF_RENDER_SCALE = 1.5` shared constant | ✅ Working | `renderer.ts` exports `PDF_RENDER_SCALE = 1.5`; `ReviewPage.tsx` imports it | — |
| Canvas size via `getBoundingClientRect()` | ✅ Working | `ReviewPage.tsx` uses `canvasRef.current.getBoundingClientRect()` | — |
| Status-based `isFlagged` predicate | ✅ Working | `ReviewPage.tsx` — confirmed status-based | — |
| Auto-lock auto_accepted + matched items | ✅ Working | `review/repository.py` — "Ticket 2.1: auto_accepted + matched items are pre-locked" comment confirms implementation | — |
| Confirm / edit / flag actions | ✅ Working | `review/repository.py` has `confirm_item()`, `flag_item()`, `edit_item()` | — |
| Content-hash review item IDs | ✅ Working | `review/repository.py` — `sha256` hash function found in code | — |
| Inline errors (not `alert()`) | 🔧 Unconfirmed | `fixes.md` §9.1 calls for replacing `alert()` with `setEditError()`. Not confirmed in current `ReviewPage.tsx` — needs direct line check | Cosmetic |
| Empty Flagged tab "Generate Model" button | 🔧 Unconfirmed | `fixes.md` §9 Step 9 ticket — not confirmed implemented | Cosmetic |
| Progress pulse on Extracting badge | 🔧 Unconfirmed | `fixes.md` §9.2 — CSS animation not confirmed | Cosmetic |
| Target metric warning banner | 🔧 Unconfirmed | `fixes.md` §9.4 Ticket 19 — not confirmed | Cosmetic |
| PyMuPDF warning banner | 🔧 Unconfirmed | `fixes.md` §9.5 Ticket 5 — not confirmed | Cosmetic |

**Overall F5 Status: ✅ for core functionality; 🔧 for UX polish items (unconfirmed)**

---

### Feature 6: Audit Trail Lookup

| Sub-Requirement | Code Status | Evidence | Severity |
|---|---|---|---|
| Source chain resolution | ✅ Working | `audit_trail/resolver.py` | — |
| PDF bbox highlighting in AuditTrailView | ✅ Working | `AuditTrailView.tsx` uses `PDF_RENDER_SCALE` from `renderer.ts`; `getBoundingClientRect()` | — |
| Export PDF button gated on `model_ready` | ✅ Working | `AuditTrailView.tsx` — `isModelReady` derived from `model_ready`; `canDownload` controls button | — |
| Dynamic sheet selector | 🔧 Unconfirmed | `fixes.md` §9.3 — replacing hardcoded `["Reconciliation", "Source_Inputs"]` with dynamic derivation. Not confirmed from inspection. | Cosmetic |
| Refresh button | 🔧 Unconfirmed | `fixes.md` §5.3 — not confirmed | Cosmetic |
| `model_compilation_service` used (not direct imports) | ✅ Working | `audit_report/compiler.py` imports from `app.model_compilation_service` | — |

**Overall F6 Status: ✅ for critical path; 🔧 for 2 UX items unconfirmed**

---

### Feature 7: Cross-Year Drift Detection

| Sub-Requirement | Code Status | Evidence | Severity |
|---|---|---|---|
| Normalized label comparison | ✅ Working | `drift/` module | — |
| Discrepancy flagging | ✅ Working | `drift/repository.py`, `DriftFlag` model | — |
| Graph persistence to SQLite | ✅ Working | NetworkX + SQLite implemented | — |
| Duplicate route removed | ✅ Working | Only `POST /drift/jobs/{job_id}/mark-relabeled` exists — no bare `/{job_id}/mark-relabeled` in current inspection | — |
| Drift router global state pattern | ⚠️ Buggy | `drift/router.py` still uses `global _drift_repo`, `global _job_repo`, etc. — DI not converted to `Depends()`. `fixes.md` §10.5 calls for fixing this. | Degraded |

**Overall F7 Status: 🔧 — functional but drift router global state not fixed**

---

### Feature 8: Audit Report Export

| Sub-Requirement | Code Status | Evidence | Severity |
|---|---|---|---|
| PDF compile via ReportLab/WeasyPrint | ✅ Working | `audit_report/` module | — |
| `audit_report/compiler.py` isolation | ✅ Working | Confirmed: compiler.py imports from `app.model_compilation_service` — NOT directly from `excel_export/` or `formula_engine/` | — |
| Route normalization (`/jobs/{id}/audit-report`, no `/api/` prefix) | 🔧 Unconfirmed | `fixes.md` §12 — not confirmed from inspection | Cosmetic |
| `model_compilation_service.py` uses deprecated `generator.py` | ❌ Mismatch | `model_compilation_service.py` imports `from app.excel_export.generator import generate_workbook` — uses the **deprecated** `generator.py`, NOT `bridge_generator.py`. This means the on-the-fly compilation path uses an outdated generator. | Degraded |

**Overall F8 Status: 🔧 — isolation fixed, but service uses deprecated generator**

---

### Feature 9: Evaluation Harness

| Sub-Requirement | Code Status | Evidence | Severity |
|---|---|---|---|
| Harness frozen | ✅ Working | `docs/plan.md` deferral note; `eval/README.md` freeze notice | — |
| Code preserved but not active | ✅ Working | `eval/` directory exists with full harness code | — |
| Corpus does not exist | ➖ Expected absence | `eval/corpus/` empty — correct per freeze decision | — |

**Overall F9 Status: ✅ (frozen as intended)**

---

### Feature 10: Workflow Pack 2 — Capital Structure

| Sub-Requirement | Code Status | Evidence | Severity |
|---|---|---|---|
| `footnote/extractor.py` wired to capital_structure pack | ✅ Working | `job_runner.py` line 200: `if workflow_pack == "capital_structure"`: imports and calls `footnote/extractor.py` | — |
| `debt_schedule_generator.py` generates output | ✅ Working | `excel_export/debt_schedule_generator.py` exists; wired in `job_runner.py` | — |
| `footnote/router.py` uses `Depends()` (not singletons) | ✅ Working | Confirmed from inspection — `footnote/router.py` uses `Annotated[..., Depends(...)]` pattern | — |

**Overall F10 Status: ✅ — wired and working**

---

### Undocumented Features (➕ In Code But Not Spec)

| Module | What It Does | Spec Status | Concern |
|---|---|---|---|
| `narrative/` | MD&A diffing, risk factor redlines | Deferred — mentioned in `business_alignment.md` but explicitly not wired | Code exists, endpoints accessible, but not in primary pipeline. This is intentional per `fixes.md` §14.2. |
| `excel_export/multi_statement_generator.py` | 6-tab comprehensive model | Beta/frozen per ADR-003 | Code exists; routed as fallback for unimplemented `cash_conversion` pack — unintended ADR-003 violation |
| `excel_export/generator.py` (deprecated) | Original 2-tab generator | Deprecated | Still imported by `model_compilation_service.py` — should be `bridge_generator.py` |
| `excel_export/multi_year_generator.py` (deprecated) | Multi-year single-sheet model | Deprecated label | Still called by `company_router.py` `POST /companies/{id}/multi-year-model` — intentional for company-level multi-year |

---

## Part 2 — Dependency & Technical Breakage Audit

### D1 — PyMuPDF Fallback 1-Based Indexing Bug (**BLOCKING**)

| Attribute | Detail |
|---|---|
| **File** | `backend/app/extraction/docling_parser.py` |
| **Bug** | `_parse_pdf_with_pymupdf()`: outer row loop is `for row_idx in range(1, len(extracted))` AND inner col loop is `for col_idx in range(1, len(row))`. Both start at 1 (row 0 = header row skipped, but col 0 = label column skipped means first data column is col 1 ✓). The `flat_idx = row_idx * num_cols + col_idx` computation: for row_idx=1, col_idx=1 → flat_idx=n+1 (skips cell 0). For a 4-col table, row 1 col 1 → idx 5 instead of idx 1 (= row 1 × 4 + 1 = 5). This assigns wrong bbox to every cell. |
| **Fix per issues_charter** | Step 1, Ticket 1.1: Change loop to `range(0, len(extracted))` for rows (or keep 1-based row skip but correct formula) and `range(1, len(row))` for cols (correct — col 0 is label). Fix formula to `flat_idx = (row_idx - 1) * num_cols + (col_idx - 1)` where `row_idx` and `col_idx` start at 1. |
| **Severity** | **BLOCKING** — every PDF using PyMuPDF fallback gets wrong bbox; highlights appear at wrong cell position in review UI |
| **Effort** | Small (2 lines) |

---

### D2 — `model_compilation_service.py` Uses Deprecated Generator

| Attribute | Detail |
|---|---|
| **File** | `backend/app/model_compilation_service.py` |
| **Bug** | Line: `from app.excel_export.generator import generate_workbook`. This imports `generator.py` which is marked DEPRECATED in its own docstring. Should import from `bridge_generator.py` which is the current default. The on-the-fly compilation path (used by audit trail) produces workbooks via the deprecated generator format (which may differ from `bridge_generator.py` output format). |
| **Fix** | Replace `from app.excel_export.generator import generate_workbook` with `from app.excel_export.bridge_generator import generate_bridge_workbook` and update the call. |
| **Severity** | Degraded — audit trail compilation uses stale generator |
| **Effort** | Small |

---

### D3 — `drift/router.py` Global State Pattern (DI Violation)

| Attribute | Detail |
|---|---|
| **File** | `backend/app/drift/router.py` |
| **Bug** | Module-level `global _drift_repo`, `_job_repo`, `_review_repo`, `_drift_graph_override`. `set_drift_repository()`, `set_job_repository()`, etc. use `global` state. This bypasses FastAPI's `app.dependency_overrides` mechanism, making the router untestable without global mutation. |
| **Fix** | `fixes.md` §10.5: Replace with `Depends()` injection pattern. |
| **Severity** | Degraded — untestable, potential thread-safety issue |
| **Effort** | Medium |

---

### D4 — `excel_export/router.py` Global Mutable Repository

| Attribute | Detail |
|---|---|
| **File** | `backend/app/excel_export/router.py` |
| **Bug** | `set_model_repository()` uses `global _model_repo`. The endpoints use `Depends(get_model_repository)` (pattern is partially correct) but the override setter is still global. |
| **Severity** | Degraded — test isolation broken |
| **Effort** | Small |

---

### D5 — `is_target_metric_candidate_item()` Keyword Fallback Incompletely Removed

| Attribute | Detail |
|---|---|
| **File** | `backend/app/classification/normalizer.py` |
| **Bug** | After gating on `is_reconciliation_candidate`, the function falls through to check `table_name` for keywords ("reconciliation", "non-gaap", "bridge"). This should have been removed per issues_charter Ticket 3.2. It creates false positives for tables whose names happen to include those terms but are not the primary reconciliation table. |
| **Fix** | Remove the keyword fallback: if `is_reconciliation_candidate == False`, return `False` immediately. |
| **Severity** | Degraded — review queue may still show non-reconciliation items |
| **Effort** | Small |

---

### D6 — `multi_statement_generator.py` as Fallback for Unimplemented `cash_conversion`

| Attribute | Detail |
|---|---|
| **File** | `backend/app/job_runner.py` |
| **Bug** | When `workflow_pack` is neither `non_gaap_bridge` nor `capital_structure`, `job_runner.py` falls through to `generate_multi_statement_workbook()` (the 6-tab generator). This means `cash_conversion` jobs (if ever submitted) would use the frozen 6-tab generator. ADR-003 guard rail violation. |
| **Fix** | For `cash_conversion` (and any other pack), return a `model_skip_reason = "workflow_pack cash_conversion not yet implemented"` rather than falling back to `multi_statement_generator.py`. |
| **Severity** | Degraded (currently low impact since `cash_conversion` UI not exposed) |
| **Effort** | Small |

---

### D7 — `narrative/router.py` DI Pattern (Non-Blocking — Deferred Module)

| Attribute | Detail |
|---|---|
| **File** | `backend/app/narrative/router.py` |
| **Status** | Has `get_job_repository()` and `get_narrative_repository()` as module-level functions returning instances (not `global` singletons but still not using `Depends()` pattern). The endpoints DO appear to use `Depends()`. This may be resolved — needs verification. |
| **Severity** | Low (module deferred from pipeline) |
| **Effort** | Small |

---

### D8 — `model_compilation_service.py` Still References Deprecated API

| Attribute | Detail |
|---|---|
| **File** | `backend/app/model_compilation_service.py` |
| **Bug** | Imports `generate_workbook` from deprecated `generator.py`. Also note: the audit trail's on-the-fly compilation uses `build_formula_tree` with a hardcoded target metric path that may not correctly route `workflow_pack=capital_structure` jobs. |
| **Severity** | Degraded |
| **Effort** | Small |

---

## Part 3 — Findings Summary Table

| Feature/Area | Status | Matches Spec? | Broken? | Severity | Effort |
|---|---|---|---|---|---|
| F1 Upload & Queueing | 🔧 | Mostly | `workflow_pack` UI selector unconfirmed | Degraded | Small |
| F2 Extraction (Docling path) | ✅ | Yes | No | — | — |
| F2 Extraction (PyMuPDF fallback) | ⚠️ | Yes | **YES — 1-based indexing bug** | **Blocking** | Small |
| F2 Y-axis inversion fix | ✅ | Yes | No | — | — |
| F2 `is_reconciliation_candidate` | ✅ | Yes | No | — | — |
| F3 Master Taxonomy (60–80 items) | ✅ | Yes | No | — | — |
| F3 Two-level pipeline (alias first) | ✅ | Yes | No | — | — |
| F3 `is_target_metric_candidate` tightening | ❌ | Partial | Keyword fallback not removed | Degraded | Small |
| F4 `bridge_generator.py` default | ✅ | Yes | No | — | — |
| F4 `multi_statement` NOT default | ❌ | No (fallback for cash_conv) | ADR-003 violation | Degraded | Small |
| F4 2-tab format (ADR-002) | ✅ | Yes | No | — | — |
| F4 Utility function deduplication | ❌ | No | `_parse_numeric_value()` still in 3 files | Cosmetic | Small |
| F5 Review UI core | ✅ | Yes | No | — | — |
| F5 `isFlagged` predicate | ✅ | Yes | No | — | — |
| F5 Auto-lock auto_accepted+matched | ✅ | Yes | No | — | — |
| F5 Content-hash review IDs | ✅ | Yes | No | — | — |
| F5 Scale fix + canvas size fix | ✅ | Yes | No | — | — |
| F5 UX polish (inline errors, banners, etc.) | 🔧 | Partial | Several unconfirmed | Cosmetic | Small |
| F6 Audit trail core | ✅ | Yes | No | — | — |
| F6 Export PDF gating | ✅ | Yes | No | — | — |
| F6 Dynamic sheet selector | 🔧 | Unconfirmed | Not verified | Cosmetic | Small |
| F7 Drift detection | ✅ | Yes | No | — | — |
| F7 Duplicate route | ✅ | Fixed | No | — | — |
| F7 Global state in drift router | ⚠️ | No | Yes — global state | Degraded | Medium |
| F8 Audit report | ✅ | Yes | No | — | — |
| F8 `audit_report/compiler.py` isolation | ✅ | Yes | No | — | — |
| F8 `model_compilation_service` generator | ❌ | No | Uses deprecated `generator.py` | Degraded | Small |
| F9 Eval harness frozen | ✅ | Yes | No | — | — |
| F10 Capital structure pack | ✅ | Yes | No | — | — |
| `narrative/` deferred | ✅ | Yes | No | — | — |
| `multi_statement` generator (beta) | ❌ | Partial | ADR-003 violation as cash_conv fallback | Degraded | Small |
| Health check `db_ok` logic | ✅ | Fixed | No | — | — |
| CORS configurable | ✅ | Fixed | No | — | — |
| `drift/router.py` DI | ❌ | No | Global state | Degraded | Medium |
| `excel_export/router.py` DI | ❌ | No | Global state | Degraded | Small |
| Route prefix normalization | 🔧 | Unconfirmed | Not verified | Cosmetic | Small |
