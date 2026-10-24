# Footnote — Evaluation results

Newest first. Every entry states the date, the commit, the command, the sample size and
the label provenance (`verified_by`). Negative results are kept. Numbers here are
internal: no accuracy figure may be shown to customers or published before second-labeller
agreement is reported (P4-13).

---

## 2026-10-24: earnings-night brief on the local store (A-19)

`python -m app.analytics.brief <TICKER>` for all 50 issuers' latest releases. This is a
smoke run, not a precision result.

- 50 briefs built.
- **Headline:** available for 45. Normalized EBITDA was not computed for 6 of them
  (unclassified line or unknown scale, reason shown). For the other 5 the latest release
  has no current verified quarter.
- **Sections with content:** changes 38, recasts 11, recurring add-backs 29, tie-out
  exceptions 14. Peer comparison is available for 46.
- **Spot check (agent, not a human):** CC's headline reads reported 247, normalized −125,
  the spec §9.1 worked example. TDG reads 1,447 / 1,412, as in the 2026-10-23 entry.
- **Not human-checked.** Claim precision needs a labelled sample (PLAN.md A-19).

---

## 2026-10-24: MCP server on the local store (A-18)

`python -m app.agent.mcp_server --db ../var/footnote.db`, driven over stdio:

- `initialize` negotiated 2025-06-18.
- `tools/list` returned the 8 tools.
- `tools/call get_quarters` (TDG, 4 quarters) returned 1,320 / 1,197 / 1,337 / 1,447, all
  `verified`. The latest matches the TDG figure in the 2026-10-23 entry.

This is a smoke run, not an accuracy result.

---

## 2026-10-24: agent pipeline, scripted end-to-end on real questions (A-12)

The "model" here is a scripted fake client, not Claude. For each of the 30 LTM questions
(C2) in the benchmark, it called `get_quarters` on the local store, then `compute` (sum of
the four quarters), then submitted the calc vid. The loop gated and rendered the answer,
and the A1 system and scorer graded it.

- **30 of 30 correct.** The agent's tools, compute, gate and renderer reproduce the
  independently generated keys (A-02) exactly, with zero wrong numbers.
- This checks that the deterministic chain agrees with the keys. It says nothing about how
  well a model chooses tools or values: that is A-13, which needs the API key and a
  budget.

---

## 2026-10-24: baseline prompt sizes and cost estimate (A-08)

The B0–B2 prompts were built for all 379 questions from the local cache (no model call).
Tokens are estimated at 4 characters per token. Cost assumes Opus 5.5 prices and about 800
output tokens per answer, so it is an estimate, not a measurement.

| System | Mean input tokens | Max | Est. per question | Est. 379 × 3 trials |
|---|---|---|---|---|
| B0 closed book | ~350 | ~400 | $0.017 | ~$20 |
| B1 BM25 top-8 | ~3,450 | ~3,670 | $0.030 | ~$34 |
| B2 long context | ~30,600 | ~40,300 | $0.139 | ~$157 |

- 18 questions have no filing available as of their date, all must-refuse: the 6
  uncovered tickers, and unreported quarters before an issuer's first stored release.
  B1 and B2 are told so.
- Adaptive thinking on Opus 5.5 adds output tokens this estimate does not count. The
  harness's budget cap bounds actual spend.

---

## 2026-10-24: harness dry run with a fake client (A-07)

The harness ran an oracle system (answers taken from the keys) over all **379**
questions, 1 trial, with a scripted fake client. No model was called and nothing was
spent. `--replay` then re-scored the transcripts offline: 379 completed, accuracy 1.0,
wrong-number rate 0.

The recorded cost ($2.274 = 379 × $0.006) is the price table applied to the fake
client's fixture token counts, not spend. This checks the plumbing, not a system.

---

## 2026-10-24: provenance gate on the local store (A-11)

Smoke run, not an accuracy result. For each issuer, the headline total from `get_bridge`
was cited by vid in a test answer, then gated and rendered:

