# REMEDIATION_PLAN.md — Prioritized Fix Plan

> **Produced:** 2026-09-09  
> **Based on:** `AUDIT_FINDINGS.md` (Volume 4 audit)  
> **Ordering rules (per task instructions):**  
> (a) Blocking issues first  
> (b) Dependency/library fixes before feature fixes where a broken library masks real feature state  
> (c) Everything else by severity then effort  
> **Rule:** Do not write or modify application code until this plan receives explicit human go-ahead (see `OPEN_QUESTIONS.md` for decisions needed first).

---

## Phase R1 — P0 Blocking: PyMuPDF Cell Indexing Bug

**Why first:** The PyMuPDF fallback assigns the wrong bounding box to every extracted cell. Every PDF that goes through the fallback path produces systematically wrong bbox highlights in the review UI. No other remediation item matters for review UX correctness until this is fixed — it masks whether ALL subsequent bbox-related bugs are real or artifacts.

| # | Ticket | File | Change | Effort |
|---|---|---|---|---|
| R1.1 | Fix PyMuPDF 1-based loop → 0-based formula | `backend/app/extraction/docling_parser.py` | In `_parse_pdf_with_pymupdf()`: keep `for row_idx in range(1, len(extracted))` (row 0 is header), keep `for col_idx in range(1, len(row))` (col 0 is label). Fix `flat_idx` formula: `flat_idx = (row_idx - 1) * num_cols + (col_idx - 1)`. This makes row_idx=1, col_idx=1 → flat_idx=0 (first data cell). | Small |
| R1.2 | Write unit test for per-cell bbox indexing | `backend/tests/extraction/test_coordinate_normalizer.py` (or `test_docling_parser.py`) | Mock a 3×4 table; assert each cell gets the correct bbox. Issues Charter Ticket 1.4 fixture test. | Small |

**Verification:** After this fix, run a known PDF through the pipeline and confirm that extracted cell bboxes match the actual cell positions when highlighted in the review UI.

**Gate:** Phases R2+ do not begin until R1 is verified on a real PDF.

---

## Phase R2 — P0: Fix `model_compilation_service.py` — Deprecated Generator

**Why second:** The `model_compilation_service.py` uses the deprecated `generator.py` instead of `bridge_generator.py`. The audit trail's on-the-fly model compilation produces workbooks via the old generator. This is a single-import change with no UX change, and it's a prerequisite for trusting audit trail output.

| # | Ticket | File | Change | Effort |
|---|---|---|---|---|
| R2.1 | Replace deprecated generator import | `backend/app/model_compilation_service.py` | Replace `from app.excel_export.generator import generate_workbook` with `from app.excel_export.bridge_generator import generate_bridge_workbook`. Update the `generation_result = generate_workbook(...)` call to `generate_bridge_workbook(...)`. Verify the function signature matches. | Small |
| R2.2 | Update test if exists | `backend/tests/` (any test that mocks `generate_workbook` in service context) | Update mock target if tests exist. | Small |

---

## Phase R3 — P0: Fix `is_target_metric_candidate_item()` Keyword Fallback

**Why third:** The review queue overcrowding is a P0 UX demo-blocker (business_alignment.md §2.2). The keyword fallback in `normalizer.py` causes non-reconciliation items to appear in the review queue even when `is_reconciliation_candidate == False`. This directly inflates the Flagged tab.

| # | Ticket | File | Change | Effort |
|---|---|---|---|---|
| R3.1 | Remove keyword fallback from `is_target_metric_candidate_item()` | `backend/app/classification/normalizer.py` | After the `if record.is_reconciliation_candidate or record.record.is_reconciliation_candidate: return True` gate, remove the keyword-based fallback that checks `table_lower` for "reconciliation", "non-gaap", "bridge". If `is_reconciliation_candidate == False`, return `False`. The reconciliation tag from the parser is the authoritative signal. | Small |
| R3.2 | Update tests | `backend/tests/classification/` | Ensure existing tests that relied on keyword fallback are updated to reflect the structural signal. | Small |

---

## Phase R4 — P1: Fix `multi_statement_generator.py` as `cash_conversion` Fallback

**Why:** ADR-003 violation. The 6-tab generator must not be the default fallback for any unimplemented pack. Return a clear skip reason instead.

