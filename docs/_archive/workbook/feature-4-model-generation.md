# Engineering Workbook — Feature 4: Deterministic Model Generation

**Module:** Formula Engine & Excel Export (`backend/app/formula_engine/`, `backend/app/excel_export/`)
**Phase:** 2 — Core Trust Loop
**Satisfies:** FR5, FR6
**Status:** Completed
**Author:** Antigravity Engineering

---

## 1. Purpose

Feature 4 is the deterministic formula generation layer. After Feature 3 produces `ClassifiedRecord` objects, Feature 4 reads confirmed and auto-accepted records, builds a pure mathematical formula tree (DAG), and generates a native `.xlsx` workbook where every derived value is a real Excel formula — never a hardcoded number from the classifier.

---

## 2. Scope of Change

### Backend — `backend/app/formula_engine/`

| File | Responsibility |
|---|---|
| `models.py` | `FormulaInputNode`, `FormulaInputBatch`, `FormulaTree`, `FormulaNode`, `FormulaNodeType` |
| `reader.py` | `read_formula_inputs(classified_records)` — includes auto-accepted records; `read_formula_inputs_from_review(items)` — converts locked `ReviewItem`s |
| `tree.py` | `build_formula_tree(batch, target_metric)` — pure function DAG builder; no I/O, no clock, no random (CONSTITUTION §1.4) |

### Backend — `backend/app/excel_export/`

| File | Responsibility |
|---|---|
| `generator.py` | `generate_workbook(tree, job_id, output_dir)` — 2-sheet workbook: `Source_Inputs` (plain values + comments) and `Reconciliation` (cross-sheet refs + SUM) |
| `multi_year_generator.py` | `generate_multi_year_workbook(company, jobs, output_dir)` — multi-year workbook (see ADR-004). **Beta feature, not default path.** |
| `multi_statement_generator.py` | 6-tab institutional model. **Frozen beta — see ADR-003.** |
| `router.py` | `POST /models/{job_id}/generate` and `GET /models/{job_id}/download` |
| `models.py` | `WorkbookGenerationResult`, `W3CAnnotationRecord`, `ModelRepository` |

---

## 3. Excel Output Format (see ADR-002)

### `Source_Inputs` sheet
- Column A: normalized label
- Column F: plain numeric value (`write_number()`, blue font for hardcodes)
- Cell comments: `Source: {source_file} / Page: {page} / BBox: ({x0}, {y0}) → ({x1}, {y1}) / Label: {label}`
- No hyperlinks on source cells.

### `Reconciliation` sheet
- Each line item: `=Source_Inputs!F{row}` (green font — sheet-link per CONSTITUTION §2.5)
- Total row: `=SUM(C{start}:C{end})` (bold, double-underline)
- Sub-totals for aggregate groups

### Provenance
W3C Web Annotation records generated for every cell and persisted to:
`data/results/{job_id}_provenance.json`

---

## 4. Formula Engine Constraints (CONSTITUTION §1.4)

`formula_engine/` functions are **pure**: no I/O, no wall-clock access, no random seeds, no unordered iteration affecting output. Any function that needs these does not belong in this package. Enforced in `mypy --strict`.

---

## 5. Model Generation Flow

```
ClassifiedRecords / ReviewItems (locked)
        │
        ▼
read_formula_inputs() / read_formula_inputs_from_review()
        │
        ▼
FormulaInputBatch (validated, non-empty)
        │
        ▼
build_formula_tree(batch, target_metric="Adjusted EBITDA")
        │
        ▼
FormulaTree (pure DAG, no side effects)
        │
        ▼
generate_workbook(tree, job_id, output_dir)
        │
        ├── Source_Inputs sheet (plain values + comments)
        ├── Reconciliation sheet (cross-sheet refs + SUM)
        └── W3CAnnotationRecord[] → data/results/{job_id}_provenance.json
```

---

## 6. Auto-Draft Generation

The job runner (`job_runner.py`) auto-generates a draft model after classification using `read_formula_inputs(classified_records)` with auto-accepted records. If the batch is non-empty, a draft workbook is created and `job.model_ready = True`. If empty, `model_skip_reason` is set on `JobRecord`.

---

## 7. Test Suite

| File | Coverage |
|---|---|
| `tests/formula_engine/test_reader.py` | Auto-accept passthrough, review item conversion, empty batch handling |
| `tests/formula_engine/test_tree.py` | DAG construction, determinism (identical input → identical tree) |
| `tests/excel_export/test_generator.py` | Source_Inputs plain values, Reconciliation cross-sheet refs, SUM total, provenance records |
| `tests/excel_export/test_router.py` | Generate endpoint, download endpoint, 404/400 edge cases |