- 43 of 46 passed with the label unquoted. The 3 rejections (AMC, FUN, NWL) are footnote
  markers in the label.
- 46 of 46 passed with the label quoted as required, and rendered with a sec.gov
  source link.
- The same answer with the number typed instead of cited was rejected 46 of 46 times.

---

## 2026-10-24: compute tool on the local store (A-10)

Each issuer's last four quarters from `get_quarters` were summed with `compute` (smoke run,
not an accuracy result):

- **43 LTM sums computed.** 16 of them include at least one unverified input and are
  flagged.
- **3 refused:** quarters not consecutive (2), scale unknown (1).
- **4 issuers** have fewer than four quarters in the store.

---

## 2026-10-24: agent tools on the local store (A-09)

Each tool was called once per issuer (50) with default arguments, on the run-10 store.
This is a smoke run, not an accuracy result.

- **`get_bridge`:** 46 ok, 4 unavailable (no extracted bridge, reason given).
- **`get_quarters`:** 46 ok, 4 not found.
- **`get_changes`:** 45 ok, 5 unavailable.
- **`get_normalized`:** 40 ok, 6 unavailable (unclassified line or unknown scale), 4 not
  found. The 40 computed matches the 2026-10-23 normalization preview.
- **Values:** 2,660 retrieved under stable vids. Of the bridge values, 1,901 are
  verified and 386 are returned with `verified: false`.
- **Store writes:** 0 (`total_changes` unchanged).

---

## 2026-10-24: scorer self-check on the answer keys (A-06)

`cd backend && python -m tools.agent_eval.score --oracle` scores the 379 keys as if they
were a system. This is a check of the scorer and the keys, not a result.

- All 379 grade as correct: wrong-number rate 0, correct refusal 1.0.
- Citation validity: **168 of 168** single-source key values appear as whole numbers in
  their cached sec.gov exhibits. These are the C1, C3 and C9 values and the quarter
  figure in C2 YoY.
- Computed values (LTM sums, percentages, counts) are not citation-checked by design.
- Not human-checked.

---

## 2026-10-24: FootnoteBench-Credit v0, must-refuse and false-premise questions (A-03)

`cd backend && python -m tools.agent_eval.traps --write --written-on 2026-10-24`, same local
store as A-02. These are questions with keys, not results.

**90 questions** (dev 25, test 65). The benchmark now holds **379 questions** (dev 90,
test 289).

| Family | Reason code | Dev | Test | Key provenance |
|---|---|---|---|---|
| C8 quarter not yet reported | `period_not_reported` | 5 | 25 | `store_status` (filings table) |
| C8 press release without EBITDA | `metric_not_ebitda` (or `no_bridge`) | 6 | 8 | `store_status` + exhibit text |
| C8 issuer not covered | `not_covered` | 2 | 4 | `store_status` (universe rejections) |
| C9 false premise (YoY flip, restatement, scale) | `false_premise` | 12 | 28 | `tieout` |

- Press releases without EBITDA: 14 found against a target of 15:
  - AMCX ×8 (reports Adjusted Operating Income);
  - GTN ×2 and OLN ×1 (guidance updates);
  - NCLH, CNK and SBGI ×1 each (a CEO appointment, box-office records, a preliminary
    segment update).

  ACHC's exhibit was excluded because it is page images.
- **Not human-checked.** The C8 keys rest on recorded filing dates and exhibit text. The
  C9 refutations rest on tie-out-verified values.

---

## 2026-10-24: FootnoteBench-Credit v0, first generated questions (A-02)

`cd backend && python -m tools.agent_eval.keys --write --written-on 2026-10-24`, on the local
store from run 10 (engine `bridge-6`, 2026-10-23), at commit `43243c9` plus the A-02 change.
These are questions with answer keys, not results: no system has been run on them yet.

**289 questions** in `eval/agent/questions/` (dev 65, test 224). The test split is not frozen
yet (A-05).

