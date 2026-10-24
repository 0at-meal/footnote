# ADR-006: Public filing data is global and append-only; customer data is tenant-scoped

- **Status:** Accepted
- **Date:** 2026-10-17 (decisions taken 2026-10-14, DECISIONS.md)
- **Deciders:** owner; drafted under P0-15
- **Phase introduced:** 1 (global tables, P1-01); 4 (tenant tables and RLS, P4-02)

## Context

Every customer sees the same public facts: what an issuer reported, in which filing, and how
it ties out. Customers also create private data: watchlists, notes, normalization policies
and corrections. Recasts and definition changes are a core product signal, so history must
never be lost.

## Decision

1. **Global schema** for public data, keyed by CIK + accession + period. Tables include
   issuers, filings, documents, bridges, `bridge_line_observations`, `xbrl_facts`,
   `tieouts`, `label_memory`, `changes`, `verifications` and `failures`. One copy of the
   public data is shared by all tenants.
2. **Append-only observations.** A reported value is an observation tied to the filing it
   came from: `(issuer, metric, period, line_key, value_raw, value, scale, sign, quote,
   xpath, accession)`. Nothing is overwritten.
   - "As first reported" is the earliest observation, and "current" is the latest.
   - A recast is two observations of the same key with different values.
   - Normalized results are stored with their `policy_version` (ADR-008).
3. **Tenant schema** (Phase 4) for customer data: orgs, users, watchlists, notes,
   policies, opt-in corrections and API keys. It is isolated by Postgres row-level security
   on `org_id`, and a cross-tenant read test must fail.
4. **Crossing the boundary.** Customer corrections reach the global record only with an
   org-level opt-in and anonymization, and only after verification. The terms are
   written into the ToS (P4-10, P4-11).

## Consequences

- Point-in-time queries and recast detection are plain queries, not a versioning system.
- Storage grows with every observation. This is acceptable: about 36K rows at 150 issuers ×
  8 quarters (ROADMAP §6).
- The first request for physically isolated data is a trigger for a new ADR (ROADMAP §6),
  not something to solve in advance.

## Alternatives rejected

- **Per-tenant copies of public data:** duplication with no benefit, and copies would drift
  apart (DECISIONS 2026-10-14).
- **`superseded_by` chains or in-place updates:** they lose "as first reported" and make
  recasts harder to see.
