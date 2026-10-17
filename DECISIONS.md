# Footnote: Decision Log

Newest first. One entry per decision, with date and reason. Entries before
2026-10-14 are recoverable from git history (tag `v0-extraction`). Several of
those entries described features as deployed that were never wired into the
running app (see the retraction below).

- **2026-10-17: ADRs written for the current direction (P0-15).** `docs/adr/`:
  - ADR-005 ingest: scheduled batch, one EDGAR gateway, write-once R2 raw store;
  - ADR-006 global append-only public data vs. tenant data under RLS;
  - ADR-007 no pack abstraction before Phase 5, and declarative `PackSpec` then;
  - ADR-008 all processing offline, with a read-only online path;
  - ADR-009 $0 infrastructure with migration triggers.

  They restate decisions already taken on 2026-10-14 and add none. ADR-001 to ADR-004
  (removed product, tag `v0-extraction`) are retired, and their numbers are not reused.
- **2026-10-17: Normalization spec v0.1 drafted (P0-13); not frozen.**
  [docs/NORMALIZATION.md](docs/NORMALIZATION.md) now defines 24 codes in four groups:
  components, adjustments, scope (`RENT`, `CORP`) and control (`MIXED`, `OTHER`). Main
  choices beyond ROADMAP §3, each open for analyst review (P0-14):
  - `NCI` and `NONOP` are components, accepted.
  - `RESTR`, `TRANSFORM`, `MA`, `LITIG` and `ENV` are *accept-unless-recurring*.
  - `RENT` and `CORP` are excluded, so normalized EBITDA is consolidated EBITDA.
  - `MIXED` lines take the strictest treatment among their constituents.
  - Any `OTHER` line blocks the computation.

  The recurrence rule has three outcomes (recurring / not recurring / unknown). An unknown
  result never flips a treatment, and quarters are not derived from LTM/YTD in v0.1. Worked
  examples use real gold-set bridges cited by accession and line. Their category assignments
  are the author's illustration, not label memory. The reviewer brief and feedback form are
  in `docs/discovery/`.
- **2026-10-17: P0-11 interview kit and pass-rule scoring.** The kit is in
  `docs/discovery/`: recruiting, script, rubric, scoresheet, notes template and tracker. The
  ICP pass rule (ROADMAP §2) is applied as follows:
  - Each criterion is scored yes / no / unclear, and every yes needs a quote or fact.
  - *Unclear* counts against passing: as no for A and B, as yes for C.
  - "At least 3 name a price anchor or ask for a trial" is computed both over all 8 and
    over those who meet A. If the two disagree, the stricter reading decides.
  - The result may be declared early only when the remaining interviews cannot change it.
    So Phase 1 can open after 5 interviews only on an early PASS (5 A, ≥3 B, 0 C).
  - Interviewees are pseudonymous in the repository; identities stay outside git.
- **2026-10-17: P0-10 extractor regression gate.** CI (and `make check`) runs
  `python -m tools.eval.score --check eval/thresholds.yaml`. It fails if any headline metric's
  overall rate (table_found, line_exact_match, scale_accuracy, sign_accuracy) drops below the
  committed floor, or if the scorer version or gold-label sha256 differ from the ones the
  floors were recorded on, since rates across different gold sets or scorers are not
  comparable. Floors start at the P0-09 baseline and move only deliberately: in their own
  commit, with a RESULTS entry and a DECISIONS entry, never lowered to make CI green. The
  `verified_by` split is reported but not gated: the `human` group has 5 scored values.
