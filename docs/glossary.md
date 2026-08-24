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
