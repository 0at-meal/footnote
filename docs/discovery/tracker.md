# Interview tracker (P0-12)

Owner-maintained. Pseudonymous IDs only. Keep names and contact details outside the
repository. Rules: [scoring-rubric.md](scoring-rubric.md).

## Pipeline

One row per person contacted. Status: `contacted` → `replied` → `booked` → `done` →
`scored`, or `declined`, `no-reply` or `not-ICP`.

| ID | Channel | Role / firm type | Contacted | Status | Interview date | Spec reviewer? (T4) |
|---|---|---|---|---|---|---|
| | | | | | | |

## Scored interviews (first 8 qualifying)

Fill in from each `interviews/I-NN-scoresheet.md`. *Unclear* counts as **no** for A and B
and as **yes** for C.

| # | ID | Date | A (rebuilds ≥ quarterly) | B (price anchor / trial) | C (existing tool covers it) | Price anchor (as said) | Tool named for C |
|---|---|---|---|---|---|---|---|
| 1 | | | | | | | |
| 2 | | | | | | | |
| 3 | | | | | | | |
| 4 | | | | | | | |
| 5 | | | | | | | |
| 6 | | | | | | | |
| 7 | | | | | | | |
| 8 | | | | | | | |

## Tally

| Item | Count | Needed |
|---|---|---|
| Scored interviews *n* | 0 | 8 (or an early decision) |
| Remaining *r* = 8 − *n* | 8 | |
| A = yes | 0 | ≥ 5 |
| B = yes (of all scored) | 0 | ≥ 3 |
| B = yes among those with A = yes (stricter reading) | 0 | ≥ 3 |
| C = yes (incl. unclear) | 0 | ≤ 3 |

**Result:** OPEN. Use one of OPEN, early PASS, early FAIL, PASS or FAIL. For early
decisions, see rubric §4.

- Early PASS: A ≥ 5 and B ≥ 3 and C + r ≤ 3.
- Early FAIL: A + r < 5 or B + r < 3 or C ≥ 4.

When the result is PASS or FAIL, record it with the date in
[eval/RESULTS.md](../../eval/RESULTS.md) (Phase 0 gate section) and in
[DECISIONS.md](../../DECISIONS.md).

## Rubric notes (calibration)

<!-- After interviews 1–2: how you applied any definition that was hard to call. -->
