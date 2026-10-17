# ADR-008: All extraction and normalization runs offline; the online path only reads

- **Status:** Accepted
- **Date:** 2026-10-17 (follows from ROADMAP §4–§5 and DECISIONS 2026-10-14)
- **Deciders:** owner; drafted under P0-15
- **Phase introduced:** 1 (offline pipeline); 4 (read API, P4-01)

## Context

Every served number must come from deterministic code, carry provenance, and be checked
(tie-outs, review) before a customer sees it. Free hosting scales to zero and has cold
starts. Accuracy is measured offline on a gold set, and CI blocks regressions (P0-08–P0-10).

## Decision

1. **Offline (batch):**
   - ingest (ADR-005);
   - parsing;
   - bridge extraction;
   - tie-outs;
   - label memory and review;
   - recast and definition-change detection;
   - normalization under a named `policy_version`;
   - alert generation.

   These run in scheduled jobs or CLI tools. They write observations and results to the
   global schema (ADR-006). Each result records the code version and policy version that
   produced it.
2. **Online (request time):**
   - the FastAPI read API, the web app and exports **only read** stored results, plus the
     tenant's own data;
   - nothing parses a filing, calls the SEC or runs extraction inside a request;
   - a customer policy profile (Phase 5) is applied by the same deterministic
     normalization code over stored, verified bridges. Whether that happens at read time
     or as a batch is decided in Phase 5.
3. **No LLM on either path produces or alters a number.** Label *suggestions* (P3-08) are
   an offline step behind human confirmation.
4. **Evaluation is offline too.** The scorer reads only saved, sha256-checked exhibits,
   never the network (P0-08), so results are reproducible.

## Consequences

- Request latency and cost do not depend on SEC availability or parsing time. A cold start
  is the main latency risk; it is measured (P4-08) and mitigated only if p95 > 2 s (P4-09).
- A number a customer sees has been through the same checks as the gold set. No unchecked
  "live" extraction can reach them.
- Data is as fresh as the last batch run (ADR-005), which is acceptable for quarterly
  filings.

## Alternatives rejected

- **On-demand extraction when a user opens an issuer:** unverified numbers would reach the
  customer, the request path would depend on SEC traffic, and costs would be unbounded.
- **An always-on worker that processes filings continuously:** it costs money while idle and
  adds nothing at quarterly cadence (ADR-009).
