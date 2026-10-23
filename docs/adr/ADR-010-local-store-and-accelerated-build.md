# ADR-010: Local SQLite observation store, and building Phases 1–4 engineering ahead of the Phase 0 gate

- **Status:** Accepted (owner directive, 2026-10-23)
- **Date:** 2026-10-23
- **Deciders:** owner (instruction to the agent run of 2026-10-23); drafted by that run
- **Phase introduced:** 1 (P1-01 local edition)

## Context

On 2026-10-23 the owner asked the agent to "go through all the phases" ahead of an investor
meeting on 2026-10-24. The Phase 0 exit gate (`eval/RESULTS.md`) is not met. Rows 4 (ICP
interviews) and 5 (spec review) need real analysts, and only the owner can run those.
ROADMAP §5.10 (no paid infrastructure until first revenue) and the accounts in ROADMAP §8
(Neon, R2, Cloud Run, Clerk, Stripe) also need the owner. An agent may not create accounts.

## Decision

1. **Engineering for Phases 1–4 is built now, behind the unmet gates.** Built: ingestion
   (P1-04/05/08/09/10), the bridge engine with automatic table selection (P2-01/04/05/06),
   label memory with rule suggestions (P2-07), the versioned policy file (P2-08), recasts,
   definition changes, recurrence and normalized EBITDA (P3-03 to P3-06), the read API
   (P4-01), the web app (P4-03 to P4-05) and the Excel export (P4-07). The gates stay as
   written. Nothing here marks Phase 0 complete, and nothing is sold on these results
   before the gates are met.
2. **Local SQLite edition of schema v1.** `backend/app/store/schema.sql` implements the
   ROADMAP §4 global tables (issuers, filings, bridges, periods, observations, checks,
   failures, runs, label_memory) on SQLite with the standard library. The schema is plain
   SQL with no SQLite-only types, so it ports to Neon Postgres (ADR-006) when the owner
   opens that account. Alembic is deferred to that move.
3. **Raw documents** stay in the immutable EDGAR accession cache (`backend/data/edgar_cache`,
   gitignored). Each filing row records the exhibit's sha256. R2 (ADR-005 §3) replaces
   this when the account exists.
4. **Engine versions are append-only.** A new engine version re-extracts every filing into
   new rows. The view `current_bridges` serves each filing's most recent extraction.
   Older extractions are kept for audit.
5. **What is labelled preview.** Normalized EBITDA is computed under draft policy v0.1 and
   shown as a preview, because the spec is not frozen (P0-14). Categories come from
   deterministic label rules (`app/analytics/classify.py`) recorded as `source='rule'`,
   shown as pending review, and always overridden by a human decision. No LLM is used.

## Consequences

- The demo runs on the owner's machine (`uvicorn`) and as a static export with no account.
- Moving to Neon/R2/Cloud Run is a port, not a rewrite: the store is behind one class.
- Customer-facing accuracy claims remain blocked by P4-13 (second labeller).
