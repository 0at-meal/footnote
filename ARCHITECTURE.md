# Footnote Architecture

The current state is a library of deterministic pieces, not an application.
There is no API server, UI, database, or orchestrator yet. The target
architecture and the phase that introduces each part are in
[docs/ROADMAP.md](docs/ROADMAP.md) §4; this file describes what exists today.

## Modules

```
backend/app/
├── ingestion/
│   ├── edgar/          client.py, rate_limiter.py, circuit_breaker.py, models.py
│   └── exhibit_99/     detector.py, extractor.py, models.py
├── extraction/
│   ├── html/           table_parser.py, detector.py, ixbrl_parser.py, extractor.py, models.py
│   ├── locator.py      PdfLocator | HtmlLocator discriminated union
│   ├── models.py       ExtractedRecord
│   └── scale_and_sign.py
└── classification/
    ├── taxonomy.py     master taxonomy, alias matching, fuzzy suggestions, add-back categories
    ├── seed_taxonomy.json  tracked seed (84 canonical items + aliases)
    └── models.py
```

Data flow available today:

```
EdgarClient.get_filings / get_filing_directory_index / get_document
        │  (raw HTML, cached by accession)
        ▼
Exhibit99Extractor  ──►  HtmlExtractor
                           ├─ extract_html_tables      (grid, numeric cells, XPath)
                           ├─ detect_reconciliation_tables
                           └─ parse_ixbrl_facts
        ▼
list[ExtractedRecord]  (value as reported, label path, HtmlLocator)
        ▼
scale_and_sign.normalize_line_item   taxonomy.match_master_taxonomy
```

No orchestration connects these steps yet. Callers compose them directly.

## Dependency rules

These are enforced by `backend/tests/test_architecture_boundaries.py`:

1. Only `ingestion/edgar/` performs network I/O.
2. No module imports an LLM SDK (groq, openai, anthropic, ...).
3. `extraction/` and `classification/` never import `ingestion/`.
4. `classification/` never imports `extraction/`.

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

These are verified against the code as of 2026-10-14:

| Area | Gap |
|---|---|
| EDGAR client | Reads only `filings.recent` from the submissions API. Older filings (`filings.files` pages) are not fetched. There is no 8-K `items` filter (e.g. 2.02). Default cache dir is relative to the working directory. |
| HTML extractor | Records use placeholder legacy PDF fields (`page=1`, full-page bbox). `HtmlLocator.url` is a CIK-qualified Archives URL when the caller passes `cik` (or a valid Archives URL); otherwise it is `None`, never derived from the accession alone. The detector is keyword-based and defaults to "Adjusted EBITDA". |
| Table parser | Column → period binding is heuristic. Caption scale is not passed into `scale_and_sign`. `row_headers` only reads label text in columns 0–1, so indented bridge labels in later columns are missed (seen in a real EX-99.1, 2026-10-14). Titles placed in elements before the table are often not captured, so many tables fall back to `Table N` (all 30 gold tables do, 2026-10-17). Period headers are searched only in the first four rows. `get_element_xpath` uses `list.index`, and BeautifulSoup compares tags by content, so identical sibling elements get the same XPath; cell XPaths are not unique. |
| iXBRL parser | Handles `ix:nonFraction` with `endDate`/`instant` only. No `startDate`, dimensions, unit resolution, or `ixt` transforms. Facts with an invalid scale or unparseable value are skipped with a logged warning. There is no structured skip list yet. |
| EX-99 extractor | HTML only. PDF and image exhibits log a warning and return no records. |
| Taxonomy | The seed is `classification/seed_taxonomy.json` (84 items, tracked). `TaxonomyRepository` reads user overrides from `$FOOTNOTE_DATA_DIR/taxonomy.json` (default `backend/data/`, gitignored), and that file **replaces** the seed when present. The aliases are hand-written and unvalidated on a gold set. Fuzzy (token-set) matches are suggestions only (`is_matched=False`), because the metric scores 1.0 on token subsets. |
| Scale exemptions | Per-share / percent detection is label-keyword based. Share-count rows are scaled like dollar rows (correct for "in millions, except per share" tables, wrong for tables that state share counts in units). |
| Validation | 30-release gold set (`eval/gold/labels/`) and scorer (`tools.eval.score`). Baseline on 2026-10-17: table found 20/30 releases, line exact match 15.5%, scale 0%, sign 49.4% ([eval/RESULTS.md](eval/RESULTS.md)). |
