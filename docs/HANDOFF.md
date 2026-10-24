# Footnote: context transfer for a new Claude Code setup

> Written 2026-10-24 at commit `cd46433` on branch `build/full-platform`. It tells a new
> Claude Code session (new account, possibly a new machine) where the project stands and
> what to do next. It summarizes; the source of truth is the files it links to. If this
> document and a linked file disagree, trust the linked file and fix this one.

---

## 1. Before you switch accounts: move the state that git does not carry

Do these on the **old** setup first. Without them the new session starts behind.

| What | Where | Status at hand-off | Action |
|---|---|---|---|
| 13 commits A-00 … A-19 (all of Track A so far) | `build/full-platform` | Pushed to `origin` on 2026-10-24 | Nothing; check `git status` shows the branch up to date |
| This file and `docs/EXPLAINER.md` | `docs/` | Committed and pushed | Nothing |
| `.claude/launch.json` (preview config for the API) | `.claude/` | Committed; points at `C:/footnote/.venv` | Edit the paths if the repo lives elsewhere |
| Local observation store (~18 MB) | `var/footnote.db` | Git-ignored | Copy it over, or rebuild it (§6) |
| EDGAR response cache (~108 MB) | `backend/data/edgar_cache/` | Git-ignored | Copy it over to skip a re-download. Rebuilding needs `SEC_USER_AGENT` and network |
| Static demo snapshot | `site/` (tracked), `web-dist/` (ignored) | `site/` is in git | Nothing |
| Secrets | `SEC_USER_AGENT`, `ANTHROPIC_API_KEY` | Env vars only, never in files | Set them again in the new shell. Never paste them in chat |
| Claude memory | `~/.claude/projects/C--footnote/memory/` | Empty | Nothing to move |

Other branches (`p0-*`, `main`) are already on GitHub. `main` is at `1f41440` (PR #9);
`build/full-platform` is 40 commits ahead of it and has **no PR yet**. There is an old stash
(`stash@{0}`, from `fix/audit-phases-0-3`) that is not needed.

Repository: `https://github.com/0at-meal/footnote` (private). Owner: Niraj Jadhav.

---

## 2. Read these first (in this order)

1. [CLAUDE.md](../CLAUDE.md): the working rules. They are strict and they override habit.
2. [ARCHITECTURE.md](../ARCHITECTURE.md): modules, data flow, dependency rules, known gaps.
3. [docs/ROADMAP.md](ROADMAP.md): phases, gates, tickets (§7), Track A section.
4. [docs/agent/PLAN.md](agent/PLAN.md): the full Track A brief (evaluated agent).
5. [eval/RESULTS.md](../eval/RESULTS.md): every measured result, newest first, plus the
   Phase 0 gate table.
6. [DECISIONS.md](../DECISIONS.md) and [docs/adr/](adr/): irreversible decisions
   (ADR-005 … ADR-011).
7. [docs/AUTONOMY-LOG.md](AUTONOMY-LOG.md): what earlier autonomous runs did, and what they
   deliberately left to the owner.
8. [docs/EXPLAINER.md](EXPLAINER.md): plain-language explanation of the product, for
   non-specialists.

---

## 3. What Footnote is (one paragraph)

The verified, versioned, normalized record of how US-listed issuers define and adjust
EBITDA, for credit / leveraged-finance analysts first. Each quarter it captures the
issuer's Adjusted EBITDA bridge from the Item 2.02 8-K (EX-99.1), ties it out (sum check
and XBRL GAAP anchor), maps every add-back to a taxonomy, tracks recasts and definition
changes, and computes a policy-driven normalized EBITDA. Every number keeps its
as-reported string and a link to the exact sec.gov text. Numbers come only from
deterministic code; no LLM ever produces a served number.

---

## 4. Where things stand

### Phase 0 (current phase): gate still open

Gate table in `eval/RESULTS.md`:

| Row | Criterion | Status |
|---|---|---|
| 1 | 30-release gold set, tie-out-first | Met |
| 2 | Scorer in CI, split by `verified_by` | Met on merge |
| 3 | Baseline published | Met on merge |
| 4 | ICP pass rule (≥5 of 8 interviews) | **Not met: owner, P0-12** (0 of 8 done) |
| 5 | Normalization spec v0.1 reviewed by ≥2 analysts | **Not met: owner, P0-14** |

Everything left in Phase 0 is owner-only work (interviews, spec review, accepting
`docs/NORMALIZATION.md`). An agent must not simulate interviews or reviews. The kit is in
`docs/discovery/` (script, rubric, tracker, recruiting, spec-review brief,
design-partner offer).

### Phases 1–4: built ahead of the gate, not gate-approved

Under an owner directive on 2026-10-23 (ADR-010), the platform was built locally:
EDGAR ingest (50 issuers × 8 quarters, `config/universe.yaml`), bridge engine, append-only
SQLite store, analytics (history, recasts, definition changes, normalization preview),
FastAPI read API, single-page web app (`web/index.html`), Excel export, review CLI, change
digest, scheduled-ingest workflow. Hosting (Neon, R2, Cloud Run) is not set up; it needs
the owner's accounts. Known gaps are listed at the end of `ARCHITECTURE.md`.

Headline measured numbers (internal only, see `eval/RESULTS.md`):
- Gold set: table found 30/30, line/role/sign/scale 100% on 1,202 values (in-sample;
  1,197 of them `model_agreement`, 5 `human`).
- Held-out: 421 releases, 418 with HTML EX-99.1, 388 not in the gold set; sum and anchor
  tie-out results are in RESULTS section B.
