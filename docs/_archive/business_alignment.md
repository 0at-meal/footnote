# Footnote — Business Alignment Diagnosis

> **Purpose:** This document diagnoses Footnote against how buy-side analysts, investment bankers, and credit auditors actually consume 10-K and 10-Q filings. It covers what is **extra** (overhead with no institutional ROI), what is **wrong** (misaligned with real practitioner workflow), and what is **missing** (gaps for subscription viability). Each section closes with actionable steps and atomic tickets.
>
> **Produced:** 2026-08-29 | **Last reviewed:** 2026-09-01

---

## Step Status (A–K)

> This is the current active roadmap. Update as steps are completed.

| Step | Focus | Priority | Status |
|---|---|---|---|
| **A** | Fix PDF coordinate accuracy (bbox wrong, Y-inversion, scale mismatch) | P0 — Demo Blocker | `[ ]` |
| **B** | Fix review queue (zero items unless genuine ambiguity) | P0 — Demo Blocker | `[ ]` |
| **C** | Taxonomy expansion (17-item seed → 60+ canonical, fuzzy alias) | P1 — Pilot Prerequisite | `[ ]` |
| **D** | SEC EDGAR direct integration (ticker → filing, no upload required) | P1 — Pilot Prerequisite | `[ ]` |
| **E** | Debt schedule footnote extraction (Item 8 tranche tables) | P2 — Differentiator | `[ ]` |
| **F** | Lease commitment waterfall extraction (ASC 842 schedules) | P2 — Differentiator | `[ ]` |
| **G** | MD&A delta tracking (narrative word-diff, Item 7) | P2 — Differentiator | `[ ]` |
| **H** | Risk factor redline tracking (Item 1A) | P3 — Retention | `[ ]` |
| **I** | Customer & supplier concentration extraction | P3 — Retention | `[ ]` |
| **J** | Drift detection: economic substance vs. label cosmetics | P3 — Retention | `[ ]` |
| **K** | Architecture path to team deployment (SQLite JobRepo, async, health) | P4 — Scale | `[ ]` |

---


## 0. Executive Context

Footnote currently solves a narrow problem: extract the non-GAAP reconciliation table (Adjusted EBITDA) from a 10-K PDF, classify each line item, and output a provenance-linked Excel workbook. The engineering quality is high.

The gap is not engineering -- it is **scope versus where institutional value actually sits.**

Financial terminals already serve the income statement, balance sheet, and cash flow statement adequately. What firms still open raw SEC filings for:

- **Footnote-level granularity** -- debt tranche schedules, lease commitment waterfalls, SBC routing across cost lines.
- **Quality-of-earnings forensics** -- recurring one-time charges, revenue recognition timing anomalies, customer concentration.
- **Narrative delta tracking** -- MD&A wording changes, risk factor redlines, key personnel changes across consecutive filings.

Footnote addresses only one sub-item of the first bullet (the non-GAAP Adjusted EBITDA bridge). Two items in the current build are overhead with no institutional buyer value at this stage.

---

## Section 1 -- What Is Extra (Overhead With No Institutional ROI)

### 1.1 The Full Evaluation Harness (Feature 9)

The evaluation harness (eval/) is a sophisticated CI/CD benchmark suite: ground-truth corpus loading, three-layer diff, precision/recall/F1 reporting, 15% failed-extraction threshold enforcement, IoU bounding-box tolerance, and performance budget validation.

**Why it is premature overhead:**
- The benchmark corpus does not yet exist. The harness requires 5-10 manually tied-out 10-Ks with schema-validated ground-truth annotations. No analyst, banker, or credit auditor has agreed to produce these.
- The harness validates the pipeline against Adjusted EBITDA only. Selling a subscription requires the pipeline to handle 15-20 distinct analytical use cases. Building the harness before the scope is known means rebuilding it.
- The 90% extraction accuracy target is aspirational, not contractually binding with any client. Firms buy tools that solve a problem today.
- 34 issues, 20 steps of fixes, and 2 full phases of refinement have been logged against the core pipeline. Investing in harness infrastructure before those are resolved sequences incorrectly.

**What to do:** Freeze the eval harness. Keep the code. Do not add to it. Revisit only after one pilot client confirms the pipeline handles their primary use case end-to-end.

---

### 1.2 The 6-Tab Multi-Statement Generator (multi_statement_generator.py)

The multi_statement_generator.py is a 1,260-line generator producing a 6-sheet workbook: Executive_Summary, Income_Statement, EBITDA_Bridge, Cash_Flow, Balance_Sheet, Audit_Trail.

