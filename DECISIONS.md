# Footnote: Decision Log

Newest first. One entry per decision, with date and reason. Entries before
2026-10-14 are recoverable from git history (tag `v0-extraction`). Several of
those entries described features as deployed that were never wired into the
running app (see the retraction below).

- **2026-10-24: Baselines B0–B2 (A-08).**
  `backend/tools/agent_eval/baselines.py`, `systems.py`. Choices:
  - All three baselines get the same system prompt. It describes the `SystemAnswer`
    JSON, the reason codes and the false-premise rule, so the baselines are judged on
    the format the agent uses.
  - The corpus is the question's issuers' EX-99.1 exhibits filed on or before `as_of`,
    read from the local EDGAR cache. Table rows become `cell | cell` lines.
  - **B1**: BM25 (k1 = 1.5, b = 0.75), pure Python, over 1,500-character chunks with a
    200-character overlap. The top 8 go in, each with its sec.gov URL.
  - **B2**: whole exhibits, newest first, up to 160,000 characters (about 40K tokens).
  - Output that is not valid JSON in the schema, or a stop reason other than end of turn
    (e.g. `refusal`), is recorded as an error with its reason, never repaired.
  - The baselines call no SDK. The model client is injected (A-07), so the boundary
    exception for an LLM SDK still waits for A-12.
  - System types moved to `tools/agent_eval/systems.py` to keep the harness and the
    systems free of import cycles.
- **2026-10-24: Harness, model-client interface and budget cap (A-07).**
  `backend/tools/agent_eval/run.py`, `backend/app/agent/model.py`,
  `eval/agent/pricing.yaml`. Choices:
  - Systems talk to a `ModelClient` protocol (Messages-API-shaped turns; raw blocks are
    kept so they can be appended back unchanged). No SDK is imported outside
    `app/agent/llm.py` (A-12). Tests use scripted fakes in `tests/agent/fakes.py`.
  - Prices live in `eval/agent/pricing.yaml`, taken from the claude-api skill's model table
    (cached 2026-10-06). Cache writes at 1.25× input and the Haiku 5.5 cache read at 0.1×
    are derived, and the file says so. A model without a price cannot be run.
  - **Hard cap.** Before every call, `BudgetedClient` reserves a worst case: `max_tokens`
    of output, plus input estimated at 2 characters per token, an over-estimate. It
    refuses the call if spend plus that reserve could exceed the cap, then charges the
    actual cost. So spend never crosses the cap. The run stops with exit code 2, and
    nothing is written for the unfinished attempt.
  - Runs resume: a (question, trial) already in `<out>/<system>.jsonl` is skipped.
    `--replay` re-scores transcripts with no client at all. A run writes
    `manifest.json` (model, split, systems, trials, budget) and `report.json`.
  - Until A-12 the CLI has no real client and says so.
- **2026-10-24: Answer schema, provenance gate and renderer (A-11).**
  `backend/app/agent/answer.py`, `gate.py`. Choices:
  - The model submits `AgentAnswer`:
    - status and reason codes;
    - prose with `{{vid}}` placeholders;
    - `values` (name + vid), `labels` (as-reported label + change) and `ranking`
      (tickers).
  - `Status` and `ReasonCode` move from the question schema to `app/agent/answer.py`.
    Both sides share them.
  - The gate rejects:
    - a numeral typed in prose or in a value name;
    - a number spelled next to a unit ("forty percent");
    - a malformed vid (*unknown*);
    - a well-formed vid the session's ledger does not hold (*unretrieved*);
    - a broken placeholder;
    - a partial or refused answer without a reason code.
  - The allow-list for prose: dates, years 1900–2099, period IDs, ISO dates, quarter and
    fiscal labels (Q2, FY2025, 2Q25, H1), accession numbers, SEC form names (8-K, 10-Q,
    EX-99.1, Item 2.02), and anything inside quotation marks.
  - Footnote markers such as "(1)" or "[6]" are *not* allowed outside quotes: "(5)" is
    also an accounting negative. As-reported labels must be quoted. On the local store,
    3 of 46 headline labels (AMC, FUN, NWL) carry such markers.
  - Known limit: a number that looks like a year passes as prose. It is never a cited
    value.
  - The renderer writes each cited value from the ledger: `$1,431.5 million` with its
    sec.gov link, or a computed value with its formula. A dash renders as "no amount
    reported". An unknown scale renders as "(scale unknown)".
- **2026-10-24: The compute tool's operations and refusals (A-10).**
  `backend/app/agent/compute.py`, exposed as the `compute` tool.
  - Eight operations: `contribution` (sign × value, so the agent never has to apply a
    bridge sign itself), `sum`, `difference`, `change`, `pct_change`, `share`, `ratio`,
    `count`.
  - A `sum` either stays within one period, or covers one line over 2–4 consecutive
    quarters. The result period is then `6M`/`9M`/`12M` ending at the last quarter.
  - `difference`, `share` and `ratio` need one period. `change` and `pct_change` need
    the same line of the same issuer in two periods.
  - Refused with a reason, never coerced: mixed units, scales, issuers or lines; an
    unknown scale; a dash; a vid not retrieved this session; division by zero.
  - Rates are quantized to 0.01. A result built from an unverified input is marked
    `verified: false` and names that input.
  - The calc vid is a hash of the operation and its inputs, so a repeated computation
    gets the same vid.
  - Values now carry the bridge `sign`.