| # | Ticket | File | Change | Effort |
|---|---|---|---|---|
| R4.1 | Replace 6-tab fallback with skip reason | `backend/app/job_runner.py` | In the `else` branch (after `non_gaap_bridge` and `capital_structure` routing), replace `generate_multi_statement_workbook()` call with: `model_skip_reason = f"Workflow pack '{workflow_pack}' is not yet fully implemented. No model generated."` and skip generation. Do not import or call `multi_statement_generator`. | Small |
| R4.2 | Remove now-unused top-level import if applicable | `backend/app/job_runner.py` | If `generate_multi_statement_workbook` is no longer called from any active code path, remove the import (but retain the module on disk per ADR-003). | Small |

---

## Phase R5 — P1: Fix DI Pattern in `drift/router.py`

**Why:** Global state pattern bypasses `app.dependency_overrides`, making the module untestable and creating thread-safety risk. This is a prerequisite for writing any meaningful tests for drift endpoints.

| # | Ticket | File | Change | Effort |
|---|---|---|---|---|
| R5.1 | Convert `_drift_repo` to `Depends()` | `backend/app/drift/router.py` | Define `get_drift_repository()`, `get_job_repository()`, `get_review_repository()`, `get_drift_graph()` as dependency provider functions. Inject via `Annotated[T, Depends(get_x)]` in each endpoint signature. Remove all `global` declarations and `set_*` mutator functions. | Medium |
| R5.2 | Write or update router tests | `backend/tests/drift/test_router.py` | Verify endpoints work with `app.dependency_overrides` for isolation. | Medium |

---

## Phase R6 — P1: Fix DI Pattern in `excel_export/router.py`

| # | Ticket | File | Change | Effort |
|---|---|---|---|---|
| R6.1 | Clarify or remove `set_model_repository()` global setter | `backend/app/excel_export/router.py` | If `set_model_repository()` is only used in tests, replace with `app.dependency_overrides[get_model_repository] = lambda: mock_repo` in tests. Remove the `global _model_repo` pattern. The endpoint injection via `Depends(get_model_repository)` is already correct — just remove the global override mechanism. | Small |

---

## Phase R7 — P2: Confirm and Complete UX Polish Items

These are lower-severity items that have been in the fixes.md roadmap but whose implementation in the current codebase is unconfirmed from the audit. Each should be verified first; if not implemented, implement.

| # | Ticket | Spec Ref | What to Confirm / Implement | Effort |
|---|---|---|---|---|
| R7.1 | Verify/implement workflow_pack UI selector in UploadZone | `spec.md` F1; `fixes.md` §7.4 | `UploadZone.tsx` should have a three-option selector for `non_gaap_bridge`, `capital_structure`, `cash_conversion`. If not present, add it. | Small |
| R7.2 | Verify/implement `model_skip_reason` surface in `JobList.tsx` | `fixes.md` §6.2 | When `status === 'done' && !model_ready`, render info icon with tooltip showing `model_skip_reason`. | Small |
| R7.3 | Verify/implement inline errors replacing `alert()` | `fixes.md` §9.1 | `ReviewPage.tsx`: confirm `alert()` → `setEditError()` migration. | Small |
| R7.4 | Verify/implement Empty Flagged tab "Generate Model" button | `fixes.md` §9 Step 9 | When `activeTab === 'flagged'` and flagged list is empty, show "Approve & Generate" button. | Small |
| R7.5 | Verify/implement progress pulse on Extracting badge | `fixes.md` §9.2 | CSS `@keyframes` pulse on `.status-badge--extracting`. | Small |
| R7.6 | Verify/implement target metric warning banner | `fixes.md` §9.4 | Amber banner when `target_metric_found === false`. Requires: backend `target_metric_found` in `ExtractionSummary`, exposed in `ReviewItemsResponse`, rendered in `ReviewPage.tsx`. | Medium |
| R7.7 | Verify/implement PyMuPDF warning banner | `fixes.md` §9.5 | Amber banner when `parser_used === "pymupdf"` or `"mixed"`. | Small |
| R7.8 | Verify/implement dynamic audit trail sheet selector | `fixes.md` §9.3 | Replace hardcoded `["Reconciliation", "Source_Inputs"]` with dynamic derivation from provenance records. | Small |
| R7.9 | Verify/implement Refresh button in AuditTrailView | `fixes.md` §5.3 | Extract `loadProvenance()` callable; add Refresh button. | Small |
| R7.10 | Verify route prefix normalization | `fixes.md` §12 | Confirm `/api/jobs/{id}/audit-report` vs `/jobs/{id}/audit-report` — remove `/api/` prefix variant. | Small |