**Why it is architectural inflation:**
- The Income Statement, Cash Flow Statement, and Balance Sheet tabs reconstruct data that Bloomberg and FactSet already serve in cleaner form. No buy-side analyst builds an income statement from raw PDF extraction -- they pull it from the terminal.
- The generator is tightly coupled to ComprehensiveModelTree, which requires all six statement types to be populated. A filing with only an Adjusted EBITDA reconciliation triggers partial-tree generation errors.
- The execution surface is enormous: 1,260 lines that can break with every new company layout, every non-standard PDF structure, every currency unit variation.
- The spec promised an "Adjusted EBITDA model." The multi-statement generator silently expanded scope without institutional buyer confirmation.

**What to do:** Deprecate the 6-tab generator as the default output path. Retain generator.py (the original 2-sheet Source_Inputs + Reconciliation generator) as the shipping product. The 6-tab generator should be a clearly labeled beta feature behind a flag, not the default pipeline path.

---

## Section 2 -- What Is Wrong (Misalignment With Real Practitioner Workflow)

### 2.1 The Scope Is Adjusted EBITDA Only -- Practitioners Need Footnote-Level Data

**The actual workflow:** An analyst opens a 10-K footnote to check debt tranches, not to rebuild the non-GAAP bridge. The non-GAAP bridge is on the face of the earnings release -- analysts can get that in 30 seconds from any terminal. What they cannot get:

- The exact coupon rate, maturity date, and covenant package on each senior secured tranche (Footnote Item 8).
- The operating vs. finance lease split, discount rates, and year-by-year future minimum payment waterfall (ASC 842 schedules).
- Where SBC is routed -- what percentage lands in COGS vs. R&D vs. SG&A.
- Capitalized software development costs versus expensed development costs.

**Current Footnote behavior:** The system extracts reconciliation table cells and routes them into a formula engine. Nothing in this workflow touches the actual footnote tables in Item 8.

**The misalignment:** The tool is named "Footnote" and positioned as a footnote-intelligence product, but it does not process footnotes.

---

### 2.2 The Review UI Shows Items That Should Never Need Review

**The actual workflow:** An analyst who accepts a subscription expects the tool to handle clean data silently. They only want to see items the machine genuinely cannot resolve -- ambiguous labels, multi-column layout failures, OCR errors.

**Current Footnote behavior:** The review queue populates with every reconciliation item, including items that scored 0.97 confidence and matched the taxonomy exactly. Issues charter Step 3 documents this as a bug: is_target_metric_candidate_item() matches too broadly, auto-accepted taxonomy-matched items are not pre-locked, and the confidence scorer penalizes clean flat labels.

**The misalignment:** Showing 20+ items that need no human decision trains users to distrust the tool. A practitioner who clicks Approve on 18 items that scored 98% confidence will stop using the product. The review queue must default to zero items unless there is genuine ambiguity.

---

### 2.3 Drift Detection Is Keyed on Exact String Labels, Not Economic Substance

**The actual workflow:** A forensic analyst tracking metric redefinition looks for economic substance changes. A company that used to include "purchase accounting amortization" and now calls it "acquisition-related intangible amortization" has not changed its calculation, but the string match flags it as drift.

**Current Footnote behavior:** The drift comparator uses exact string equality on normalized_label. Any label rename triggers a redefinition edge even if the economic content is identical. There is no semantic similarity layer, no user-feedback loop to mark a relabel as same item, different name.

**The misalignment:** Drift detection that cries wolf on label cosmetics teaches analysts to ignore the flags. The only drift that matters is economic substance change -- a new "strategic transformation" charge that did not exist in prior years, or when restructuring detail stops being disclosed. String exact-match cannot detect either.

---

### 2.4 The Taxonomy Is Hardcoded to a Generic 17-Item Seed -- Not Company-Specific

**The actual workflow:** Each company has its own idiosyncratic non-GAAP terminology. Apple calls it "Other Income, Net." Tesla calls charges "Restructuring and Other." Palantir uses "Adjusted Operating Expenses." These do not alias cleanly to a generic seed of 17 items.

**Current Footnote behavior:** Unrecognized labels go to pending_taxonomy_confirmation and sit in the review queue until a human resolves them one at a time.

**The misalignment:** For any company with more than 3-4 custom non-GAAP items, the review queue fills with items the generic taxonomy cannot handle. The experience becomes "I have to manually label everything" -- exactly what the tool was supposed to eliminate.