| Category | Dev | Test | Key provenance |
|---|---|---|---|
| C1 point lookup | 13 | 27 | 20 `gold_model_agreement`, 20 `tieout` |
| C2 multi-period (LTM, YoY) | 18 | 42 | `tieout` |
| C3 point in time (16 recasts, 13 unchanged controls) | 3 | 26 | `tieout` |
| C4 add-back composition | 8 | 32 | `tieout` |
| C5 definition change | 10 | 30 | `tieout` |
| C6 removal of named items | 4 | 36 | `tieout` |
| C7 cross-issuer ranking | 9 | 31 | `tieout` |

- C3 has 29 questions against a target of 40: only 16 restatements met every guard. The
  split by hash leaves C3 and C6 with few dev questions. A-05 should balance them.
- Skips, each counted by reason:
  - 149 release pairs with lines both added and dropped (possible renames, C5);
  - 89 quarters whose latest release is not verified for the period;
  - 75 quarters with a later filing that has no extracted bridge;
  - 61 restatement candidates where the metric or line changed (C3);
  - 60 release pairs where one release has no bridge (C5);
  - 30 restatement pairs not verified at both ends;
  - 18 layout changes (C5);
  - 12 YoY comparisons with a base that is not positive;
  - 11 issuers whose latest quarter is not verified (C7);
  - 6 YoY comparisons across different metrics;
  - 5 release pairs with a failing sum tie-out (C5).
- **Check against the source (agent, not a human).** Every C1 and C3 value (98) was searched
  for in the text of its cached sec.gov exhibit. All 98 are present. One appears as
  "(58.0)" where the key reads −58 (AMC), the same number.
- **Caveat.** `tieout` keys come from the store the agent will read, so they test retrieval
  and reasoning, not extraction (ADR-011). No key has been checked by a person yet. That is
  A-04: the owner checks 60 sampled test keys against sec.gov.

---

## 2026-10-23: bridge engine (bridge-6) on the gold set and on 388 held-out releases

Agent run under the owner directive of 2026-10-23 (ADR-010). **The Phase 0 gate is still
open**: rows 4 and 5 of the gate table below are unchanged. These numbers are internal (P4-13).

### A. Gold set (in-sample regression check)

`cd backend && python -m tools.eval.score_bridge --json ../eval/results/bridge-2026-10-23.json`

- Engine: `app.extraction.bridge.engine.extract_headline_bridge`. It reads the whole document
  and selects the table itself; no gold table index or metric label is passed in.
- 30 releases, 1,202 scored values (`model_agreement` 1,197, `human` 5, `tieout` 0).
- table_found **100.0%** (30/30 releases; the P0-09 extractor: 20/30). line_exact_match, role,
  sign and scale accuracy are all **100.0%** (1,202/1,202).
- **Caveat.** The gold values were drafted by the same row and period parsing (P0-05, on the
  owner-chosen table) and then confirmed by an independent model reading or the owner. So
  these figures show the engine reproduces verified labels *with automatic table
  selection*. They are not an independent estimate of parsing accuracy. Gated in CI by
  `eval/thresholds-bridge.yaml` (P2-14).

### B. Held-out releases (independent, arithmetic verification)

`python -m app.pipeline.cli ingest --quarters 8` (run 10, engine `bridge-6`, 2026-10-23).

- Universe: `config/universe.yaml`, 50 issuers with CIKs resolved from EDGAR. Every Item 2.02
  8-K from 2024-09-30 to 2026-10-22: 421 releases, 418 with an HTML EX-99.1. **388 of them
  are not in the gold set**, and their results come from code never tuned on them, except
  through the error analysis listed in section C.
- Verification is arithmetic, not labels. The **sum tie-out** checks that the start plus
  the adjustments equals the stated total within max(1, ⌈n/2⌉) units. The **GAAP anchor**
  checks that the start equals the XBRL companyfacts value for the same period.

