# Footnote — Domain Glossary

This glossary establishes canonical definitions for financial, extraction, and pipeline concepts in the Footnote application.

---

### Core Financial & Domain Terms

#### 1. Non-GAAP Financial Measure
A numerical measure of a company's historical or future financial performance, financial position, or cash flows that excludes amounts included in the most directly comparable measure calculated and presented in accordance with GAAP (U.S. Generally Accepted Accounting Principles), or includes amounts excluded from GAAP. Common examples include **Adjusted EBITDA**, **Free Cash Flow**, and **Adjusted Net Income**.

#### 2. Reconciliation Table (Non-GAAP Bridge)
A structured table in SEC filings (10-K, 10-Q, 8-K) that provides a line-item mathematical bridge connecting a GAAP measure (e.g., Net Income or Operating Income) to the Target Non-GAAP Metric (e.g., Adjusted EBITDA) by adding or subtracting specific reconciliation adjustments.

#### 3. Target Metric
The specific financial metric selected by the analyst during job upload (e.g., `Adjusted EBITDA`). Governs which non-GAAP reconciliation tree is constructed by the deterministic formula engine.

#### 4. Addbacks & Adjustments
Line items added back to GAAP Net Income to arrive at Adjusted EBITDA, including:
* **Stock-Based / Share-Based Compensation (SBC)**
* **Depreciation & Amortization (D&A)**
* **Restructuring & Severance Charges**
* **Impairments & Asset Write-downs**
* **Litigation & Settlement Charges**
* **Acquisition, Transaction, and Integration Costs**

---

### Pipeline & Architectural Terms

#### 5. Target Metric Scope (Relevance Filter)
The subset of extracted tables and line items from a filing that directly contribute to the target metric's reconciliation tree. Non-reconciliation tables (e.g., Balance Sheet, PPE, Debt schedules) are classified as *Out-of-Scope Filing Data*.

#### 6. Noise Suppression
The extraction pre-filter that strips non-data table artifacts, document section banners ("Item 7. Management's Discussion..."), unit qualifiers ("in millions, except per share amounts"), and empty header labels from entering the financial line item stream.

#### 7. Confidence Bands (3-Tier Routing)
* **Auto-Accept ($\ge 0.95$):** Structurally unambiguous line items with clear bounding boxes and exact taxonomy matches. Auto-included in the draft model.
* **Needs Review ($0.65 - 0.95$):** Line items with minor structural ambiguity, multi-level header splits, or unrecognized taxonomy strings requiring analyst confirmation.
* **Manual Required ($< 0.65$):** Low-confidence extractions or unparseable values requiring analyst entry before inclusion.

#### 8. Frozen 5-Field Schema
The immutable JSON schema required by `CONSTITUTION §2.3` for all raw extraction records:
`{ value: str, label: str, page: int, bbox: dict, source_file: str }`.

#### 9. W3C Web Annotation Provenance Record
A canonical JSON object mapping each generated `.xlsx` cell to its exact bounding box (`x0, y0, x1, y1` normalized to 0–1000), page number, and source file in the original filing.

---

### Multi-Year & Company Architecture Terms (Phase 2)

#### 10. CompanyRecord
A Pydantic model (`backend/app/ingestion/models.py`) grouping one or more `JobRecord`s under a named company entity. Fields: `company_id` (UUIDv4), `name`, `ticker`, `created_at`, `job_ids`. Stored in `data/companies.json`.

#### 11. filing_year
An optional integer field on `JobRecord` recording the fiscal year of a filing (e.g. `2023`). Used to order columns in the multi-year Excel workbook and to supply filing year context to drift detection without manual input.

#### 12. Multi-Year Generator
The function `generate_multi_year_workbook` in `backend/app/excel_export/multi_year_generator.py`. Produces a single `.xlsx` with fiscal years as columns and normalized line items as rows, covering all filings associated with a company.

---

### Reconciliation Scoping Terms (Refinement Phase 1)

#### 13. is_reconciliation_candidate
A boolean flag (`bool = False`) propagated from `DoclingItem` → `ExtractedRecord` → `ScoredRecord`. Set `True` for items whose parent table title matches the target metric (case-insensitive) or contains keywords: `non-gaap`, `reconciliation`, `adjusted`, `bridge`. Items flagged `False` are filtered from Groq dispatch and the review queue.

#### 14. Noise Suppression Pre-Filter
The function `_is_noise_cell(cell_text, row_idx, col_idx)` in `docling_parser.py` that drops non-data table cells (SEC document boilerplate like `"Item 7."`, `"Table of Contents"`, `"PART I"`, currency qualifiers like `"in millions"`, and cells containing no numeric digits).

#### 15. Draft Model
An `.xlsx` workbook auto-generated during the initial extraction pass using auto-accepted reconciliation items. Generated without requiring explicit analyst review, enabling immediate download for clean filings.

---

### Footnote Intelligence Terms (Roadmap — Steps E, F)

#### 16. DebtSchedule
A structured model (`backend/app/footnote/models.py`) representing a parsed debt maturity table from Item 8. Fields include `tranches` (list of `DebtTranche` with coupon rate, maturity date, outstanding principal) and `total_debt`.

#### 17. LeaseSchedule
A structured model representing the ASC 842 lease commitment waterfall. Fields include year-by-year `operating_amount` and `finance_amount`, `operating_discount_rate`, and `finance_discount_rate`.

#### 18. NarrativeSection
A structured model (`backend/app/narrative/models.py`) representing a parsed MD&A or Risk Factors section extracted from a filing. Fields: `job_id`, `item_number`, `title`, `text`, `page_start`, `page_end`.

---

### Drift Detection Terms (Refinement)

#### 19. DriftChangeType
An enum on `DriftEdge` with values: `added`, `removed`, `relabeled`, `split`, `merged`. `relabeled` carries `from_label` and `to_label` fields, distinguishing economic-substance changes from cosmetic label renames.

#### 20. parser_used
A `Literal["docling", "pymupdf", "mixed"]` field on `DoclingItem` and `ExtractionSummary`. Records which parser produced each extraction record, enabling conditional Y-axis inversion in the coordinate normalizer and surfacing a quality-degraded warning in the review UI when the PyMuPDF fallback was used.