---

### 2.5 PDF Coordinate System Bugs Mean Highlights Are Systematically Wrong

**The actual workflow:** The entire value proposition of Footnote's review UI is that an analyst sees a highlighted bbox on the source PDF and verifies the extraction instantly. If the highlight is in the wrong place, the UX collapses.

**Current Footnote behavior:** Issues charter Step 1 documents two confirmed bugs: (A) PyMuPDF fallback assigns the entire table bbox to every cell due to wrong 1-based loop indexing; (B) Docling uses bottom-left origin while PyMuPDF canvas uses top-left origin, causing systematic vertical inversion. Step 15 documents ReviewPage and AuditTrailView rendering at different scales (1.5 vs 1.3), causing inconsistent highlights. Step 16 documents clientWidth reads including CSS padding, breaking 1:1 coordinate mapping.

**The misalignment:** These bugs affect every PDF. A product where source highlights are systematically wrong cannot be demoed.

---

### 2.6 The Architecture Is Local-Only -- Institutional Buyers Cannot Use It

**The actual workflow:** A buy-side shop has IT security policies. Nothing runs on a single analyst's laptop from a local Python process. Data lives on firm infrastructure, goes through DLP scanning, and is accessed through sanctioned applications. The Docling requirement of >= 2GB RAM on a local machine is a non-starter for a firm of 10+ analysts.

**Current Footnote behavior:** The Constitution explicitly enforces local-only extraction. Groq free tier (30 RPM, 1,000 RPD) cannot support concurrent firm-wide use. SQLite is single-user. No authentication, no multi-tenancy -- by design.

**The misalignment:** The MVP design is appropriate for a solo proof-of-concept. It is not appropriate for a subscription product sold to institutional firms. The architecture must have a clear path to team-level deployment.

---

### 2.7 The Audit Report PDF Is Generic Compliance Theater

**The actual workflow:** When a credit auditor downloads a document for their work file, it needs to meet specific regulatory standards -- clear chain-of-custody, timestamps, preparer identification, legal entity, and a format attachable to a credit committee memo.

**Current Footnote behavior:** The audit report generates five fixed sections treating every filing identically regardless of use case. A debt capital markets banker, a credit auditor, and a buy-side portfolio manager need entirely different formats.

**The misalignment:** A one-size report for all roles is a report optimized for no role.

---

## Section 3 -- What Is Missing (The Actual Gaps for Subscription Viability)

### 3.1 Actual Footnote Extraction -- Item 8 Footnote Table Parsing

The product is named Footnote but does not extract footnotes. The use cases that drive practitioners back to raw filings are all in Item 8:

- **Debt schedule tables:** Tranche-by-tranche breakdown with coupon rates, maturity dates, outstanding principal, LIBOR/SOFR spreads.
- **Lease commitment waterfalls:** Operating vs. finance lease split, discount rates, undiscounted future minimum payments by year.
- **SBC routing table:** Share-based compensation allocated to each income statement line (COGS, R&D, SG&A).
- **Capitalized software costs:** Capitalized development costs added to intangibles vs. expensed R&D.

Without footnote table extraction, Footnote is a non-GAAP reconciliation extractor with a better audit trail. Valuable, but not subscription-grade differentiation.

---

### 3.2 SEC EDGAR Direct Integration -- No-Upload Filing Retrieval

**What practitioners need:** Type a ticker or CIK, select a filing period, and the tool fetches the filing directly from EDGAR. No PDF download, no drag-and-drop.

**Current state:** Upload-only. Every workflow starts with the analyst finding the filing on EDGAR, downloading it, and then uploading. This adds friction and breaks the tool's claim to be a workflow improvement.

**What this requires:** EDGAR EFTS search API, EDGAR filing index API (data.sec.gov/submissions/{CIK}.json), and a filing fetcher that downloads the primary document from SEC servers without user intervention.

---

### 3.3 MD&A Delta Tracking (Item 7 / Item 2 Text Diffing)

**What practitioners need:** The word-by-word diff of the MD&A section between consecutive filings, flagged with semantic categories (volume vs. pricing language, FX impact, segment margin commentary changes).

**Current state:** No text extraction, no diff engine, no NLP layer. The pipeline is table-only.

---

### 3.4 Risk Factor Redline Tracking (Item 1A)

**What practitioners need:** Automated diffs between consecutive 10-Ks and 10-Qs to flag new risk factor language. New regulatory risk disclosures and litigation scope expansions are early signals institutional funds monitor.

