# Architectural Decision Record (ADR) 004: Multi-Year Company Architecture

* **Status:** ✅ Implemented
* **Date:** 2026-08-20 (decided during grill-me interview session)
* **Implemented:** Refinement Phase 2, Steps 2.1–2.2
* **Deciders:** Antigravity Team

---

## 1. Context and Problem Statement

After Refinement Phase 1, the pipeline could produce a single-year Adjusted EBITDA
workbook from one uploaded filing. The natural next requirement was multi-year comparison:
a banker uploads three consecutive 10-Ks for a company and gets a single workbook with
fiscal years as columns and line items as rows (standard IB model format).

This required several design decisions that were not obvious upfront:

1. **Multi-year layout:** One sheet with years as columns vs. one sheet per year.
2. **Company identity:** How does the system know which filings belong to the same company?
3. **Filing year source:** How does the year appear on each filing's column header?
4. **Multi-year trigger:** When does the multi-year model get built?

---

## 2. Resolved Design Decisions

The following were decided and locked during a structured interview session:

| Decision | Options Considered | Chosen |
|---|---|---|
| Multi-year xlsx layout | One sheet per year vs. one sheet with years as columns | **Option B — one sheet, fiscal years as columns, line items as rows** (standard IB format) |
| Company identity / grouping | Auto-detect company name from filing vs. manual user grouping | **Option A — user manually groups filings.** Upload form gets "Assign to Company" dropdown; user selects existing or types a new name. |
| Filing year source | Auto-detect from filing date vs. user input | **User selects/types fiscal year** (e.g. `2023`) at upload time alongside target metric. New field on `JobRecord`. |
| Template support | Footnote-formatted model only vs. import from existing template | **Footnote-formatted model only.** User manually incorporates. `openpyxl` migration acceptable if templates are ever in scope. |
| Multi-year model trigger | Auto-build when second job completes vs. manual trigger | **Manual — a "Build Multi-Year Model" button on the company view**, appears once 2+ jobs are done. |
| Excel output structure | Source_Inputs per year + combined Reconciliation vs. single grid | Source_Inputs sheet: plain numeric values + cell comments with provenance. Reconciliation sheet: `=Source_Inputs!F{row}` cross-sheet references per line item, `=SUM(C4:C12)` for total row. No `=HYPERLINK` wrappers. _(See ADR-002.)_ |
| Phase execution order | Parallel vs. strictly sequential | **Strictly sequential.** Phase 0 fully done → Phase 1 fully done → Phase 2. |

---

## 3. Data Model

### `CompanyRecord` (`backend/app/ingestion/models.py`)
```python
class CompanyRecord(BaseModel):
    company_id: str          # UUIDv4
    name: str
    ticker: str | None = None
    created_at: str          # ISO 8601 UTC
    job_ids: list[str] = []
```
Stored at `data/companies.json`.

### Extended `JobRecord` fields
```python
filing_year: int | None = None    # fiscal year, user-supplied at upload
company_id: str | None = None     # UUIDv4 of associated CompanyRecord
```

### Multi-Year Generator
```python
def generate_multi_year_workbook(
    company: CompanyRecord,
    jobs: list[tuple[JobRecord, FormulaTree]],
    output_dir: Path,
) -> WorkbookGenerationResult:
```
Output: `data/models/{company_id}_multi_year.xlsx`

---

## 4. API Surface

| Endpoint | Description |
|---|---|
| `POST /companies` | Create a company (name, optional ticker) |
| `GET /companies` | List all companies with associated job summaries |
| `GET /companies/{company_id}` | Get one company with full job list |
| `POST /companies/{company_id}/jobs/{job_id}` | Assign existing job to company |
| `POST /companies/{company_id}/multi-year-model` | Build multi-year xlsx from 2+ completed jobs |
| `GET /companies/{company_id}/multi-year-model/download` | Download multi-year xlsx |

---

## 5. Consequences & Benefits

* **Positive:** User-controlled grouping means no ambiguity about which filings belong to
  which company — the user makes the decision explicitly.
* **Positive:** Manual fiscal year input is unambiguous (SEC filings have complex fiscal
  year boundaries; auto-detection would require parsing multiple date fields).
* **Positive:** Manual multi-year trigger prevents partial models — the button is only
  enabled when 2+ jobs have `model_ready == True`.
* **Negative/Trade-off:** User must perform the grouping step — there is no magic "this is
  the same company" detection. Friction is acceptable at MVP scale.

---

## 6. Implementation Notes

| Ticket | Files | Change |
|---|---|---|
| 2.1.1 | `ingestion/models.py`, new `ingestion/company_repository.py` | `CompanyRecord` model; `CompanyRepository` with save/list/get/add_job |
| 2.1.2 | `ingestion/models.py`, `ingestion/repository.py`, `ingestion/router.py` | Added `filing_year` and `company_id` to `JobRecord`; `POST /upload/jobs` accepts `filing_years` and `company_name` |
| 2.1.3 | new `ingestion/company_router.py` | 4 company CRUD endpoints registered in `main.py` |
| 2.1.4 | new `frontend/src/components/CompanySelector.tsx`, `App.tsx`, `types/job.ts` | Company combobox + fiscal year input in upload form |
| 2.2.1 | new `excel_export/multi_year_generator.py` | Pure function multi-year workbook generator |
| 2.2.2 | `ingestion/company_router.py` | `POST /companies/{id}/multi-year-model` endpoint |
| 2.2.3 | new `frontend/src/components/CompanyView.tsx`, `App.tsx` | Company view with "Build Multi-Year Model" button |
| 2.2.4 | `drift/service.py`, `drift/router.py` | Drift evaluation auto-resolves company name and filing year from `JobRecord` |