| | Held-out (388) | Gold (30) | All (418) |
|---|---|---|---|
| Releases with a headline bridge found | 344 (88.7%) | 30 | 374 (89.5%) |
| …that tie out in **every** period | **338 / 344 (98.3%)** | 30 / 30 | 368 / 374 (98.4%) |
| Period-level sum tie-outs passed | 1,191 / 1,209 (98.5%) | 100 / 100 | 1,291 / 1,309 |
| GAAP anchor: match / mismatch / no XBRL fact | 1,033 / 79 / 71 | 95 / 1 / 4 | 1,128 / 80 / 75 |

Anchor matches where XBRL has a comparable fact: **1,128 / 1,208 (93.4%)**. The 80
mismatches are concentrated: SPB 28, CNK 16, CC 8, MAT 6, and 4 or fewer elsewhere. CC's line up with its recasts: CC
re-reported earlier periods with different values (for example, Q2 2024 net income was 70
in its Nov 2024 release and 60 in its Aug 2025 release), and the XBRL facts carry the
later values. The
others are **not yet investigated**. A mismatch never changes a stored value; it is shown
as an exception on the release.

**Not found (44 releases), each with a recorded reason.** By reason: no EBITDA total with
a GAAP start above it (25), only estimate or repeated-period columns (11), and no tables
at all, meaning image or PDF-only exhibits (8). By issuer:
- USFD 11: amount and margin columns are interleaved;
- BYD 9: the bridge runs in reverse, from EBITDA down to net income;
- AMCX 8: the metric is "Adjusted Operating Income", not EBITDA;
- CLF 3, GTN 2, OLN 2, and 1 each for THC, RXT, PENN, NCLH, CNK, SBGI, CCO, ACHC and COTY.

The 3 releases without an HTML EX-99.1 are recorded as index failures.

**Human check.** Not done. CLAUDE.md requires a person to check output against sec.gov
before a feature counts as done. This agent spot-checked rendered bridges (CC, MGM) against
their own arithmetic only.

### C. Error analysis that changed the engine (P2-10, P2-11..13)

| Class (held-out) | Fix | Engine |
|---|---|---|
| Segment breakdown repeats the total under the bridge (RRR, CHDN) | try every EBITDA row as the total | bridge-2 |
| Per-unit and same-facility totals picked (RCL "per APCD", ACHC) | excluded as totals | bridge-2 |
| Start "income from continuing operations" not recognized (CCO) | added to GAAP starts | bridge-2 |
| Estimate ranges ("Low/High (Estimated)") stored as actuals (RXT) | columns not stored | bridge-2 |
| "Total adjustments" spanning headed blocks read as an adjustment (CHDN) | cross-heading subtotal | bridge-3 |
| Margin rows inside the bridge (COTY) | memo, not summed | bridge-3 |
| "Net Earnings" start (POST), "Adjusted OIBDA" (OUT), "$ (268.6)" (CLVT) | recognized | bridge-3 |
| Segment-per-column tables (OUT) | ranked below consolidated | bridge-3 |
| "% of sales" columns beside amounts (AVTR) | ratio columns not stored | bridge-4 |
| Zero-width characters and `[2]` footnotes splitting line keys (AMC, NWL) | ignored in keys | bridge-4 |
| Fiscal Q4 has no 3-month XBRL fact | FY − 9M YTD | bridge-3 |
| "(Millions of U.S. dollars)" caption (TROX) | recognized | bridge-5 |
| **Negative result, found and fixed:** SIRI's scale was read from a nearby KPI caption ("listener hours (in billions)"), so two SIRI bridges stored values 1,000× too large (in bridge-5 and the first published demo) | a caption next to a non-money unit is never a table's scale; SIRI is now `scale unknown` (not computed) rather than wrong; regression test added | bridge-6 |

### D. Normalization preview (draft policy v0.1, rule-suggested categories)

- Latest quarter computed for 40 of 46 issuers with a verified quarter. The rest are blocked
  by an unclassified line (5) or an unknown scale (1). 992 label-memory entries, all
  `source=rule`, pending human review.
- **The deterministic code reproduces the spec's hand-worked examples.** CC Q2 2026: 247
  becomes **−125** (spec §9.1). WYNN Q2 2026: 568,309 becomes **498,805** (§9.3). In §9.2
  (TDG) recurrence was *unknown* with two quarters. With eight quarters of history, `MA`
  is now recurring, so normalized is 1,447 − 35 = 1,412: the history resolved it, as §9.2
  predicted.