**Current state:** Nothing. The pipeline does not touch Item 1A.

---

### 3.5 Customer and Supplier Concentration Extraction

**What practitioners need:** The explicit disclosure that a single customer or supplier accounts for >= 10% of consolidated revenue. This is a credit and equity risk signal that terminals do not surface -- they only show aggregated revenue.

**Current state:** Not extracted. No customer concentration data model exists anywhere in the system.

---

### 3.6 Working Capital and Revenue Recognition Quality Flags (ASC 606)

**What practitioners need:** Changes in unearned revenue, contract assets, billings in excess of cost, and allowance for credit losses between periods -- the early indicators of revenue recognition timing manipulation.

**Current state:** Nothing. No balance sheet footnote extraction, no period-over-period working capital comparison.

---

### 3.7 Multi-User / Team Workspace With Role-Based Access

**What practitioners need:** One analyst extracts, one associate reviews, one VP approves. Three people, three different permissions.

**Current state:** Single-user, single-session by constitutional design. No authentication, no multi-tenancy, no role differentiation.

---

### 3.8 Filing Comparison Across Peers (Sector-Level Benchmarking)

**What practitioners need:** Compare how 15 software companies each define and calculate Adjusted EBITDA -- who includes SBC, who adds back restructuring, how the bridge differs across peers.

**Current state:** One company at a time only. No cross-company comparison.

---

### 3.9 Confidence-Calibrated Accuracy Per Company Over Time

**What practitioners need:** After 6 months across 50 Apple filings: "What is my actual accuracy on Apple? Which sections produce low confidence? Has accuracy improved since I updated the taxonomy?"

**Current state:** No per-company accuracy tracking. The evaluation harness is a one-shot benchmark against a static corpus, not a running accuracy monitor.

---

### 3.10 Subscription-Grade Output Formats

**What practitioners need:** XBRL-tagged output for regulatory submission, CSV export for quant import, and a PowerPoint-compatible slide table for client presentation.

**Current state:** .xlsx only (plus a PDF audit report). Incomplete for institutional workflows.

---

## Section 4 -- Actionable Steps With Implementation Tickets

> Each step addresses one diagnosis. Each ticket is atomic -- independently implementable, testable, and mergeable. Tickets within a step are ordered by dependency. Steps are ordered by institutional value delivery priority.

---

### STEP A -- Fix the Core UX: PDF Coordinate Accuracy

**Diagnosis addressed:** Section 2.5 -- Highlights are systematically wrong.
**Gate:** No demo, no pilot, no subscription until this is resolved.

| Ticket | File | Action |
|---|---|---|
| A-1 | extraction/docling_parser.py | Fix PyMuPDF fallback cell indexing: change 1-based loop to 0-based: (row_idx-1) * len(row) + (col_idx-1). Verify table.cells is flat list before index access. |
| A-2 | extraction/models.py | Add parser_used field (Literal["docling","pymupdf"], default "docling") to DoclingItem. Set "pymupdf" on every item from _parse_pdf_with_pymupdf(). |
| A-3 | extraction/coordinate_normalizer.py | Add Y-axis inversion for Docling coordinates: y0_screen = 1000.0 - y1_norm, y1_screen = 1000.0 - y0_norm. Apply only when parser_used == "docling". |
| A-4 | frontend/src/lib/pdf/renderer.ts | Export PDF_RENDER_SCALE = 1.5 constant. Update AuditTrailView.tsx to import and use it instead of hardcoded 1.3. |
| A-5 | ReviewPage.tsx, AuditTrailView.tsx | Replace clientWidth/clientHeight reads with getBoundingClientRect() in both components for accurate canvas dimensions. |
| A-6 | tests/extraction/test_coordinate_normalizer.py | Parametrized unit tests: Docling Y-inversion path, PyMuPDF direct mapping path, per-cell flat_idx correctness on 3x4 mock table. |

---

### STEP B -- Fix the Review Queue: Zero Items Unless Genuine Ambiguity

**Diagnosis addressed:** Section 2.2 -- Review queue shows items that should never need review.
**Gate:** Pilot users must open the review tab and see <= 5 items on any clean institutional filing.