- All 992 category assignments are `source='rule'`; no human has confirmed any. The
  review queue is `review/category-queue.csv`.

**No accuracy figure may be shown externally** until second-labeller agreement (P4-13).

### Track A (evaluated agent, ADR-011): runs alongside the phases

| Ticket | Status |
|---|---|
| A-00 governance, ADR-011, plan | done |
| A-01 question schema + validator | done |
| A-02 keys C1–C7 | done |
| A-03 must-refuse / false-premise questions | done (benchmark now 379 questions: dev 90, test 289) |
| **A-04 [owner]** 20–30 analyst-phrased questions; verify 60 test keys on sec.gov | **open, owner** |
| **A-05** freeze test split, sha256 manifest in CI | **open: next engineering ticket** (no `eval/agent/manifest.sha256` yet) |
| A-06 scorer | done |
| A-07 harness (budget cap, replay) | done |
| A-08 baselines B0/B1/B2 | done (prompt sizes and cost estimate recorded) |
| A-09 tools, A-10 compute, A-11 gate/renderer | done |
| A-12 agent loop + Anthropic adapter | done; tested only with a scripted fake client (30/30 on C2) |
| **A-13** first full run, all systems × 3 trials | **open: needs `ANTHROPIC_API_KEY` and an owner budget cap** |
| A-14..16 fix top 3 failure classes | open, after A-13 |
| A-17 [owner] human check of 30 agent answers | open |
| A-18 read-only MCP server | done (smoke run) |
| A-19 earnings-night brief | done (deterministic sections; claim-precision eval needs a labelled sample) |
| A-20 ask-with-receipts API, web view, Excel export | open |

Sequencing note: A-04 adds questions, and A-05 freezes the test split. If the owner's
A-04 questions are meant for the test split, freeze after they land, or freeze now and
publish them as a new benchmark version. Ask the owner which.

Code: `backend/app/agent/` (tools, compute, values, answer, gate, model, llm, loop,
mcp_server) and `backend/tools/agent_eval/` (questions, keys, traps, records, systems,
baselines, agent_system, run, score). Questions and pricing: `eval/agent/`.

---

## 5. What to do next

In priority order. Confirm with the owner before anything outward-facing (push, PR,
spending API budget).

1. **Open a PR** for `build/full-platform` → `main` (owner approval first). The branch is
   pushed but has no PR.
2. **A-05**: freeze the test split (after settling the A-04 question above).
3. **A-13**: get a budget cap from the owner, confirm `ANTHROPIC_API_KEY` is set in the
   environment, re-check model IDs and prices (use the `claude-api` skill; `eval/agent/pricing.yaml`
   holds the table the harness uses), then run a small dev-split slice before the full run.
   Cost estimate for B0–B2 over 379 × 3 is about $210 at Opus prices before A1 and thinking
   tokens (RESULTS, A-08 entry).
4. **A-14..16**, then **A-20**.
5. Owner items to keep visible, never to simulate: P0-12 interviews, P0-14 spec review,
   A-04, A-17, category confirmation, a 10-bridge human check of held-out results, P4-13.

Do not open Phase 1 tickets as "phase work"; the Phase 0 gate is not met.

---

## 6. Setup on a new machine

Python 3.11. From the repo root:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
```

Environment (set in the shell; the code does not read `.env`):
- `SEC_USER_AGENT="<owner's name> <owner's email>"`: required for any EDGAR call.
- `ANTHROPIC_API_KEY`: only for A-13 and later live agent runs.
- Optional: `FOOTNOTE_DATA_DIR` (default `backend/data`), `EDGAR_CACHE_DIR`.
  See `.env.example`.

Checks (Windows has no `make`):

```bash
ruff check backend && ruff format --check backend && mypy && cd backend && pytest
```

At hand-off: **302 passed**. CI (`.github/workflows/ci.yml`) also runs the gold-set
sha256 check, label validation, both scorer gates and the question validator.

Rebuild the store if `var/footnote.db` was not copied (from `backend/`):

```bash
python -m app.pipeline.cli ingest --quarters 8
```

Other commands (from `backend/`):
- API + web app: `uvicorn app.api.main:app --port 8000`
- Excel export: `python -m app.pipeline.cli export`
- Bridge scorer: `python -m tools.eval.score_bridge`
- Brief: `python -m app.analytics.brief <TICKER>`
- MCP server: `python -m app.agent.mcp_server --db ../var/footnote.db`
- Agent eval: `python -m tools.agent_eval.run --split dev --systems B0,B1,B2,A1 --trials 3 --model <id> --budget-usd <cap>`; add `--replay` to re-score saved transcripts with no API calls.

---

## 7. Rules a new session tends to break

- Served numbers only from deterministic code. The agent cites values by ID; the gate
  rejects any numeral the model typed.
- Only `ingestion/edgar/` touches the network; the LLM SDK is allowed only in
  `app/agent/llm.py` and `tools/agent_eval/`. `tests/test_architecture_boundaries.py`
  enforces this.
- No silent failure: explicit status and reason, never a guessed scale or a swallowed
  exception.
- Never fabricate data, URLs, CIKs, labels, interview notes or human checks. If a step
  needs a human, stop and say so.
- Every result goes in `eval/RESULTS.md` with date, commit, command, N and label
  provenance. Keep negative results.
- Atomic tickets, one concern per commit, tests included, `mypy --strict` without
  `# type: ignore`.
- Irreversible decisions go in `DECISIONS.md`.
- The removed PDF/workbook product is at tag `v0-extraction`: reference only.