- Change feed: 205 recasts, 50 recurring "non-recurring" add-backs, 142 add-backs added,
  163 dropped, 336 renamed lines, 7 renamed metrics, 20 layout changes.

---

## Phase 0 exit gate: status as of 2026-10-17

**Phase 0 is not complete, and Phase 1 stays closed.** Three of five criteria are met. The
two that are open are the owner's (P0-12, P0-14). The engineering evidence below sits on the
stacked branches `p0-08-scorer` … `p0-gate-status` and counts once those PRs are merged to
`main`.

| # | Exit criterion (ROADMAP §7) | Status | Evidence |
|---|---|---|---|
| 1 | 30-release gold set complete under the lean, tie-out-first procedure | **Met** | See the three sub-checks below |
| 1a | Owner confirmed table selection for all 30 releases | Met | `eval/gold/review_decisions.yaml`: 30 entries under `tables_confirmed`, reviewer Niraj Jadhav, 2026-10-17. `labels --validate --strict` fails on any unconfirmed table, and it passes: "30 label files checked, 0 problems" |
| 1b | Every exception resolved | Met | 7 resolutions in `review_decisions.yaml`; `review_queue.md` says "0 item(s) still open". Promotion refuses to write labels while any queue item is unresolved (DECISIONS 2026-10-17, P0-06) |
| 1c | Every label carries `verified_by` | Met | It is a required field of the schema (`tools/gold/labels.py`). 1,304 values: 1,297 `model_agreement`, 7 `human`. Exhibits are unchanged: `fetch_releases --verify` gives "30 releases checked, 0 problems" |
| 2 | Scorer in CI, reporting accuracy split by `verified_by` | **Met on merge** | `backend/tools/eval/score.py` (P0-08). CI step "Extractor scorer must not regress below the baseline (P0-10)" runs it with `--check eval/thresholds.yaml`. Every metric is printed overall and per `verified_by` |
| 3 | Baseline published | **Met on merge** | The P0-09 entry below, plus `eval/results/baseline-2026-10-17.json` |
| 4 | ICP pass rule met (§2) | **Not met. Owner: P0-12** | `docs/discovery/tracker.md` reads OPEN: 0 of 8 interviews |
| 5 | Normalization spec v0.1 reviewed by ≥2 analysts | **Not met. Owner: P0-14** | `docs/NORMALIZATION.md` v0.1 is drafted; 0 feedback forms received |

### What the owner must do to close the gate

**A. Review the spec draft (P0-13 acceptance), before sending it out.**
1. Read `docs/NORMALIZATION.md` v0.1. Correct anything you disagree with, especially:
   - the default treatments (§5);
   - the category illustrations in §4 and §9.
2. Closing artefact: your go-ahead in the P0-13 PR, or a commit with your edits.

**B. ICP interviews (P0-12).** Kit: `docs/discovery/`.
1. Recruit with `recruiting.md`. Send the outreach messages yourself; plan on 40–60 messages.
2. Run each call with `interview-script.md` (40 min).
3. Within 24 h, fill in `interviews/I-NN-notes.md` and `interviews/I-NN-scoresheet.md` from
   the templates. Score with `scoring-rubric.md`: every "yes" needs a quote.
4. Update the tally in `tracker.md` after each interview. Stop at 8, or earlier if rubric §4
   gives an early PASS (5 A, at least 3 B, 0 C after 5 interviews) or an early FAIL.
5. **Closing artefact:**
   - 8 scoresheets (or 5+ with an early decision);
   - `tracker.md` showing **PASS**;
   - a DECISIONS.md entry;
   - this table updated.
6. If the result is **FAIL**: switch to the fallback persona (equity earnings-quality /
   forensic analysts), log the switch in DECISIONS, and re-interview 5 with the same kit.