| Ticket | File | Action |
|---|---|---|
| B-1 | extraction/confidence.py | Add +0.15 confidence bonus for is_reconciliation_candidate == True. Add +0.05 for well-formed numeric value (parseable after stripping $, commas, parens, percent). Clamp at 1.0. |
| B-2 | extraction/confidence.py | Add table-consistency second pass: if >= 70% of items in a table scored >= 0.80, boost remaining items in that table by +0.10. |
| B-3 | classification/normalizer.py | Tighten is_target_metric_candidate_item(): require is_reconciliation_candidate == True as primary gate before keyword matching. Remove broad label-only fallback. |
| B-4 | review/repository.py | In _from_classified_records(): if confidence_band == auto_accepted AND taxonomy_status == matched, set status = ReviewStatus.locked immediately. These never enter the Flagged tab. |
| B-5 | frontend/src/components/review/ReviewPage.tsx | Fix isFlagged predicate: include only {needs_review, manual_required, extraction_error, pending_taxonomy_confirmation, flagged}. Remove confidence_score < 0.95 condition. |
| B-6 | tests/extraction/test_confidence.py, tests/review/test_repository.py | Tests: reconciliation table item scores >= 0.95; auto_accepted+matched items enter locked; non-reconciliation items unaffected by bonus. |

---

### STEP C -- Fix the Taxonomy: Company-Adaptive Alias Expansion

**Diagnosis addressed:** Section 2.4 -- 17-item seed fails on any company with custom terminology.
**Gate:** A filing from any S&P 500 company should produce <= 2 pending_taxonomy_confirmation items.

| Ticket | File | Action |
|---|---|---|
| C-1 | classification/taxonomy.py | Expand seed taxonomy from 17 to 60+ canonical items covering D&A, Interest Expense, Income Tax, Change in FV of Derivatives, Non-cash Lease Expense, Earn-out Payments, IPO-related Costs, Spin-off Costs, COVID Costs, Contingent Consideration, and 30+ more. Research: 5 annual reports from each of 5 sectors. |
| C-2 | classification/client.py | Update Groq classifier prompt to include company name and SIC code as context, enabling industry-specific terminology resolution against the expanded taxonomy. |
| C-3 | classification/taxonomy.py | Add fuzzy alias matching: after exact and canonicalized matching fail, apply token-set-ratio similarity check (threshold >= 0.85). Mark as fuzzy_matched in TaxonomyCheckResult for informational review without blocking auto-acceptance. |
| C-4 | backend/app/review/router.py | Add POST /review/{job_id}/bulk-confirm-taxonomy endpoint: accepts list of {item_id, canonical_name} pairs, adds all to taxonomy in one request. |
| C-5 | frontend/src/components/review/ReviewPage.tsx | Add Bulk Taxonomy Confirm panel in pending_taxonomy_confirmation section: shows all pending items with suggested canonical matches, checkbox selection, one-click batch confirm. |

---

### STEP D -- SEC EDGAR Direct Integration

**Diagnosis addressed:** Section 3.2 -- Upload-only is a friction barrier for any structured pilot.
**Gate:** A user can type "AAPL 2024 10-K" and the filing loads without downloading a PDF.

| Ticket | File | Action |
|---|---|---|
| D-1 | backend/app/ingestion/edgar_client.py (NEW) | Pure function module: search_company(query: str) -> list[EdgarCompanyResult] using EDGAR EFTS API. Returns CIK, company name, SIC, ticker. mypy --strict required. |
| D-2 | backend/app/ingestion/edgar_client.py | Add get_filings(cik, form_type, limit) -> list[EdgarFiling] using data.sec.gov/submissions/{CIK}.json. Parses filing index for 10-K and 10-Q. |
| D-3 | backend/app/ingestion/edgar_client.py | Add fetch_filing_pdf(accession_number, cik) -> bytes from EDGAR archives. Validates returned bytes as valid PDF via existing validate_pdf_bytes. |
| D-4 | backend/app/ingestion/router.py | Add POST /upload/edgar endpoint: accepts {cik, accession_number, target_metric, filing_year, company_name}, fetches PDF, saves via JobRepository, enqueues pipeline. Returns same JobRecord shape as file upload. |
| D-5 | frontend/src/components/EdgarSearch.tsx (NEW) | Debounced search input calling GET /upload/edgar/search. Autocomplete with company name, ticker, CIK. On filing selection: POSTs to /upload/edgar. |
| D-6 | backend/tests/ingestion/test_edgar_client.py (NEW) | Unit tests using httpx_mock: company search returns valid results, filing index parses, PDF fetch validates bytes, 404 from EDGAR surfaces as structured error not exception. |

---

### STEP E -- Debt Schedule Footnote Extraction (Item 8)

