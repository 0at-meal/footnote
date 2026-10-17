# Footnote — Evaluation results

Newest first. Every entry states the date, the commit, the command, the sample size and
the label provenance (`verified_by`). Negative results are kept. Numbers here are
internal: no accuracy figure may be shown to customers or published before second-labeller
agreement is reported (P4-13).

---

## 2026-10-17 — P0-09 baseline: `HtmlExtractor` on `main`

**What was run.** `cd backend && python -m tools.eval.score --json ../eval/results/baseline-2026-10-17.json`
(scorer v1, P0-08). Full report: [results/baseline-2026-10-17.json](results/baseline-2026-10-17.json).

- **Code.** Scorer at commit `8df6cc1` (branch `p0-08-scorer`). `backend/app/` there is identical to
  `main` at `1f41440`, so this is the extractor as merged after P0-06. No extractor
  change was made for this ticket.
- **How the extractor is called.** It runs with its default `target_metric="Adjusted EBITDA"`.
  The gold metric label is not passed in. The table is the extractor's top-ranked candidate.
- **Gold set.**
  - 30 releases (15 issuers × 2 quarters) with 1,304 values.
  - 102 dash placeholders are not scored, which leaves **1,202 scored values**.
  - Provenance: `model_agreement` 1,297 (1,197 scored), `human` 7 (5 scored), `tieout` 0.
  - Label files sha256 `944a60bea101e9ed428ff9774842d7431f74091634ce4055b2824cdfe34a21ee`.
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
