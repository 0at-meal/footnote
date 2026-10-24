# ADR-005: Ingest public filings in scheduled batches from EDGAR into a write-once raw store

- **Status:** Accepted
- **Date:** 2026-10-17 (decision taken 2026-10-14, ROADMAP §4)
- **Deciders:** owner; drafted under P0-15
- **Phase introduced:** 1 (P1-02, P1-04, P1-05, P1-07, P1-09–P1-11)

## Context

Footnote's raw material is public SEC filings:
- Item 2.02 8-Ks with an EX-99.1 earnings release in HTML;
- 10-Q and 10-K HTML/iXBRL;
- XBRL `companyfacts` for GAAP anchors.

Non-GAAP bridges sit in untagged EX-99.1 HTML, not in PDFs. The SEC requires a declared
User-Agent and limits clients to 10 requests per second. Filings are immutable once
accepted. Recasts arrive as *new* filings, never as edits to old ones.

## Decision

1. **One gateway.** Only `backend/app/ingestion/edgar/` touches the network
   (`EdgarClient`): SEC User-Agent from the environment, a ≤10 req/s token bucket, 429
   backoff, a circuit breaker and an immutable accession cache. This is enforced by
   `test_architecture_boundaries.py`.
2. **Sources.** Submissions (including `filings.files` paging), filing indexes, EX-99.1
   HTML, 10-Q/10-K HTML and XBRL `companyfacts`. HTML/iXBRL is primary. PDF and image
   exhibits are logged as unsupported, never guessed.
3. **Raw store.** Every fetched document is written once to object storage (Cloudflare R2),
   keyed by accession and document, with its sha256. Bytes are never modified. Parsing
   always reads from the raw store, so any result can be reproduced from the stored bytes.
   This is the same pattern the gold set already uses: `eval/gold/raw/` plus a sha256
   manifest.
4. **Schedule.** Ingest is a scheduled batch: a GitHub Actions cron on the private repo
   with manual dispatch. Cloud Run Jobs + Cloud Scheduler is the fallback. There is no
   always-on worker or queue.
5. **Idempotent and explicit.** Re-running a window creates no new rows. Every skip or
   failure is written with stage and reason, and the retry policy is transient vs.
   permanent (P1-10).

## Consequences

- Reprocessing (a parser fix, a new policy version) needs no SEC traffic: re-read R2.
- Freshness is bounded by the cron interval (daily, with more frequent runs in earnings
  weeks if needed). The product does not promise real-time data.
- Each run's cost is visible in minutes and Neon CU-hours, logged per run (ROADMAP §6).

## Alternatives rejected

- **PDF/Docling extraction** as the source of bridges: official filings are HTML/iXBRL
  (DECISIONS 2026-10-14).
- **A persistent queue or worker** (Procrastinate, Sidequest): Sidequest is Node.js only, and
  a queue adds always-on cost with no need at ~150–1,000 issuers. Procrastinate stays the
  fallback if a queue is ever needed.
- **Scraping third-party aggregators:** licensing risk and lost provenance.