- **2026-10-24: Agent tools read the store directly, with an as-of date (A-09).**
  `backend/app/agent/tools.py`, `values.py`. Choices:
  - Seven read-only tools: `resolve_issuer`, `list_releases`, `get_bridge`,
    `get_line_history`, `get_quarters`, `get_changes`, `get_normalized`.
  - Every tool takes `as_of` and sees only filings filed by then, so questions asked as
    of a date get what was public then. `app.analytics.history` has no as-of, so the
    tools query observations themselves.
  - There is no `get_peers` tool. Cross-issuer questions call `get_quarters` per issuer,
    then `compute`.
  - Value IDs: `obs:<bridge_id>:<row_order>:<period_id>`, `norm:<cik>:<period>:<policy>`,
    `calc:<hash>` (A-10). A session ledger refuses one vid with two different values.
  - Values that fail a check are returned with `verified: false` and their check
    statuses, never dropped. A line key that occurs twice in one release is left out of
    line histories and quarter series (ambiguous).
  - `get_normalized` must not write. `analytics.normalize.category_for` refreshes label
    memory, so the tool reads recorded categories with a new read-only
    `recorded_category`, and `normalize_issuer` is split so `normalize_quarters` takes
    decided categories. An unrecorded category gives `unavailable` (unclassified_line).
    Normalized figures are offered for the current record only: with an earlier `as_of`
    the tool says so instead of computing a figure that was never public.
  - The boundary test now forbids `app/agent` from importing `ingestion/` or
    `pipeline/`, calling any store write method, or importing `category_for`.
- **2026-10-24: Scoring rules for FootnoteBench-Credit (A-06).**
  `backend/tools/agent_eval/score.py`, `records.py`. Choices the plan left open:
  - Every system is scored from one `SystemAnswer` (status, reason codes, values,
    labels, ranking). Each trial is one JSONL `Trial`. A failed run keeps `answer: null`
    and an `error`, and counts as neither answered nor correct.
  - A value matches when the unit is the same, the period and ticker agree where given,
    and it is within tolerance after scaling. A dollar amount without a scale never
    matches.
  - **Wrong number** means any answer value that matches no key value. Any number on a
    question with no correct number counts as wrong.
  - Answering a false premise while naming `false_premise` as a reason counts as a
    correct refusal.
  - Labels are compared on the normalized line key.
  - Systems give no confidence score, so the risk–coverage "curve" is a single point:
    coverage, and wrong numbers among answered trials.
  - Citation validity counts only single-source values (`computed = false`). The number
    must appear as a whole token ("1,200" is not "200") in the cited document from the
    local cache, or in the cell its XPath points to (`analytics.source.resolve_xpath`). A
    document missing from the cache is invalid.
  - pass^k uses the smallest trial count any question has.
  - `--oracle` scores the keys themselves as a self-check. It is never reported as a
    system result.
- **2026-10-24: Must-refuse questions only where no correct number exists (A-03).**
  `backend/tools/agent_eval/traps.py`. Choices:
  - A C8 question is built only when the public record as of `as_of` holds no correct
    answer:
    - a quarter not yet reported (`as_of` is the day before the next Item 2.02 8-K);
    - an EX-99.1 whose text never mentions EBITDA. Exhibits under 2,000 characters of
      text are excluded: the ACHC exhibit is page images, so absence proves nothing;
    - a ticker that `config/universe.yaml` records as rejected.
  - A scale Footnote could not detect, or a bridge it failed to extract, is not a C8
    question. The number exists in the filing, so a system that reads it correctly must
    not be marked wrong. This drops the PLAN.md SIRI example.
  - `expected.reason_codes` lists every acceptable reason, best first. A press release
    with no EBITDA figure accepts `metric_not_ebitda` or `no_bridge`.
  - C9 premises are refuted with verified values (provenance `tieout`):
    - a YoY move flipped in direction, only when it is at least 5%;
    - a "restatement" of a quarter reported with the same value in *every* release, not
      just the first and last;
    - a headline total stated one unit too large.
  - Covenant-EBITDA and guidance questions need a key written by a person, so they are
    left to A-04.
  - `keys.write` and `keys.to_question` take an author, so each generator replaces only
    its own rows.
