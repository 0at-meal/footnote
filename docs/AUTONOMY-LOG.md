# Autonomy log

One entry per item touched by an unattended agent run. Desk research here is never customer
evidence. Nothing in this file is an interview answer, reviewer feedback or a human check.

---

## 2026-10-21 — run 1 (Claude Code, owner away)

**Starting state.** Current phase 0. All Phase 0 engineering tickets exist on the stacked,
unmerged branches `p0-08-scorer` → `p0-09-baseline` → `p0-10-ci-gate` → `p0-11-interview-kit`
→ `p0-13-normalization-spec` → `p0-15-adrs` → `p0-gate-status` (tip `2050bf1`). Earlier
tickets (P0-01, P0-03–P0-06) are merged to `main` (`1f41440`).

**Verification of the stack (no code changed).** On `p0-gate-status`, in a fresh venv built
from `requirements-dev.txt`: `ruff check backend` clean, `ruff format --check backend` clean,
`mypy` "no issues found in 37 source files", `pytest` 127 passed,
`python -m tools.eval.score --check ../eval/thresholds.yaml` → "gate: pass".
Note: the owner's global Python env fails `mypy` with 15 `import-untyped` errors because it
has beautifulsoup4 4.12.3 (pinned: 4.15.0) and no `types-PyYAML`. This is an environment
drift, not a repo defect. Fix: `python -m pip install -r requirements-dev.txt`.

| Ticket | Type | What happened | Owner must do next |
|---|---|---|---|
| P0-08 scorer | blocked-needs-human | Built earlier (`8df6cc1`, `3406fcc`); re-verified green. Not "done" per CLAUDE.md until a human checks output on real filings | RESULTS.md gate step D: confirm one example per failure class + one exact match in `eval/results/baseline-2026-10-17.json` against sec.gov |
| P0-09 baseline | blocked-needs-human | Same as P0-08 (`d2238ea`, `86a9f84`) | Same as above |
| P0-10 CI gate | done (pending merge) | Re-ran the threshold gate: pass | Review and merge the stacked PRs in order |
| P0-11 interview kit | done (pending merge) | No change | Merge |
| P0-12 interviews | blocked-needs-human | Not touched. Manual-only; `docs/discovery/tracker.md` shows 0 of 8 | Recruit and run interviews with `docs/discovery/`; fill scoresheets yourself |
| P0-13 spec v0.1 | blocked-needs-human | Not touched. Draft exists; owner acceptance outstanding | Read `docs/NORMALIZATION.md`, edit or approve in the P0-13 PR |
| P0-14 spec critique | blocked-needs-human | Not touched. Manual-only; no `spec-feedback/` forms | Send the brief to ≥2 interviewees who said yes to T4; file replies as `spec-feedback/R-NN.md` |
| P0-15 ADRs | done (pending merge) | No change | Merge |
| P0-07 second labeller | skipped | Deferred to Phase 4 (P4-13) by the roadmap | — |

**Decisions made without the owner.**
- Did not open any Phase 1 ticket: gate rows 4 and 5 in `eval/RESULTS.md` are "Not met".
- Did not install packages into the owner's global Python; verified in a throwaway venv instead.

**Sources.** None; no web research was needed.

**Stop reason.** Every remaining Phase 0 item is manual-only (P0-12, P0-13 acceptance,
P0-14, human check of P0-08/09), and Phase 1 is behind the unmet gate.

---

## 2026-10-23 — run 2 (Claude Code, owner directive: "go through all the phases")

**Directive.** The owner asked for the whole platform before an investor meeting the next
day, with every human step done by the agent. The parts an agent may not or cannot do
honestly are listed under "Owner must do next". They were not simulated.

| Item | Type | What happened | Owner must do next |
|---|---|---|---|
| P1-04/05/08/09/10 ingest | built | 8-K Item 2.02 filter, cached index, same-day companyfacts cache, 50-issuer EDGAR-resolved universe, idempotent ingest with a failures table | Review `config/universe.yaml` |
| P1-01 store | built (local edition) | SQLite append-only schema v1 (ADR-010) | Open Neon/R2 accounts when ready |
| P2-01/04/05/06 bridge engine | built | 30/30 gold table selection; 338/344 held-out bridges tie out in every period | **Human check**: confirm 10 held-out bridges against sec.gov (RESULTS B) |
| P2-07/08, P3-03..06 | built | Label memory with rule suggestions, policy file, recasts, definition changes, recurrence, normalized EBITDA (preview) | Confirm or correct categories (all 992 are `rule`) |
| P2-14 | built | Bridge scorer and CI gate | — |
| P4-01/03/04/05/07 | built | API, web app, Excel export | — |
| P4-12 public demo | built (artifact) | Static snapshot published as a private claude.ai artifact | Share it from the page's Share menu if you want others to open it |
| Market research | desk research | `docs/research/market.md`, with sources | Not customer evidence |
| Pitch deck | drafted | Slides artifact; the raise amount and contact are placeholders | Fill `[$__]` and contact; rehearse |
| P0-12 interviews, P0-14 spec review | **not done** | An agent cannot hold real customer interviews; desk research does not count | Run them (kit in `docs/discovery/`) |
| Paid users, Stripe, Clerk, ToS, entity | **not done** | Creating accounts and taking payments are owner actions | P4-10 |
| P4-13 second labeller | **not done** | Needs a second person | Before any accuracy figure is published |

**Sources.** See `docs/research/market.md`.

**Stop reason.** The engineering is built and measured. The open items need the owner.

