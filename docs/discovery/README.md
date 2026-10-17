# Discovery: ICP validation and spec review (Phase 0)

This folder holds the owner's customer-discovery work for Phase 0:
- **P0-12:** 8 interviews with credit / leveraged-finance analysts, scored against the
  ICP pass rule ([ROADMAP §2](../ROADMAP.md));
- **P0-14:** at least 2 of those analysts critique
  [NORMALIZATION.md](../NORMALIZATION.md) v0.1.

The engineering side (P0-11, P0-13) only provides the kit. The interviews, scores and
feedback are the owner's evidence, and nothing here may be filled in on the owner's behalf.

## Files

| File | Use |
|---|---|
| [recruiting.md](recruiting.md) | Who qualifies, where to find them, and the outreach message you send yourself |
| [interview-script.md](interview-script.md) | The 40-minute script (workflow, pain, trust in normalization, tools, price, buying process) |
| [scoring-rubric.md](scoring-rubric.md) | How to score an interview: the three pass-rule criteria plus context scores |
| [templates/scoresheet.md](templates/scoresheet.md) | Fill in one copy per interview, within 24 h |
| [templates/notes.md](templates/notes.md) | Running notes during the call |
| [tracker.md](tracker.md) | Status of every candidate and interview, and the pass-rule tally |

Filled-in copies go in `interviews/I-NN-scoresheet.md`, `interviews/I-NN-notes.md` and
`spec-feedback/R-NN.md`.

## Privacy

Use pseudonymous IDs (`I-01` … `I-08`) in this repository. Keep names, firms and contact
details in your own contact list, outside git. Notes record the role and firm *type* (e.g.
"direct lender, ~$5bn AUM"), not the firm. Ask for permission before taking notes, and
before quoting anyone outside the team.

## How Phase 0 closes on this side

- **ICP pass rule (P0-12).**
  - Closed by 8 filled scoresheets in `interviews/` and a [tracker.md](tracker.md) tally
    reading **PASS**.
  - The rule may be declared early once 5+ interviews make the outcome certain (see
    [scoring-rubric.md](scoring-rubric.md) §4).
  - If it reads **FAIL**, the fallback persona applies: equity earnings-quality / forensic
    analysts. Re-interview 5 of them with the same kit, then record the switch in
    [DECISIONS.md](../../DECISIONS.md).
- **Spec review (P0-14).**
  - Closed by at least 2 filled `spec-feedback/R-NN.md` forms from analysts you
    interviewed.
  - Engineering then revises the spec to v0.2 and answers every comment.