**Diagnosis addressed:** Section 3.1 -- The product is named Footnote but does not extract footnotes.
**Gate:** A user uploads a 10-K and the debt maturity schedule is extracted with tranche, coupon, maturity, and outstanding balance.

| Ticket | File | Action |
|---|---|---|
| E-1 | extraction/docling_parser.py | Add _detect_footnote_section(table_title, section_heading) -> FootnoteCategory or None. Categories: DEBT_SCHEDULE, LEASE_SCHEDULE, SBC_ROUTING, COMMITMENTS. Keyword match on table title and surrounding section header. |
| E-2 | extraction/models.py | Add footnote_category (str or None, default None) to DoclingItem. Propagate through ExtractedRecord and ScoredRecord. Values: "debt_schedule", "lease_schedule", "sbc_routing", None. |
| E-3 | backend/app/footnote/ (NEW directory) | Create footnote/ module with models.py defining DebtTranche(label, coupon_rate, maturity_date, outstanding, currency), DebtSchedule(job_id, tranches, total_debt, as_of_date). mypy --strict. No imports from classification/ or formula_engine/. |
| E-4 | backend/app/footnote/extractor.py (NEW) | Pure function extract_debt_schedule(records: list[ExtractedRecord]) -> DebtSchedule or None. Identifies debt schedule rows by column structure. Parses maturity dates in multiple formats (YYYY, MM/YYYY, "due YYYY"). |
| E-5 | backend/app/footnote/router.py (NEW) | GET /footnotes/{job_id}/debt-schedule returns DebtSchedule. GET /footnotes/{job_id}/available returns list of detected footnote categories. Register in main.py. |
| E-6 | backend/tests/footnote/test_extractor.py (NEW) | Unit tests: 3-tranche schedule parses correctly, maturity date formats handled, missing coupon rate produces None field not error. |

---

### STEP F -- Lease Commitment Waterfall Extraction (ASC 842)

**Diagnosis addressed:** Section 3.1 -- Operating vs. finance lease breakdown schedules missing.
**Gate:** A user uploads a 10-K and the lease commitment table is extracted with operating vs. finance split and weighted-average discount rate.

| Ticket | File | Action |
|---|---|---|
| F-1 | backend/app/footnote/models.py | Add LeaseCommitmentYear(year_label, operating_amount, finance_amount), LeaseSchedule(job_id, years, operating_total, finance_total, operating_discount_rate, finance_discount_rate, as_of_date). |
| F-2 | backend/app/footnote/extractor.py | Add extract_lease_schedule(records) -> LeaseSchedule or None. Identifies rows by "operating lease" / "finance lease" column headers. Extracts discount rate from "weighted-average discount rate" row. Handles "thereafter" label. |
| F-3 | backend/app/footnote/router.py | Add GET /footnotes/{job_id}/lease-schedule endpoint returning LeaseSchedule. |
| F-4 | frontend/src/components/footnote/LeaseScheduleCard.tsx (NEW) | Renders LeaseSchedule as two-column table (Operating / Finance) with year-by-year rows and discount rate footer. IB table styling. |
| F-5 | backend/tests/footnote/test_lease_extractor.py (NEW) | Unit tests: 5-year waterfall parses, "thereafter" row captured, discount rate extracted, missing finance column produces None not error. |

---

### STEP G -- MD&A Delta Tracking (Narrative Intelligence)

**Diagnosis addressed:** Section 3.3 -- No narrative section extraction or diff engine.
**Gate:** A user uploads two consecutive 10-Ks and the system produces a word-diff of the MD&A section.

| Ticket | File | Action |
|---|---|---|
| G-1 | backend/app/narrative/ (NEW directory) | Create module with models.py: NarrativeSection(job_id, item_number, title, text, page_start, page_end), NarrativeDiff(company_id, item_number, earlier_job_id, later_job_id, added_tokens, removed_tokens, unchanged_tokens). mypy --strict. |
| G-2 | backend/app/narrative/extractor.py (NEW) | extract_narrative_sections(job_id, docling_items) -> list[NarrativeSection]. Uses Docling section heading detection for Item 2 (10-Q MD&A) and Item 7 (10-K MD&A). Falls back to page range heuristic if headings unavailable. |
| G-3 | backend/app/narrative/differ.py (NEW) | Pure function diff_narrative_sections(earlier, later) -> NarrativeDiff. Uses Python difflib.SequenceMatcher at token level. Deterministic -- no LLM call. |
| G-4 | backend/app/narrative/router.py (NEW) | POST /narrative/{company_id}/diff accepts {earlier_job_id, later_job_id, item_number}, runs diff, returns NarrativeDiff. GET /narrative/{job_id}/sections returns extracted sections. |
| G-5 | frontend/src/components/narrative/NarrativeDiffView.tsx (NEW) | Side-by-side text diff with color-coded additions (green) and deletions (red). Pagination by paragraph. Filter toggle for changed paragraphs only. |
| G-6 | backend/tests/narrative/test_differ.py (NEW) | Unit tests: identical text produces empty diff, single word addition produces one-token insertion, paragraph deletion produces correct removed_tokens count. |

