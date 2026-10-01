# Footnote — Architectural Decisions Log

Format: one line per decision, with date and context.

- **2026-10-01**: Hosted SaaS replaces local-first architecture to support institutional analyst workflows, shared caches, and multi-tenant security.
- **2026-10-01**: EDGAR-first ingestion replaces PDF-only ingestion; iXBRL and HTML tables provide authoritative source data with PDF as fallback.
- **2026-10-01**: Groq free tier is not a production dependency; classifier abstracted to support enterprise LLM providers with deterministic fallback.
- **2026-10-01**: 6-tab multi-statement generator retired (FN-001); non-GAAP reconciliation bridge and multi-period bridge are the core product focus.
- **2026-10-01**: Narrative intelligence (MD&A / Risk factor diffing) removed from pipeline to focus entirely on numerical reconciliation accuracy and trust.
- **2026-09-02**: 2-tab Excel output format (Source_Inputs + Reconciliation) selected as primary financial model standard (ADR-002).
- **2026-09-01**: Review UI scoped to flagged items only; auto-accepted items pre-locked to maximize reviewer velocity (ADR-001).
- **2026-09-01**: Target metric automatically scoped per workflow pack; `non_gaap_bridge` defaults to Adjusted EBITDA (ADR-001).
- **2026-08-25**: xlsxwriter chosen over openpyxl to enforce deterministic, fresh workbook generation from scratch (CONSTITUTION §4.2).
- **2026-08-20**: Deterministic alias matching executes before LLM classification to guarantee zero token cost and 100% reproducibility for known items.
