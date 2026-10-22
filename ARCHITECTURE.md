# Footnote Architecture

The repository now holds a working pipeline: EDGAR ingest, a deterministic bridge
engine, an append-only observation store, analytics, a read API, a web app and an
Excel export. It runs locally on SQLite (ADR-010). The hosted target (Neon, R2,
Cloud Run, Cloudflare Pages) and the phase that introduces each part are in
[docs/ROADMAP.md](docs/ROADMAP.md) §4. Phase 0's exit gate is still open (owner-only
interviews and spec review), so everything past Phase 0 is built but not yet
gate-approved.

## Modules

```
backend/app/
├── ingestion/edgar/     EDGAR gateway (only network code): submissions, 8-K item filter,
│                        cached filing index and documents, same-day companyfacts cache
├── ingestion/exhibit_99/ legacy EX-99 extractor (kept for the P0-10 baseline scorer)
├── extraction/
│   ├── bridge/          core.py (rows, periods, tie-out solver, scale, XBRL anchor),
│   │                    engine.py (headline-table selection), keys.py, patterns.py
│   ├── html/            table_parser, detector, ixbrl_parser, legacy extractor
│   ├── locator.py, models.py, scale_and_sign.py
├── classification/      seed taxonomy (legacy alias matching)
├── store/               schema.sql + db.py: append-only SQLite observation store
├── pipeline/            ingest.py (orchestration), universe.py, cli.py
├── analytics/           classify.py (rule suggestions), history.py (quarters, recasts,
│                        definition changes), normalize.py (policy, recurrence),
│                        snapshot.py (read model), policies/footnote-default-v0.1.yaml
├── api/                 FastAPI read API + web app host
└── export/              Excel workbook (live formulas, source comments)
web/index.html           single-page app (served by the API, or static with snapshot.json)
config/universe.yaml     50 issuers, CIKs resolved from EDGAR (tools.universe.build)
```

Data flow:

```
EDGAR ─► pipeline.ingest ─► extraction.bridge.engine ─► store (bridges, periods,
         (Item 2.02 8-Ks,      (table selection, sum      observations, checks,
          EX-99.1, XBRL)        tie-out, XBRL anchor)      failures, runs)
                                                              │
                         analytics (quarters, recasts, changes, normalization)
                                                              │
                         api / web / export ◄── snapshot (read model)
```

Commands (from `backend/`, `SEC_USER_AGENT` set for ingest):
`python -m app.pipeline.cli ingest --quarters 8`, `python -m app.pipeline.cli export`,
`uvicorn app.api.main:app --port 8000`, `python -m tools.eval.score_bridge`.

## Dependency rules

These are enforced by `backend/tests/test_architecture_boundaries.py`:

1. Only `ingestion/edgar/` performs network I/O.
2. No module imports an LLM SDK (groq, openai, anthropic, ...).
3. `extraction/` and `classification/` never import `ingestion/`.
4. `classification/` never imports `extraction/`.
5. `store/` imports neither `ingestion/` nor `extraction/`.
6. `analytics/`, `api/` and `export/` never import `ingestion/` or `pipeline/`:
   served numbers come from stored observations, never a live fetch.

## Engineering principles

These carry over from the earlier product because they still hold:

- **Deterministic numbers.** Every extracted or normalized value comes from
  deterministic code. If an LLM is introduced later, it may assist with labels
  but must never produce or alter a number.
- **No silent failure.** Anything skipped, unparseable, or ambiguous returns an
  explicit status or reason (`not_found_reason`, `flag_reason`,
  `ForeignFilerUnsupportedError`). It is never dropped or defaulted quietly.
- **Provenance on every number.** An `ExtractedRecord` carries the raw
  as-reported string plus a `Locator` back to its source. A record without
  provenance fails validation (`require_provenance`); it is never padded out.
- **Honest validation.** A feature counts as working only once it has run on a
  real saved SEC filing and a human has checked the output against the source.
  Fixture and mock tests are necessary but not sufficient. Any accuracy number
  must state its sample size and label provenance.

## Known gaps

Verified against the code and the 2026-10-23 run (`eval/RESULTS.md`):

| Area | Gap |
|---|---|
| EDGAR client | Reads only `filings.recent` (enough for 8 quarters of the 50 issuers); `filings.files` paging (P1-04) not built. |
| Bridge engine | Bridges laid out in reverse (EBITDA down to net income, e.g. BYD), tables that interleave amount and margin columns (USFD), and metrics other than EBITDA/OIBDA (AMCX "Adjusted Operating Income") are not found and are recorded as failures with a reason. Only one bridge per release (the headline) is kept. |
| XBRL anchor | Net income / operating income / pre-tax concepts only; dimensional facts are not used. |
| Categories | Deterministic label rules suggest categories (`source='rule'`); no human has confirmed any yet. Unmatched labels are `OTHER` and block the normalized figure. |
| Normalization | Policy v0.1 is a draft (P0-14 open): every normalized figure is a preview. |
| Hosting | Local only (SQLite, accession cache). Neon/R2/Cloud Run need the owner's accounts. |
| Validation | Gold set: 1,297 of 1,304 labels are `model_agreement`; second-labeller agreement (P4-13) not done, so no accuracy figure may be published. |