---

### STEP H -- Risk Factor Redline Tracking (Item 1A)

**Diagnosis addressed:** Section 3.4 -- No risk factor change detection.
**Gate:** A user running a 10-K comparison sees new risk factor headings and modified language flagged by severity.

| Ticket | File | Action |
|---|---|---|
| H-1 | backend/app/narrative/extractor.py | Extend section extractor to detect Item 1A (Risk Factors). Parse individual risk factor headings as sub-sections. Each heading becomes RiskFactor(heading, body_text). |
| H-2 | backend/app/narrative/models.py | Add RiskFactorChange(heading, change_type, severity_score, added_text, removed_text), RiskFactorRedline(company_id, earlier_job_id, later_job_id, changes). change_type: Literal["added","removed","modified"]. |
| H-3 | backend/app/narrative/differ.py | Add diff_risk_factors(earlier_sections, later_sections) -> RiskFactorRedline. Matches headings exact then fuzzy. New heading = added. Absent heading = removed. Body changes = modified with severity score (proportion changed). |
| H-4 | backend/app/narrative/router.py | Add POST /narrative/{company_id}/risk-redline endpoint returning RiskFactorRedline. |
| H-5 | frontend/src/components/narrative/RiskRedlineView.tsx (NEW) | List view sorted by severity. "New" badge for added risks. "Removed" badge for deleted risks. Expandable inline diff for modified risks. |

---

### STEP I -- Customer and Supplier Concentration Extraction

**Diagnosis addressed:** Section 3.5 -- Customer/supplier concentration disclosures not extracted.
**Gate:** For any 10-K where a customer >= 10% disclosure exists, the tool extracts name, percentage, and segment.

| Ticket | File | Action |
|---|---|---|
| I-1 | backend/app/footnote/models.py | Add CustomerConcentration(customer_name, revenue_percentage, segment, disclosure_location, job_id), ConcentrationSummary(job_id, customers, suppliers). |
| I-2 | backend/app/footnote/extractor.py | Add extract_customer_concentration(records) -> ConcentrationSummary. Pattern-match: "accounted for", "represented", "no single customer". Regex for percentage extraction. |
| I-3 | backend/app/footnote/router.py | Add GET /footnotes/{job_id}/concentration returning ConcentrationSummary. |
| I-4 | frontend/src/components/footnote/ConcentrationCard.tsx (NEW) | Renders concentration table: customer name/alias, percentage, segment. Warning badge if any customer >= 15%. |
| I-5 | backend/tests/footnote/test_concentration.py (NEW) | Unit tests: "Customer A accounted for 12%" extracts 12%, "no single customer" produces empty list, multi-segment disclosures parsed correctly. |

---

### STEP J -- Drift Detection: Economic Substance vs. Label Cosmetics

**Diagnosis addressed:** Section 2.3 -- Drift flags label renames, not economic changes.
**Gate:** Renaming "purchase accounting amortization" to "acquisition-related intangible amortization" does NOT generate a drift flag.

| Ticket | File | Action |
|---|---|---|
| J-1 | drift/comparator.py | Add semantic similarity layer: before flagging a label as "removed" in year N+1, check if any new label has token-set-ratio >= 0.80 against it. If match found: record as relabeled not removed + added. |
| J-2 | drift/models.py | Add DriftChangeType to DriftEdge with values: added, removed, relabeled, split, merged. relabeled carries from_label and to_label. |
| J-3 | drift/router.py | Add POST /drift/{job_id}/mark-relabeled endpoint: analyst manually confirms removed+added pair is a relabeling. Converts to single relabeled edge, suppresses future false positives for that entity. |
| J-4 | drift/storage.py | Persist relabeled pairs as entity-level exception list in data/drift_relabeling.json. Load on startup alongside drift graph. |
| J-5 | frontend/src/components/drift/DriftFlagCard.tsx (NEW) | Renders drift flags grouped by type. relabeled pairs shown with "Same economic item, renamed" label. "Mark as Relabeling" button on any removed+added pair. |

