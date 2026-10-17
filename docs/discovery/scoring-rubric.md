# Scoring rubric and ICP pass rule (P0-11 / P0-12)

Score each interview within 24 hours, from the notes, on a copy of
[templates/scoresheet.md](templates/scoresheet.md). Every **yes** needs a supporting quote or
a concrete fact from the notes. A score without evidence counts as **no evidence**.

## 1. The ICP pass rule (ROADMAP §2)

Phase 1 opens only if, **among the first 8 qualifying interviewees** (screened per
[recruiting.md](recruiting.md) §1):
1. **At least 5** meet criterion **A**; **and**
2. **at least 3** meet criterion **B**; **and**
3. **fewer than half (at most 3 of 8)** meet criterion **C**.

If the rule fails, switch to the fallback persona (equity earnings-quality / forensic
analysts) and re-interview 5 with the same kit.

*Reading of "at least 3".* ROADMAP §2 can be read as 3 of the 8, or as 3 of the 5 who meet
A. The tracker computes both. If they disagree, the stricter reading (B among those who
meet A) decides, unless you record otherwise in DECISIONS.md.

## 2. The three criteria

Each criterion is scored **yes**, **no** or **unclear**. *Unclear* is resolved
conservatively: it counts as **no** for A and B, and as **yes** for C.

### A. Rebuilds or adjusts EBITDA bridges manually, at least quarterly
Sources: W1–W4.

| Score | Evidence that qualifies |
|---|---|
| yes | Describes doing it themselves (or their team, as part of their own job) for one or more issuers **every quarter** or more often. Examples: "every quarter I re-key the bridge into our model and strip out X"; "we adjust every add-back against the credit agreement each quarter". |
| no | Uses the issuer's or a vendor's number as-is; does it only at underwriting or once a year; or someone else does it and they never touch it. |
| unclear | Says they "look at" add-backs without describing changing or rebuilding anything, or the frequency is unknown. |

### B. Names a price anchor or asks for a trial
Sources: B2, B4, E3.

| Score | Evidence that qualifies |
|---|---|
| yes | Gives a number or range they would expect to pay or have budget for (per seat, team or year), or a concrete comparison ("about what we pay for X"); **or** asks for a trial or early access without prompting; **or** answers B4 with a clear yes plus a next step (names issuers, agrees to a date). |
| no | "Interesting" or "send me something" with no number and no commitment; declines a trial. |
| unclear | Gives a number for a *different* product with no link to this one, or a vague "depends". |

A price anchor is only evidence. A low number still counts as an anchor; record it exactly,
it informs pricing.

### C. Says an existing tool already covers normalization **plus** change tracking
Source: E2 (and E1 if volunteered).

| Score | Evidence that qualifies |
|---|---|
| yes | Names a tool or service they use that, in their words, gives them normalized (policy-adjusted) EBITDA **and** flags definition changes or restatements, so they would not need this. |
| no | Their tools give one part at most (e.g. as-reported data, or covenant analysis without quarterly change tracking), or they say nothing covers it. |
| unclear | Thinks a tool might do it but has not used that feature. |

Record which tool they named: this is competitive evidence, whatever the score.

## 3. Context scores (0–3, not part of the rule)

These do not change the pass or fail result. They help choose design partners and P0-14
reviewers.

| Dimension | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| **Pain** (P1–P4) | none named | mild annoyance | costs hours each quarter | caused a real error or loss they describe |
| **Time per issuer-quarter** (P1) | not done | < 15 min | 15–60 min | > 1 h |
| **Trust bar** (T1–T3) | would never use a third party's normalized number | needs full itemization and an override | needs itemization | would use it as-is |
| **Buying power** (B3) | no influence | can recommend | influences the budget | decides or holds the budget |
| **Spec reviewer** (T4) | declined | maybe | yes | yes, and has a written firm policy to compare |

## 4. When to declare the result

Let *n* be the number of scored interviews among the first 8 (n ≤ 8), and *r = 8 − n*.
- **Early PASS** once the rule can no longer fail: A ≥ 5, B ≥ 3, and C + r ≤ 3.
- **Early FAIL** once it can no longer pass: A + r < 5, or B + r < 3, or C ≥ 4.
- Otherwise keep interviewing until 8.

ROADMAP P0-12 allows Phase 1 to open after 5 interviews only if an early PASS holds.

## 5. Calibration

After the first 2 interviews, re-read both scoresheets against this rubric. If a
definition was hard to apply, write down how you decided. A note in [tracker.md](tracker.md)
under *Rubric notes* is enough. Then apply the same reading to every later interview. Do
not change a definition after you have seen a result you dislike.