**C. Spec review (P0-14).**
1. Send `docs/discovery/spec-review-brief.md`, the spec and `templates/spec-feedback.md` to
   at least 2 interviewees who said yes to script question T4.
2. File each reply as `docs/discovery/spec-feedback/R-NN.md`, linked to its interview ID.
3. **Closing artefact:** 2 or more completed forms. Engineering then revises the spec to
   v0.2 and fills in the disposition table on each form. v0.2 must be frozen before
   **Phase 2** (not Phase 1).

**D. Human check of the scorer output (needed to call P0-08/P0-09 done, per CLAUDE.md).**
This is not a gate row.
1. Open `eval/results/baseline-2026-10-17.json` and pick one example per failure class
   (wrong table, period ambiguous, period missing, label not found, value mismatch, sign
   direction wrong) and one exact match.
2. Confirm each one against the release on sec.gov.
3. Closing artefact: a one-line note per example under the P0-09 entry, or in its PR.

Phase 1 opens only when rows 4 and 5 read **Met** with their artefacts committed.

---

## 2026-10-17 — P0-09 baseline: `HtmlExtractor` on `main`

**What was run.** `cd backend && python -m tools.eval.score --json ../eval/results/baseline-2026-10-17.json`
(scorer v1, P0-08). Full report: [results/baseline-2026-10-17.json](results/baseline-2026-10-17.json).

- **Code.** Scorer at commit `3406fcc` (branch `p0-08-scorer`). `backend/app/` there is identical to
  `main` at `1f41440`, so this is the extractor as merged after P0-06. No extractor
  change was made for this ticket.
- **How the extractor is called.** It runs with its default `target_metric="Adjusted EBITDA"`.
  The gold metric label is not passed in. The table is the extractor's top-ranked candidate.
- **Gold set.**
  - 30 releases (15 issuers × 2 quarters) with 1,304 values.
  - 102 dash placeholders are not scored, which leaves **1,202 scored values**.
  - Provenance: `model_agreement` 1,297 (1,197 scored), `human` 7 (5 scored), `tieout` 0.
  - Label files sha256 `5d0953b0cb034279eb3ae634b1925bcb274cb7cc2ef722f3c180cedbbf073d20`,
    over LF-normalized files. The first recording (`944a60be…`, at `8df6cc1`) hashed
    a Windows CRLF checkout and did not match CI. The metrics are identical.
- **Determinism.** A second run gave a byte-identical JSON.
- **Unit.** One gold value (line × period). Metric definitions are in
  [DECISIONS.md](../DECISIONS.md) (2026-10-17, P0-08) and the scorer's docstring.

### Metrics

| Metric | Overall | `tieout` | `model_agreement` | `human` |
|---|---|---|---|---|
| **table_found** | **60.7%** (729/1202) | n/a (n=0) | 60.7% (727/1197) | 40.0% (2/5) |
| **line_exact_match** | **15.5%** (186/1202) | n/a (n=0) | 15.5% (186/1197) | 0.0% (0/5) |
| **scale_accuracy** | **0.0%** (0/1202) | n/a (n=0) | 0.0% (0/1197) | 0.0% (0/5) |
| **sign_accuracy** | **49.4%** (594/1202) | n/a (n=0) | 49.5% (592/1197) | 40.0% (2/5) |
| line_label_value_match (diagnostic, period ignored) | 54.2% (651/1202) | n/a (n=0) | 54.2% (649/1197) | 40.0% (2/5) |

Per release:
- table found in **20/30**;
- scale right in **0/30**.

The `human` column has only 5 scored values, so it says almost nothing on its own. It is shown
because the split is required, not because it is informative.

Reading the numbers:
- Exact matches are concentrated in releases with one 3-month column per year. There the
  year alone identifies the period. 7 releases match every scored value: THC, CAR, CZR, RXT
  and FUN Q1, and both CVNA releases. CYH Q1 matches 12/16.
- Releases with several periods ending in the same year (3M with 6M, 9M or LTM) score 0.
  The one exception is FUN Q2 at 16/94: its only distinct column, the 12M ended
  December 31, 2025, carries a full date.