---

### STEP K -- Architecture Path to Team Deployment

**Diagnosis addressed:** Section 2.6 -- Local-only architecture cannot scale to institutional buyers.
**Gate:** Two analysts at the same firm can upload filings simultaneously without one blocking the other.

| Ticket | File | Action |
|---|---|---|
| K-1 | backend/app/main.py | Read CORS allowed origins from ALLOWED_ORIGINS env var (comma-separated list), default to localhost:5173. Document in README. Unblocks staging and cloud deployment. |
| K-2 | backend/app/ingestion/repository.py | Replace jobs.json file-level lock with SQLite-backed JobRepository. Single-writer lock at job record level, not file level. Backward-compatible schema. |
| K-3 | backend/app/ingestion/router.py | Add POST /upload/jobs/async endpoint: accepts upload, saves file, creates job record, enqueues pipeline via FastAPI BackgroundTasks. Document migration path to Celery/RQ. |
| K-4 | backend/app/main.py | Add GET /health endpoint returning {status, version, db_ok, data_dir_writable}. Required for load balancer health checks in any deployed environment. |
| K-5 | backend/app/ingestion/models.py | Add session_id (str or None, default None) to JobRecord. Not enforced at MVP but required for future per-session job isolation without a schema migration. |

---

## Execution Priority Matrix

| Priority | Step | Rationale |
|---|---|---|
| P0 -- Demo Blocker | Step A (PDF coordinates) | Cannot demo, cannot pilot until highlights work correctly |
| P0 -- Demo Blocker | Step B (Review queue) | Review queue with 20 auto-approved items kills trust in first session |
| P1 -- Pilot Prerequisite | Step C (Taxonomy expansion) | No pilot company will have <= 2 pending_taxonomy_confirmation items without this |
| P1 -- Pilot Prerequisite | Step D (EDGAR integration) | Upload-only workflow is a friction barrier for any structured pilot |
| P2 -- Subscription Differentiator | Step E (Debt footnote) | First feature with zero terminal equivalent |
| P2 -- Subscription Differentiator | Step F (Lease waterfall) | ASC 842 lease schedules are a confirmed analyst pain point |
| P2 -- Subscription Differentiator | Step G (MD&A delta) | Narrative intelligence is the highest-frequency practitioner use case |
| P3 -- Retention Features | Step H (Risk factor redline) | Institutional funds will pay for automated risk factor monitoring |
| P3 -- Retention Features | Step I (Customer concentration) | Simple extraction, high signal -- credit analysts check this for every filing |
| P3 -- Retention Features | Step J (Drift substance vs. cosmetics) | Required before drift detection is useful in production |
| P4 -- Scale Prerequisite | Step K (Team deployment path) | Must exist before any firm-level contract is signed |

---

## Features to Freeze (Do Not Invest Further Until P0-P2 Are Complete)

| Feature | Current State | Reason to Freeze |
|---|---|---|
| Feature 9 Evaluation Harness | Built, dormant | No benchmark corpus; scope will change before useful |
| 6-Tab Multi-Statement Generator | Built, partial errors | Income Statement / Balance Sheet / Cash Flow have no subscription value vs. terminals |
| Audit Report PDF | Built | Generic format; revisit after first pilot confirms what format auditors actually need |
| Drift Graph UI | Built | Not useful until Step J (substance vs. cosmetics) is resolved |

---

## Architecture Guard Rails for New Steps

1. All new modules (footnote/, narrative/) must follow CONSTITUTION Section 1 (mypy --strict), Section 2 (naming), Section 3 (isolation). No module in these directories may import from classification/client.py or formula_engine/.
2. EDGAR API calls are network I/O and belong in ingestion/edgar_client.py, not in any extraction or formula module.
3. The narrative/ module must never modify extraction records. It reads DoclingItem and ExtractedRecord from the extraction store and writes to its own data/narrative/ directory.
4. The footnote/ module is higher-level than extraction/ -- it identifies and structures specific footnote table types on top of lower-level extraction output. Do not conflate the two.
5. New LLM calls (if added) must go through the same Groq interface and the same label-only, no numeric output constraint from CONSTITUTION Sections 6.1 and 6.2. No new LLM call may produce a numeric value directly.

---

*Document produced: 2026-08-29. Based on full codebase analysis of c:\footnote -- all backend modules, frontend components, 21 documentation files -- cross-referenced against the practitioner workflows described in the business context provided.*