- **2026-10-17: P0-08 scorer lives at `backend/tools/eval/score.py`.** ROADMAP names
  `eval/score.py`, but mypy strict and the import root cover only `backend/`, so the scorer
  sits with the other gold tools and runs as `python -m tools.eval.score` (`make score`).
  It is offline (reads only the saved `.gz` exhibits, sha256-checked; it never imports
  `app.ingestion`) and deterministic. Metric definitions, fixed with the scorer:
  - The unit is one gold *value* (line x period), so every metric splits by `verified_by`.
    Dash placeholders (102 of 1,304) are not scored. Table-found and scale are also
    reported per release.
  - **Line exact match** needs the right table (the extractor's top-ranked candidate),
    the label (normalized as in `tools.gold.compare`; k-th occurrence aligns to k-th), the
    period (the extractor's period string must identify exactly one gold period) and the
    value. A period-agnostic `line_label_value_match` is reported beside it as a diagnostic
    so period binding (P2-03) can be measured on its own.
  - **Scale** is what `detect_scale_from_caption` finds in the extractor's table title,
    the only caption the extractor passes on today.
  - **Sign** compares the direction `detect_sign` gives the located cell with the gold
    contribution sign(sign x value). Unlocated values count as wrong, so the metric cannot
    rise when coverage falls.
  - The extractor is run with its default `target_metric`; gold metric labels are not
    passed in, so the score is what a caller gets today.

  Finding: `get_element_xpath` uses `list.index`, and BeautifulSoup compares tags by
  content, so structurally identical siblings share an XPath. On the gold set, hundreds of
  cell XPaths per release collide. The scorer therefore attributes records to tables by
  replaying the extractor's public pipeline and checking it record by record against the
  real output (any divergence raises). The XPath bug is logged for Phase 1/2, not fixed here.
- **2026-10-17: P0-06 review done; gold set promoted.** The owner confirmed all 30 table
  selections on sec.gov and resolved the 7 queue items. Decisions are recorded in
  `eval/gold/review_decisions.yaml`, the single source for `tools.gold.promote` and for the
  review status in `review_queue.md`. Promotion refuses to write any label unless every table
  is confirmed at the drafted index, every queue item has exactly one resolution, and every
  value is verified. Result: 30 label files and 1,304 values (1,297 `model_agreement`,
  7 `human`). `labels --validate --strict` passes and now runs in CI and `make gold-verify`.
  Resolutions:
  - The 4 anchors missing from companyfacts (CAR and HTZ Q2) were confirmed against each
    10-Q's inline XBRL.
  - The CC LTM "mismatch" was the anchor mixing restated XBRL vintages (FY2024 69 +
    Q1 2025 −5 − Q1 2024 54 = 10). Every consistent vintage gives the release's 12, so
    this is not a recast.
  - The FUN Q1 non-controlling-interest row, blank in both columns, is a deduction (−1),
    as the same row ties out in Q2.

  Review also found that a data row above the GAAP start leaked into period labels (CC).
  This is fixed in the draft tool; no values changed.
- **2026-10-14: P0-05b independent reading done.** Claude transcribed all 30 bridges from the
  approved tables rendered as raw cell text (`tools.gold.render_table`, no extractor logic),
  recording periods, scale (with quoted evidence), labels, roles, signs and every value. The
  comparison (`tools.gold.compare`) found one disagreement in 1,304 values: a sign on a row
  that is blank in every column, which arithmetic cannot settle. 1,231 values (94.4%) are
  `model_agreement` (both P0-05 checks pass and the reader agrees). The other 73 stay
  unverified until the owner resolves them. Limits of independence: the reader used the
  P0-01 table choice and the same HTML cell text, so table selection and source-text errors
  are not covered; the owner's table confirmation in P0-06 covers the former.
- **2026-10-14: P0-05 drafts; parser fix found on real filings.** `parse_numeric_cell` treated a
  cell that is only a single-digit negative, e.g. "(7)", as a footnote marker and dropped the
  value; it now strips a trailing footnote only when something remains. The draft tool also
  handles four real-filing layouts deterministically: parentheses split across cells, top-down
  bridges (items shown with income-statement signs), header spans misaligned with value columns
  (columns then assigned by phrase order) and labels wrapped over two rows. A single inferred
  sign flip is applied only if it makes every period tie out, and is reported as a note for the
  owner. Results: 100/100 sum tie-outs, 95/100 XBRL anchors (5 are genuine: SEC companyfacts
  lacks two Q2 2026 10-Qs, and one LTM figure differs from XBRL by 2, a likely recast). One
  table choice was revised after approval (FUN Q1, table 9 → 4); the revision is recorded in
  `eval/gold/issuers.yaml`.
- **2026-10-14: Lean, tie-out-first gold-set labelling (ROADMAP Phase 0).** The extractor
  auto-drafts each bridge. Two independent checks run: the sum tie-out (within
  max(1, ⌈n/2⌉) units) and the GAAP anchor against XBRL `companyfacts`. Claude independently
  reads every filing as a second reader. The owner only confirms table selection and resolves
  exceptions: failed checks and Claude/extractor disagreements. Every label records
  `verified_by` (`tieout` / `model_agreement` / `human`), and the scorer reports accuracy split
  by it. Second-labeller agreement moves from the Phase 0 exit gate to a Phase 4 gate, required
  before any accuracy number is shown or published.
  *Why:* the same honesty guarantee (the answer key is never just the system under test) at
  about 25% of the manual effort (~2–3 h instead of ~8–10 h). Arithmetic tie-outs and XBRL
  anchors catch value, sign and scale errors; a human check covers what they cannot, namely
  wrong table selection.
- **2026-10-14: Direction adopted — see [docs/ROADMAP.md](docs/ROADMAP.md).** Footnote becomes
  the verified, versioned, normalized record of how US-listed issuers define and adjust EBITDA,
  for credit / leveraged-finance analysts first (fallback persona: equity earnings-quality).
  *Why:* reconciled an external research report and an independent stress test against the
  code and primary sources; the moat is point-in-time verified history, a normalization
  standard with customer policy profiles, and change intelligence (Daloopa is "as reported",
  merges renamed lines and hides restatements by default).
- **2026-10-14: Report items rejected.** PDF/Docling as the non-GAAP source (official EDGAR
  filings are HTML/iXBRL; bridges sit in untagged EX-99.1 HTML), per-tenant copies of public
  data, a YAML pack DSL, Sidequest (Node.js only), HF Spaces as the production backend
  (sleeps after 48 h, non-persistent disk), demo before measured accuracy, and LLM
  classification. Sources in ROADMAP §10.
- **2026-10-14: Stress-test items corrected.** Private-repo GitHub Actions cron works (2,000
  free min/month; the 60-day auto-disable is for public repos). Review burden is bounded by
  issuer-scoped label memory plus automatic sum/XBRL tie-outs. Sum tie-out tolerance is
  max(1, ⌈n/2⌉) units of reported scale, not ±1.
- **2026-10-14: Strict $0 infrastructure until first revenue.** GitHub Actions scheduled
  ingest, Neon free, Cloudflare R2 + Pages, Cloud Run free (Phase 4), Clerk, Resend, Stripe
  Payment Links; HF Spaces only for a public demo. Migration triggers in ROADMAP §6.
- **2026-10-14: Public filing data is global; customer data is tenant-scoped (RLS).** Public
  facts are keyed by CIK + accession + period and shared; watchlists, notes, policies and
  opt-in corrections are per organisation.
- **2026-10-14: Append-only observation model.** Every reported value is an observation tied
  to the filing it came from; "as first reported", "current" and recasts are queries, never
  overwrites.
- **2026-10-14: Gates before build.** Phase 1 opens only after the 30-release gold set, the
  ICP pass rule (≥5 of 8 interviews) and an analyst-reviewed normalization spec
  ([docs/NORMALIZATION.md](docs/NORMALIZATION.md)).
- **2026-10-14: Merged `origin/main` (39 commits, PR #2 "fix/audit-phases-0-3")
  into the clean base.** That work had not been in the local checkout. Fixes
  to kept modules were adopted: CIK-qualified SEC Archives URLs
  (`sec_archives_url`), records without provenance are rejected
  (`require_provenance`), `FOOTNOTE_DATA_DIR`, test data isolation, and CI
  (trimmed to the backend). Its fixes to removed modules, the frontend e2e
  suite, `tools/`, and the phase 0–3 audit report (`docs/audit/`) were not
  carried over because they concern the removed product. They remain in git
  history at `ea7d318`. The audit's open item "seed taxonomy must be
  versioned" is resolved by `seed_taxonomy.json`.
- **2026-10-14: Reset to a clean base.** Removed the PDF → workbook product
  from `main`: FastAPI app, job runner, Docling/PyMuPDF extraction, Groq
  classifier, formula engine, Excel export, review, audit trail/report, drift,
  footnote packs, and the React frontend. Kept the deterministic core: EDGAR
  client, EX-99.1 detection/extraction, HTML table / iXBRL parsing, locators,
  scale and sign normalization, and the taxonomy. *Why:* the next direction is
  under review, and the removed code was unvalidated on real filings. Everything
  is preserved at tag `v0-extraction`.
- **2026-10-14: Fabricated evaluation corpus deleted.** `eval/` labels were
  generated by a script, not annotated. For example, "MSFT" rows carried
  Amazon's CIK, and second-annotator agreement was hard-coded. The only real
  benchmark run scored 0% on five synthetic PDFs. *Rule going forward:*
  accuracy numbers require real filings, human labels with provenance (who,
  when, source URL), and a stated sample size.
- **2026-10-14: Retraction.** Earlier entries claiming a hosted SaaS
  architecture, a deployed EDGAR-first ingestion cascade, a shared extraction
  cache, an LLM provider abstraction, and a CI regression gate were not true of
  the code. The EDGAR/HTML/EX-99 modules existed but were reachable only from
  tests, and no CI existed.
- **2026-10-14: SEC User-Agent is required.** The EDGAR client no longer falls
  back to a made-up contact address; it raises if `SEC_USER_AGENT` is unset.
- **2026-10-14: Unknown scale is flagged, never guessed.**
  `normalize_line_item` previously defaulted to thousands and multiplied
  unknown-scale values by 0. It now returns no normalized value plus a flag.
- **2026-10-14: No fabricated SEC URLs.** The HTML extractor used to build
  archive URLs with the accession where the CIK belongs. It now builds a
  CIK-qualified Archives URL only when the CIK is known (or accepts a valid
  Archives URL from the caller); otherwise the URL is `None`.
- **2026-10-14: Second review pass: correctness fixes in kept code.**
  - The taxonomy seed is now a tracked file (`seed_taxonomy.json`). It was
    previously read from untracked runtime data, so tests failed on a fresh
    clone. Junk entries and aliases that the old review UI had added (e.g.
    "Comprehensive income / 23,662") were dropped.
  - Fuzzy taxonomy matches are suggestions only and never count as matched.
  - Scale exemptions no longer treat any label containing "margin", "shares",
    or "rate" as unscaled.
  - EDGAR exhibit types are read from the index's type column. Previously
    filenames such as `x-ex991.htm` produced a bogus "EX991." type, and a
    filename-only match was guessed as EX-99.1.
  - Index fetch failures now raise instead of returning an empty list.
  - Leading minus signs (including U+2212) now parse as negatives.
  - Unknown locator payloads now raise instead of becoming a fake
    `unknown.pdf` locator.
  - Test fixtures that attached invented financials to real companies were
    relabeled as synthetic.
  - Seed taxonomy cleanup from a full read of every entry: removed aliases
    that conflate different metrics ("EBITDA" and "Adjusted Operating Income"
    under Adjusted EBITDA), misfiled lines (a cash-flow acquisitions line as
    an add-back; "Goodwill and other intangibles" as Goodwill), mojibake
    duplicates, and invented " cf" aliases.
  - A corrupt taxonomy override file now raises instead of silently falling
    back to the seed and discarding user-confirmed entries.
- **Carried forward (pre-2026-10-14, still holds):** numbers are produced only
  by deterministic code. An LLM may never read or write a numeric value.
  Deterministic alias matching comes before any probabilistic matching.
  Failures surface explicitly, never silently. Every extracted value keeps its
  as-reported string and a source locator.