- **2026-10-24: Answer keys for C1–C7 are pure arithmetic on verified values (A-02).**
  `backend/tools/agent_eval/keys.py`. Choices:
  - A key value comes from a gold label, or from a store column that passes *both* the sum
    tie-out and the XBRL anchor, with a known scale. "Latest reported" is the newest
    release that reports the period. If that release is not verified for the period, there
    is no key. The generator never falls back to an older release.
  - A quarter is also skipped when a later filing of the issuer, within 400 days, has no
    extracted bridge, since it may have recast the quarter unseen.
  - The keys read the store with their own SQL, not through `app.analytics`. The agent will
    use the analytics, so a bug there is not copied into the keys.
  - Values are compared or summed only under the same headline metric (normalized label).
    The first run found MAT reporting "EBITDA" of 0.1 in May 2025 and "Adjusted EBITDA" of
    57.2 for the same quarter in April 2026: a different measure, not a recast.
  - Judgement calls get no key:
    - C5 skips any release pair with lines both added and dropped, since those may be
      renames.
    - C6 names the reconciling items to remove, instead of applying policy v0.1 to
      rule-suggested categories. Policy-based C6 keys wait for human-confirmed
      categories (`label_memory.source = 'human'`, 0 today).
    - C7 ranks only when adjacent values differ by at least 2%.
  - Selection is round-robin across issuers, in a fixed hash order. The split is by hash
    (about 1 in 4 to dev). IDs derive from the candidate, so a re-run on an unchanged
    store rewrites no file. Rows from other authors in the question files are kept.
  - The question schema now allows a tolerance of 0.05 percentage points on percent and
    ratio values, so an answer rounded to one decimal place passes. Reported and summed
    dollar values must match exactly (tolerance 0).
- **2026-10-24: Track A, an evaluated agent with numbers by reference (ADR-011, A-00).**
  The owner approved [docs/agent/PLAN.md](docs/agent/PLAN.md). Track A runs alongside the
  phases and changes no phase gate. The Phase 0 gate is still open.
  - The agent never writes a number. It cites stored or computed values by ID, and a
    deterministic renderer and provenance gate produce the text the analyst reads. The
    CLAUDE.md rule on served numbers is scoped to say so.
  - The evaluation is built before the agent (A-01 to A-08). The headline metric is the
    wrong-number rate on answered questions. Refusal is a scored answer status.
  - The boundary exceptions (an LLM SDK and model-API network calls in `app/agent/llm.py` and
    `tools/agent_eval/` only) are written in ADR-011. They enter
    `test_architecture_boundaries.py` with the first ticket that needs them, so the
    test stays strict until then.
  - The Track A gate numbers in ADR-011 are proposals the owner may adjust here.
  - The model API is the project's first paid dependency. It is bounded by a per-run budget
    cap and an owner-set monthly limit.
- **2026-10-24: FootnoteBench-Credit question schema (A-01).**
  `backend/tools/agent_eval/questions.py`. Choices beyond PLAN.md:
  - Key provenance adds `store_status` to the planned four values. It covers must-refuse
    keys derived from a recorded store status (a failure reason, an unknown scale, a
    coverage gap), which have no value to verify. It is allowed only on refusals without a
    false premise.
  - `human_checked` requires `checked_by` and `checked_on`.
  - Expected answers have three shapes: values (number, unit, scale, period, tolerance,
    sec.gov sources), labels (as-reported line labels with a change kind), and an ordered
    ticker ranking.
  - A value's tolerance may not exceed 1% of its magnitude, so a key cannot be made loose
    enough to pass anything.
  - Question files are `eval/agent/questions/<split>.jsonl`. A question's split must match
    its file, IDs are unique across files, and covered tickers must match
    `config/universe.yaml`.
- **2026-10-23: Phases 1–4 engineering built ahead of the open Phase 0 gate (ADR-010).**
  The owner directed the agent to "go through all the phases" before an investor meeting.
  The gates are unchanged, and nothing here marks Phase 0 complete or a later phase open.
  Decisions taken in the run:
  - The bridge engine is the P0-05 parser moved into `app/extraction/bridge/`, with
    automatic headline-table selection. Ranking: ties out in every period, then distinct
    periods, then a current-quarter column, then a net-income start, then more lines, then
    the earlier table. `tools.gold.draft` now imports it, so gold drafting and the product
    share one engine.
  - The local SQLite edition of schema v1 is append-only. Each engine version re-extracts
    into new rows; `current_bridges` serves the newest one.
  - The second scorer `tools.eval.score_bridge` and its CI floor `eval/thresholds-bridge.yaml`
    are in-sample. Its caveat (gold values drafted by the same parser) is printed in every
    report.
  - Categories are suggested by deterministic label rules (`app/analytics/classify.py`),
    stored as `source='rule'` and refreshed when the rules change. A human decision always
    wins. No LLM is used. This extends spec §4.5 (label memory or human) with rule
    suggestions that are shown as pending review.
  - Normalized EBITDA is computed under draft policy v0.1 and labelled a preview while the
    spec is unfrozen.
  - Line keys ignore zero-width characters, non-breaking spaces, `[n]` and `(n)` footnotes,
    and hyphens between letters. Definition changes are compared release over release. A
    dropped line and an added line with the same category are reported as *renamed*. When
    fewer than half the lines carry over, one *layout changed* event is reported instead
    of a line diff.
  - When a period repeats in a table, only a column headed Total or Consolidated is kept;
    otherwise none is. Estimate and ratio columns are never stored.
  - The XBRL anchor derives a fiscal Q4 as FY − 9M YTD, as it already derived LTM.
  - Market and competitor desk research is in `docs/research/market.md`. It is not customer
    evidence and does not count toward P0-12.
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
