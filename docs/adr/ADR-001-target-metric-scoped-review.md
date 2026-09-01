# Architectural Decision Record (ADR) 001: Target-Metric-Scoped Extraction & Review Triage

* **Status:** ✅ Implemented
* **Date:** 2026-08-19
* **Implemented:** 2026-09-01 (Refinement Phase 1, Steps 1.1–1.2)
* **Deciders:** Antigravity Team & Lead Financial Architect

---

## 1. Context and Problem Statement

Footnote's core value proposition is saving junior investment bankers and private equity analysts hours of tedious, manual financial modeling by automatically parsing 10-K/10-Q filings, extracting non-GAAP reconciliations, and generating native, formula-driven Excel models (`.xlsx`) with full provenance.

However, the initial implementation of Feature 2 (Extraction) and Feature 5 (Review UI) parsed **every single table across the entire 200+ page filing** (Balance Sheet, Cash Flows, Segment Reporting, PPE schedules, Tax schedules, Debt notes). This generated **300 to 1,000+ data cells**, including document headers and non-reconciliation tables, and presented them as a flat, unranked review queue.

Because the user is prompted for a `target_metric` (e.g., *Adjusted EBITDA*) at upload time, but that metric was never used to filter, scope, or rank extractions, the junior banker was burdened with reviewing hundreds of irrelevant items — defeating the core business purpose.

---

## 2. Decision Drivers

1. **Analyst Velocity (NFR3):** Reduce analyst review time from 15–30 minutes of sifting through 300+ items to **under 30 seconds** (reviewing only the 1–3 flagged items).
2. **Mathematical & Deterministic Rigor (CONSTITUTION §1.4, NFR1):** Filtering and ranking must be 100% deterministic pure functions. No random seeds, no hallucinated values.
3. **AI Boundaries (CONSTITUTION §6.1, §6.2):** The LLM remains strictly a classifier of labels/tables; it never generates, infers, or modifies numeric values.
4. **Frozen Schema Invariance (CONSTITUTION §2.3):** The 5 frozen fields (`value`, `label`, `page`, `bbox`, `source_file`) remain unchanged.

---

## 3. Decision

We introduce **Target-Metric-Scoped Triage & Relevance Filtering** across the pipeline:

### 3.1 Structural Table Relevance Scoring & Noise Suppression (Extraction Layer)
* Filter out non-data noise (table title cells, headers without numeric values, "In millions except per share", "Item 7", etc.).
* Tag extracted tables and items with a deterministic `table_context` and identify **Target Metric Reconciliation Tables** (tables containing headers or rows matching the `target_metric` name, e.g., *"Reconciliation of Net Income to Adjusted EBITDA"*, *"Non-GAAP Financial Measures"*).

### 3.2 Metric Relevance Tagging (Classification / Review Layer)
* Items belonging to the target reconciliation table or matching the seed taxonomy for the target metric are flagged with `metric_relevance: "primary"` (typically 5–15 line items).
* Items from unrelated tables (Balance Sheet, Leases, PPE) are tagged with `metric_relevance: "other_filing_data"`.

### 3.3 Target-Metric-Focused Review UI (Frontend Layer)
* Default the Review UI to **"Target Metric Reconciliation"** tab, showing only the ~5–15 relevant items.
* Group items into:
  1. **Primary Reconciliation Items** (Active default view)
  2. **Needs Review / Flagged** (Only ambiguous or low-confidence items)
  3. **Auto-Accepted** (High confidence items ready for instant model inclusion)
  4. **All Filing Tables** (Collapsible secondary drawer for advanced power-user lookup).
* Enable **"Accept All High-Confidence Items"** / **"Generate Model"** so that if all primary reconciliation items are $\ge 0.95$ confidence, the model builds in 1 click.

---

## 4. Consequences & Benefits

* **Positive:** Slashes analyst cognitive load by $>95\%$. The banker opens the Review UI and immediately sees the exact Adjusted EBITDA bridge.
* **Positive:** Preserves 100% provenance and 100% determinism.
* **Positive:** Leaves all other document tables reachable in the secondary "All Filing Tables" drawer without cluttering the primary workflow.
* **Negative/Trade-off:** Requires a deterministic table header classifier and regex scoring rule for non-GAAP reconciliation detection.

---

## 5. Implementation Notes

This decision was fully implemented in **Refinement Phase 1** (see `docs/archive/refinement.md`):

| Ticket | File | Implementation |
|---|---|---|
| 1.1.1 | `extraction/docling_parser.py` | Added `_is_reconciliation_table()` pure function; added `is_reconciliation_candidate: bool` to `DoclingItem` |
| 1.1.2 | `extraction/models.py`, `assembler.py`, `confidence.py` | Propagated `is_reconciliation_candidate` from `DoclingItem` → `ExtractedRecord` → `ScoredRecord` |
| 1.1.3 | `job_runner.py` | Filter to `is_reconciliation_candidate == True` before Groq dispatch |
| 1.2.1 | `review/repository.py` | `_from_classified_records()` skips non-reconciliation items; auto-accepted+matched items pre-locked |
| 1.2.2 | `frontend/src/components/review/ReviewPage.tsx` | Simplified to two tabs: Flagged (default) and All Reconciliation Items |
| 1.2.3 | `ReviewPage.tsx`, `review/router.py` | Added "Approve All & Generate Model" one-click button |

Also note: `isFlagged` predicate was fixed per ADR intent in `issues_charter.md` Ticket 3.4 — confidence score threshold removed; only `status`-based predicate used.