---

## Phase R8 — P2: Code Quality / Deduplication

These do not affect runtime behavior but reduce maintenance risk.

| # | Ticket | File | Change | Effort |
|---|---|---|---|---|
| R8.1 | Deduplicate `_parse_numeric_value()` | `backend/app/excel_export/utils.py` | Confirm the function is in `utils.py`. Update `generator.py`, `multi_year_generator.py`, and `multi_statement_generator.py` to import from `excel_export.utils`. Resolve the 0-vs-2 decimal format per OQ-7 decision. | Small |
| R8.2 | Deduplicate `_col_to_letter()` and `_to_cell_coord()` | `backend/app/excel_export/utils.py` | Same approach — move to `utils.py`, import in all generators. | Small |
| R8.3 | Archive or document `fixes_implementation.md` (root) | Root / `docs/_archive/` | Review content for unique information; archive or delete (per OQ-10 decision). | Small |

---

## Phase R9 — P3: Verification and Documentation Update

After all remediation phases:

| # | Action | Detail |
|---|---|---|
| R9.1 | Run full test suite | `pytest backend/tests/ -v`, `mypy --strict` on all affected modules, `ruff check backend/`, `npx tsc --noEmit`, `npm test` |
| R9.2 | Manual smoke test: non_gaap_bridge pack | Upload a real 10-K → verify bbox highlights are correct → verify review queue shows only genuinely flagged items → verify model generates and downloads as 2-tab workbook |
| R9.3 | Manual smoke test: capital_structure pack | Upload a real 10-K → verify `footnote/extractor.py` runs → verify `debt_schedule_generator.py` produces output |
| R9.4 | Update `docs/CONSTITUTION.md`, `docs/plan.md`, `docs/spec.md` | Replace the in-place files with the Volume 4 versions from `docs/_archive/`. This is the re-baseline step — do not do this before remediation verification. |
| R9.5 | Create `docs/_archive/` index | Ensure `PROVENANCE.md`, `TIMELINE.md`, `OPEN_QUESTIONS.md`, `AUDIT_FINDINGS.md`, `REMEDIATION_PLAN.md` are all committed to `docs/_archive/` with a single conventional commit: `docs(rebaseline): archive Volume 4 SDD deliverables` |

---

## Remediation Summary Table

| Phase | Items | Priority | Total Effort | Blocking? |
|---|---|---|---|---|
| R1 | PyMuPDF bbox indexing fix | P0 | Small | **YES** |
| R2 | `model_compilation_service` deprecated generator | P0 | Small | Yes |
| R3 | `is_target_metric_candidate` keyword fallback | P0 | Small | Yes (UX demo) |
| R4 | `multi_statement` as `cash_conversion` fallback | P1 | Small | No |
| R5 | `drift/router.py` DI global state | P1 | Medium | No |
| R6 | `excel_export/router.py` DI global state | P1 | Small | No |
| R7 | UX polish verification/completion (10 items) | P2 | Small×9 + Medium×1 | No |
| R8 | Code quality / deduplication (3 items) | P2 | Small | No |
| R9 | Verification + doc re-baseline | P3 | Medium | No |

**Total blocking items: 3 (R1, R2, R3)**  
**Estimated total effort: ~3 small fixes (P0) + 1 medium + ~12 small verification/implement tickets**  
**Recommended minimum before demo: R1 + R3 (bbox fix + review queue fix) — these are the two P0 demo-blockers**

---

## Pre-Requisites for Starting Code Changes

Before any code is written:

1. **OQ-1** must be answered (legacy job workflow_pack default).
2. **OQ-7** must be answered (0 vs. 2 decimal places) before R8.1.
3. Human must explicitly approve this remediation plan (per task ground rules).
4. The OPEN_QUESTIONS.md should be reviewed and any blocking OQs resolved for the specific phase being started.

The Volume 4 baseline documents (`docs/_archive/CONSTITUTION.md`, `spec.md`, `plan.md`) should be moved to replace the existing `docs/` versions only after R9.1–R9.3 pass — not before.
