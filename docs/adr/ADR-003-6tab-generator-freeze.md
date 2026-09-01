# Architectural Decision Record (ADR) 003: 6-Tab Multi-Statement Generator — Frozen as Beta Feature

* **Status:** ✅ Decision Made — Generator Frozen
* **Date:** 2026-08-29
* **Decided by:** Business alignment diagnosis (`docs/business_alignment.md` §1.2)
* **Deciders:** Antigravity Team

---

## 1. Context and Problem Statement

During Refinement Phase 2, a 6-tab multi-statement Excel generator
(`backend/app/excel_export/multi_statement_generator.py`, ~1,260 lines) was built to
produce a full institutional financial model:

1. Executive Summary
2. Income Statement
3. EBITDA & Non-GAAP Bridge
4. Cash Flow & FCF
5. Balance Sheet & Net Debt
6. Audit & Provenance

This generator was proposed in `docs/archive/proposed_changes.md` as the default output
path for the platform.

However, after the generator was built and evaluated, a business alignment diagnosis
(`business_alignment.md`) identified three compounding problems:

1. **No subscription value vs. terminals.** Bloomberg and FactSet already serve Income
   Statement, Balance Sheet, and Cash Flow data in cleaner form. No buy-side analyst
   builds these from raw PDF extraction — they pull them from the terminal. The generator
   solves a problem that practitioners do not have.

2. **Architectural fragility.** The generator is tightly coupled to
   `ComprehensiveModelTree`, which requires all six statement types to be populated. A
   filing with only an Adjusted EBITDA reconciliation table (the most common case)
   triggers partial-tree generation errors.

3. **Silent scope expansion.** The original spec promised an Adjusted EBITDA model. The
   6-tab generator expanded scope without institutional buyer confirmation.

---

## 2. Decision

**The 6-tab multi-statement generator is frozen as a clearly-labeled beta feature.**

- `generator.py` (the original 2-sheet `Source_Inputs` + `Reconciliation` generator)
  remains the **default, shipping output path**.
- `multi_statement_generator.py` is retained in the codebase behind a feature flag, not
  the default pipeline path.
- No further investment in the 6-tab generator until a pilot client explicitly requests
  and validates a multi-statement output format.

The **active product scope** is:
> Upload a 10-K/10-Q → extract the Non-GAAP reconciliation bridge → generate a
> provenance-linked 2-sheet `.xlsx` workbook → enable analyst review and model generation.

---

## 3. Consequences & Benefits

* **Positive:** Eliminates a 1,260-line surface area from the default execution path,
  reducing the probability of layout-triggered generation failures.
* **Positive:** Refocuses engineering toward actual subscription differentiators:
  footnote-level data extraction, EDGAR integration, narrative delta tracking.
* **Negative/Trade-off:** Users expecting a full 3-statement model from a single upload
  will not get it out of the box. This is intentional until market validation occurs.

---

## 4. Guard Rails

- Any future investment in the multi-statement generator requires: (a) a named pilot
  client who has confirmed the format meets their workflow, and (b) an explicit ADR
  updating this one.
- The `multi_statement_generator.py` must not be imported from the default pipeline path
  (`job_runner.py`) without removing this guard rail first.
- Features that depend on `ComprehensiveModelTree` (e.g., the 6-tab audit sheet) must
  not be presented as default UI elements — they must remain clearly labeled as beta.
