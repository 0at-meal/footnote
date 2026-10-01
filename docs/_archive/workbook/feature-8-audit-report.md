# Engineering Workbook — Feature 8: Audit Report Export

**Module:** Audit Report (`backend/app/audit_report/`)
**Phase:** 4 — Extensibility & Compliance Output
**Satisfies:** FR9 (compliance evidence layer)
**Status:** Completed (with known issues — see below)
**Author:** Antigravity Engineering

---

## 1. Purpose

Feature 8 generates a structured, downloadable compliance-style PDF report for a completed model. It assembles data from all upstream pipeline stages (job metadata, formula cells, source chain, review history, classifier governance log, drift flags) and renders a multi-section PDF via ReportLab or WeasyPrint.

---

## 2. Scope of Change

### Backend — `backend/app/audit_report/`

| File | Responsibility |
|---|---|
| `models.py` | `AuditReportMetadata`, `AuditReportSection`, `AuditReportSectionType` |
| `compiler.py` | `compile_report_data(job_id)` — collects metadata, formula cells, source chains, review history, classifier logs, drift summary |
| `renderer.py` | `render_pdf(report_data, output_path)` — produces binary PDF; multi-page tables with repeated column headers |
| `repository.py` | `AuditReportRepository` — persists generated PDFs to `data/reports/{job_id}_audit.pdf` |
| `router.py` | `GET /api/jobs/{job_id}/audit-report` — serves binary PDF with `Content-Disposition: attachment` |

---

## 3. Report Structure

1. **Executive Summary & Metadata**
   - Job ID, company name, target metric, generation timestamp
   - Total cell count; automated vs. human-verified breakdown

2. **Reconciliation Summary**
   - High-level table of the target metric bridge (label → formula → value)

3. **Comprehensive Provenance Matrix**
   - Full ledger: every cell → source file, page, normalized bbox, label
   - Multi-page table with repeated column headers

4. **Classifier Governance Proof**
   - Verifies all classifier interactions returned only labels (no numeric extraction)
   - Shows call count, model version, max confidence returned

5. **Cross-Year Definitional Consistency**
   - Drift summary for the associated company (or "No drift data — single filing")

6. **Manual Override & Correction Ledger**
   - All items manually edited, hardcoded, or overridden during review
   - If zero overrides: *"Zero manual overrides — 100% of values are derived from layout extraction and taxonomy-confirmed inputs."*

---

## 4. Known Critical Issues

> **⚠ Active bug — see `issues_charter.md` Step 2.**

The `compiler.py` module currently imports from `excel_export/` to retrieve the W3C Annotation provenance records:
```python
# VIOLATION: audit_report/ must not import from excel_export/
from app.excel_export.models import W3CAnnotationRecord
```
This violates CONSTITUTION §3.5 module isolation (`audit_report/` is Level 3; `excel_export/` is Level 2). The correct fix is to expose provenance records through a shared persistence layer (`data/results/{job_id}_provenance.json`) read by both `audit_report/` and `excel_export/` independently.

Status: **Tracked in `issues_charter.md` Step 13 (Ticket 13.1)**. The audit PDF endpoint returns HTTP 500 when the import fails in strict isolation mode.

---

## 5. Design Constraints

- **No data egress:** The PDF is generated locally and served via `GET /api/jobs/{job_id}/audit-report`. No cloud PDF rendering service (CONSTITUTION §6.5).
- **No numeric generation:** The compiler assembles only values already in the pipeline's persistence layer — it does not compute or re-derive any value.
- **Isolation rule:** After the Step 13 fix, `audit_report/` must read provenance from `data/results/` JSON, not from `excel_export/` models.

---

## 6. Module Isolation (CONSTITUTION §3.5)

```
Level 0: ingestion/
Level 1: extraction/
Level 2: classification/, formula_engine/, excel_export/, review/
Level 3: audit_trail/, drift/, audit_report/
Level 4: narrative/ (roadmap)
```

`audit_report/` imports: `audit_trail/` (source chains), `drift/` (drift summary), `review/` (review history) — all permitted (same level or upstream). It must **not** import from `excel_export/` or `formula_engine/` directly.

---

## 7. Test Suite

| File | Coverage |
|---|---|
| `tests/audit_report/test_compiler.py` | Data assembly from each upstream source; zero-overrides path |
| `tests/audit_report/test_renderer.py` | PDF output exists, non-zero size; multi-page table headers |
| `tests/audit_report/test_router.py` | Download endpoint, Content-Disposition header, 404 on missing report |