### Failure classes (line exact match; values, releases)

1. **Wrong table: 473 values, 10 releases.** LUMN, WYNN, CC, IHRT and HTZ, both quarters
   each.
   - The keyword detector ranks another reconciliation table first.
   - In every case the gold table is still among the candidates, ranked 2nd to 8th.
   - Examples:
     - IHRT `0001628280-26-033471`: gold table 9 is ranked 2nd, behind table 8.
     - CC `0001627223-26-000010`: gold table 11 is ranked 8th of 9.
     - WYNN `0001174922-26-000051`: gold table 6 is ranked 5th; table 2 is ranked first.
2. **Period ambiguous: 355 values, 8 releases.** THC Q2, CAR Q2, CHTR Q1 and Q2, CZR Q2,
   CYH Q2, RXT Q2 and FUN Q2.
   - The header is split over two rows, e.g. "Three Months Ended June 30," above
     "2026 | 2025". The extractor keeps only the year as the period.
   - A year alone cannot tell 3M from 6M or LTM.
   - Example: THC `0000070318-26-000032`, line 0, `3M-2026-06-30` = 826. The period string
     is `'2026'`, which matches both 3M and 6M.
3. **Period missing: 110 values, 4 releases.** TDG and BHC, both quarters.
   - The parser looks for period headers only in the first four rows.
   - In these tables those rows hold the table title (TDG: "TRANSDIGM GROUP INCORPORATED /
     SUPPLEMENTAL INFORMATION …"; BHC: "Reconciliation of GAAP Net Loss to Adjusted
     EBITDA …"). The value columns therefore get no period.
   - Example: BHC `0000885590-26-000051`, line 0 'Net loss', `3M-2026-03-31` = (1,431).
4. **Label not found: 76 values, 4 releases.**
   - BHC (both quarters): adjustment labels are indented into later columns, and
     `row_headers` reads only columns 0–1. This is a known gap in
     [ARCHITECTURE.md](../ARCHITECTURE.md). Example: 'Interest expense, net' = 392.
   - CYH (both quarters): labels wrap over two rows, so the extractor keeps only a fragment.
     Example: 'Net loss attributable to Community Health Systems, Inc. stockholders' becomes
     'Systems, Inc. stockholders'.
5. **Value mismatch: 2 values, 1 release.** CYH `0001193125-26-312454`, line 5 'Loss (gain)
   from early extinguishment of debt' = (138). The opening and closing parentheses sit in
   separate cells, so the extractor emits nothing for that column. The row yields only 5
   and 12.

**Scale: 1,202 values, 30 releases, all `scale_not_detected`.**
- For every gold table the extractor's title is the `Table N` fallback, so
  `detect_scale_from_caption` has no unit text to read.
- The real captions (e.g. TDG "(Amounts in millions, except per share amounts)") sit in
  rows or text the title logic does not capture.
- Caption scale is not passed into `scale_and_sign`, a known gap (P2-02).

**Sign: 551 not located (as above) + 57 direction wrong, 3 releases.**
- These are top-down bridges: THC (both quarters) and FUN Q2. Items are shown with
  income-statement signs, so `detect_sign` reads `(204)` as a deduction where the bridge
  adds it back.
- Example: THC `0000070318-26-000023`, line 1 'Net income available to noncontrolling
  interests' = (204). Read as −1; the gold contribution is +1.

**Not measured by this scorer.** It measures recall against the gold lines, not precision.
The extractor also emits records that are not bridge values. For example, in CZR
`0001590895-26-000015` the header years "2026" and "2025" come out as values of a row
labelled "(In millions)". A precision metric is a candidate for Phase 2 (P2-10).

**Not covered by this baseline.**
- The gold drafts (P0-05) read cell text through the same `extract_html_tables`, so a
  cell-text error shared by both sides would not show up here. Tie-outs and the
  independent reading (P0-05b) limit this risk but do not remove it.
- No second-labeller agreement exists yet (P4-13).
