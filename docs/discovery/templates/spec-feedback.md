# Spec feedback: R-NN on NORMALIZATION.md v0.1

Copy to `docs/discovery/spec-feedback/R-NN.md`. Either the reviewer fills it in, or the owner
transcribes a call. Write the reviewer's words in quotes and the owner's paraphrase without
quotes. P0-14 closes when at least 2 completed forms exist from interviewed analysts.

| Field | Value |
|---|---|
| Reviewer ID | R-NN |
| Interview ID (must exist) | I-NN |
| Role / firm type (no names) | |
| Spec version reviewed | v0.1 (2026-10-17) |
| Date received | YYYY-MM-DD |
| Format | form / marked-up PDF / call (transcribed by owner) |
| Permission to quote (anonymized)? | yes / no |

## A. The five main questions

| # | Question | Answer | Would change (what, specifically) |
|---|---|---|---|
| 1 | Recurring "non-recurring" items: reverse a category at ≥3 of the last 4 quarters? (§6, Ex. 9.1) | agree / agree with changes / disagree | |
| 2 | SBC default for credit | accept / reverse / flag | |
| 3 | Categories (§4): missing, wrongly merged, needlessly split, or example lines mapped wrongly? | | |
| 4 | Default output: consolidated or attributable? EBITDA or EBITDAR? (Ex. 9.3, 9.6) | | |
| 5 | Is a published default policy useful, or only your own firm's policy? | useful / only own policy / both | |

## B. Treatment per category (§5)

Mark only the rows you would change.

| Code | Draft default | Your default | Why |
|---|---|---|---|
| `NCI` | accept | | |
| `NONOP` | accept | | |
| `SBC` | flag | | |
| `RESTR` / `TRANSFORM` / `MA` / `LITIG` / `ENV` | accept-unless-recurring | | |
| `IMPAIR` / `DIVEST` / `DEBT` / `FX` / `DERIV` | accept | | |
| `PREOPEN` | flag | | |
| `REV` | flag | | |
| `SYNERGY` | exclude | | |
| `RENT` / `CORP` | exclude | | |
| `OTHER_NR` | flag | | |
| `MIXED` | strictest constituent | | |

## C. Other open questions (§12)

| # | Topic | Answer |
|---|---|---|
| 3 | Recurrence window (3 of 4? 4 of 8 for seasonal businesses?) | |
| 4 | Synergies and covenant EBITDA | |
| 7 | Restructuring vs. transformation as separate codes | |
| 8 | Derive missing quarters from LTM or YTD? | |
| 10 | Revenue-side adjustments: flag or reverse? | |
| 12 | After v0.1, what next: segments, 10-Q/10-K bridges, covenant EBITDA? | |

## D. Anything else

- What would stop you from using a normalized number from Footnote?
- What would you need to see next to the number to trust it?
- Free comments, by section if possible:

## E. Owner's disposition (filled in when revising to v0.2)

| Comment | Accepted / rejected / deferred | Change made, or reason |
|---|---|---|
| | | |
