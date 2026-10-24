# Footnote Agent: build prompt (Track A — "verified answers, measured")

> Paste-ready brief for an implementing agent. On approval, step A-00 saves it to
> `docs/agent/PLAN.md` so it lives in the repo.

## Context

Footnote already holds what general AI tools lack: a deterministic, append-only record of
every Item 2.02 EBITDA bridge for 50 leveraged issuers × 8 quarters. Every value has its
as-reported string, an XPath, a sec.gov text-fragment URL, sum and XBRL tie-outs, recasts,
definition changes and a policy-driven normalized EBITDA (`eval/RESULTS.md`, 2026-10-23).

The owner wants an AI agent on top of it that credit analysts would sign up for at once.
It must not be another "chat with a 10-K" demo. It stands out only if its evaluation is
rigorous, so **most of the effort goes into the test set, scorer and baselines**, and the
interface stays thin.

Public evidence for why this gap exists (re-check before quoting anywhere):
- FinanceBench (Patronus, 2023): GPT-4-Turbo with retrieval answered wrongly or refused
  81% of 150 questions. https://arxiv.org/abs/2311.11944
- Vals AI Finance Agent: the best tool-using frontier models score roughly 60–65% on
  entry-level analyst tasks over SEC filings. https://vals.ai/benchmarks/finance_agent
- Fin-RATE (2026): accuracy drops ~18.6 points on multi-period tasks and ~14.4 points on
  cross-company tasks, mainly from period and entity mismatches.
  https://arxiv.org/abs/2602.07294
- Credit analysts' core job is exactly the weak spot: multi-period, cross-issuer,
  point-in-time numbers with add-back judgement (`docs/research/market.md`).

**Thesis:** general agents fail on finance because they *produce* numbers from text.
Footnote's agent never produces a number. It *references* verified numbers, and a
deterministic gate checks the reference. The eval measures how often each approach gives an
analyst a wrong number. That rate is the headline metric.

## Principles taken from the best agents, and how they apply here

| Source | Principle | Footnote application |
|---|---|---|
| Hebbia Matrix | Every answer is a cell with a citation; work in grids, not chat | Answers are structured claims, each with a click-to-source link; outputs export to Excel |
| Daloopa MCP, Claude for Financial Services | Be the trusted data tool *inside* the analyst's existing AI client | Ship Footnote as a read-only MCP server; the same tools drive our agent and the eval |
| Octus CreditAI / CovenantAI | Credit-specific workflows (benchmark vs comparable deals, flag deviations) beat generic Q&A | Lead with the earnings-night credit brief and peer add-back benchmarking, not a chat box |
| Anthropic agent-eval practice | Grade outcomes rather than paths; read transcripts; report pass^k reliability, not just pass@1 | Deterministic outcome grader, transcript archive, pass^3 for every system |
| FinanceBench / Vals | Fixed question set, closed-book and RAG baselines, cost per query | Same structure, with a frozen hashed test split and cost per *correct* answer |
| Footnote's own rules | No silent failure; provenance or it doesn't ship | Refusal is a first-class answer status with a reason code, and it is measured |

## Architecture (new rules need ADR-011 first)

1. **Numbers by reference.** Tools return values with a stable `vid`, e.g. `obs:<bridge_id>:<row_order>:<period_id>`,
   or `calc:<hash>` for a deterministic computation. The model writes prose with
   placeholders (`{{obs:812:3:3M-2026-06-30}}`). A deterministic renderer substitutes the
   formatted value plus its source link. A **provenance gate** rejects any answer that has
   bare numerals outside an allow-list (years, period labels, quoted issuer names), an
   unknown vid, or a vid the agent never retrieved this session. Rejection → one retry →
   status `refused: unverifiable`. So the LLM never types a served number, and CLAUDE.md's
   rule holds by construction.
2. **Answer schema** (pydantic): `status ∈ {answered, partial, refused}`,
   `reason_code` (for example `not_covered`, `metric_not_ebitda`, `scale_unknown`,
   `period_not_reported`, `false_premise`, `ambiguous`, `unverifiable`), `claims[]`
   (text + vids), `trace[]` (tool calls), `policy_version`.
3. **Tools** are pure, typed, read-only functions over `Store`, in a new
   `backend/app/agent/tools.py`. They reuse the existing analytics:
   - `resolve_issuer`: universe + coverage;
   - `get_bridge(ticker, period, as_of=latest|first_reported|<date>)`: `current_bridges`
     and observations, with checks attached;
   - `get_series(ticker, line_key|category, periods)`: `history.quarter_series`;
   - `get_changes(ticker, since)`: `history.recasts`, `history.definition_changes`;
   - `get_normalized(ticker, period, policy)`: `normalize.normalize_issuer`,
     `normalize.recurrence`;
   - `get_peers(metric, period)`: the snapshot peer logic in `analytics/snapshot.py`;
   - `compute(op, vids)`: Decimal-only LTM sum, delta, % change, ratio and share. It returns
     a `calc:` vid with the formula, refuses mixed scales or periods, and never guesses.
   - Every result carries `status`/`reason`, following the no-silent-failure rule.
4. **Boundaries.** An LLM SDK is allowed only in `backend/app/agent/llm.py` and
   `backend/tools/agent_eval/`. Update `test_architecture_boundaries.py` with that exception
   and with new rules: `agent/` never writes to the store, and never imports `ingestion/`
   or `pipeline/`. Tools must not import the LLM module.
5. **Model.** Claude via the Anthropic API (latest Sonnet as the default, Haiku and Opus as
   cost and quality columns), using tool use with prompt caching. Model IDs and prices come
   from the `claude-api` skill at build time, never from memory.

## The evaluation: FootnoteBench-Credit v0 (most of the effort)

**Question schema** (`eval/agent/questions/*.jsonl`, validator plus tests): `id`, `split`
(dev/test), `category`, `question`, `as_of`, `expected.status`, `expected.reason_codes`,
`expected.values[]` (value, scale, period, tolerance = half a unit of reported scale),
`expected.source_urls`, `key_provenance ∈ {gold_human, gold_model_agreement, tieout, human_checked}`,
`author`, `date`. No answer key without provenance.

**Categories and target counts (~400 questions: 100 dev, 300 frozen test):**

| # | Category | Example | Share |
|---|---|---|---|
| C1 | Point lookup | "CC Adjusted EBITDA, 3M ended 2026-06-30, as reported?" | 10% |
| C2 | Multi-period math | "LTM Adj. EBITDA and YoY change for WYNN at Q2 2026" | 15% |
| C3 | Point-in-time / recast | "What did CC first report for Q2 2024 net income, and what is it now?" | 10% |
| C4 | Add-back composition | "Share of Adj. EBITDA from restructuring for TDG over the last 4Q" | 10% |
| C5 | Definition change | "Which add-backs did X add, drop or rename since Q4 2025?" | 10% |
| C6 | Normalization under policy | "Normalized EBITDA for CC Q2 2026 under default v0.1, itemized" | 10% |
| C7 | Cross-issuer | "Top 5 issuers by add-back intensity, latest quarter" | 10% |
| C8 | Must refuse / flag | AMCX EBITDA (not an EBITDA metric), SIRI (scale unknown), an unreported future quarter, an uncovered issuer, covenant EBITDA, guidance | 15% |
| C9 | False premise / traps | "Why did X's EBITDA fall 40%?" when it rose; thousands-vs-millions; reverse-sign bridges | 10% |

**How answer keys are built (no circularity hidden):**
- C1–C7 keys are generated deterministically by `tools/agent_eval/keys.py`. Gold-set
  releases use the gold labels. Held-out releases use only values whose bridge passes
  *both* sum and anchor checks (`tieout`). Each question records which.
- C8 keys come from the `failures` table reasons and coverage gaps. C9 keys are written by
  hand.
- **Disclosed caveat:** `tieout`-keyed questions measure retrieval and reasoning, not
  extraction, since the agent reads the same store. Gold-keyed and human-checked questions
  measure the end-to-end chain. Every metric is reported split by `key_provenance`, the
  same way `score.py` splits by `verified_by`.
- The owner verifies a random 60 test keys against sec.gov (`human_checked`), and adds 20–30
  real analyst questions in their own words (from interviews or experience).
- Question *wording* may be paraphrased for variety by a model. Numbers and keys never are.
- The test split is frozen: a sha256 manifest is checked in CI, and a changed test file
  fails the build. Iterate only on dev. Every new version is a new benchmark version.

**Scorer** (`tools/agent_eval/score.py`, deterministic, unit-tested):
- **Wrong-number rate** (headline): answers containing ≥1 number that doesn't match the key
  within tolerance, as a share of answered questions. Period or entity mismatch counts as
  wrong.
- Accuracy (fully correct / all), coverage (answered / answerable), and a selective
  risk–coverage curve.
- Refusal confusion matrix: correct refusal on C8/C9, and over-refusal on C1–C7, with
  reason-code accuracy.
- Citation validity: each cited URL/XPath actually contains the value (checked against the
  cached exhibit with `analytics/source.py`).
- pass^3 reliability (all 3 trials correct), alongside pass@1.
- Cost per question, cost per *correct* answer, p50/p95 latency, tool calls, tokens.
- No LLM judge in v0. If free-text grading is added later, it is calibrated against human
  labels with the agreement reported.

**Systems compared (same model, same questions, same filings available as of `as_of`):**
- B0 closed-book: the question only, as a floor and contamination check.
- B1 plain RAG: BM25 over chunked EX-99.1 and 10-Q HTML from the EDGAR cache, top-k in
  context ($0, no vector DB).
- B2 long-context: the relevant full EX-99.1 exhibit(s) pasted in. This is the strongest
  "chat with a filing" baseline.
- A1 Footnote agent: tools, numbers by reference, provenance gate.
- Ablations: A1 without the gate (free-typed numbers), and A1 without `compute`. These show
  which part of the design earns the gain.
- Model column: A1 and B2 on Haiku/Sonnet/Opus for the cost-accuracy frontier.

**Harness** (`tools/agent_eval/run.py`): resumable, writes the full transcript JSONL per
trial to `eval/agent/runs/<date>-<system>/`, enforces a hard budget cap in USD, records
model ID and prompt hash. A `--replay` mode re-scores saved transcripts with no API calls,
so CI scores without a key.

**Write-up:** a new `eval/RESULTS.md` entry with N, splits, provenance, cost, and a failure
taxonomy with a real example per class (wrong period, wrong scale, stale vs recast, wrong
entity, hallucinated number, unwarranted refusal, bad citation). Negative results are kept.
Internal only until P4-13 and the human check below are done.

## The product credit analysts would sign up for (thin interface, built after eval v0)

1. **Earnings-night credit brief** per watchlist issuer, generated when a new Item 2.02 8-K is
   ingested. Deterministic sections come from `analytics/digest.py`: reported vs first-reported
   vs normalized EBITDA, new, dropped or renamed add-backs, recasts, recurring
   "non-recurring" items, add-back intensity vs peers, and tie-out exceptions. The agent
   writes only the narrative and "questions for management", by reference. Every number
   links to its sec.gov text fragment. The brief has its own metric: claim precision on a
   human-labelled sample.
2. **Footnote MCP server** (read-only, the same tools) so analysts can use it from Claude or
   another MCP client. This is how analysts already work, it avoids building a chat UI, and
   it is how Daloopa reaches the same users.
3. **Ask-with-receipts** endpoint and a minimal web view: answer, status and reason, every
   number clickable, the tool trace shown as formulas, and a one-click Excel export with
   live formulas (reusing `export/excel.py`).

## Tickets (≤1 day each, in order; the eval comes before the agent)

- **A-00**: DECISIONS entry + ADR-011 (Track A, numbers-by-reference, LLM boundary) + ROADMAP
  track section with gates; save this plan to `docs/agent/PLAN.md`. Needs the owner's sign-off.
- **A-01**: Question schema + validator + tests.
- **A-02**: Deterministic key generators C1–C7 from gold and tie-out data.
- **A-03**: C8/C9 builders (failures table, coverage gaps) + hand-written traps.
- **A-04 [YOU]**: 20–30 analyst-phrased questions; verify 60 sampled test keys on sec.gov.
- **A-05**: Freeze test split; manifest hash check in CI.
- **A-06**: Scorer (all metrics above) + tests on synthetic transcripts that are clearly
  marked fixtures.
- **A-07**: Harness with budget cap, transcripts, cost/latency, replay mode.
- **A-08**: Baselines B0/B1/B2 (BM25 retrieval over the cache).
- **A-09**: Agent tool layer over `Store` + tests on the real local store.
- **A-10**: `compute` tool (Decimal, formula trace, scale/period guards).
- **A-11**: Answer schema, renderer, provenance gate + tests (including bare-numeral
  rejection).
- **A-12**: Agent loop (`llm.py`: tool use, step cap, refusal policy, prompt caching).
- **A-13**: First full run, all systems × 3 trials → RESULTS entry.
- **A-14..16**: Fix the top 3 failure classes, one per ticket, each with its delta logged.
- **A-17 [YOU]**: Human check of 30 agent answers against sec.gov.
- **A-18**: MCP server (read-only tools) + contract tests.
- **A-19**: Earnings-night brief + claim-precision eval.
- **A-20**: Ask-with-receipts API + minimal web view + Excel export.

**Track A gate** (proposed; the owner adjusts the numbers in A-00):
- Wrong-number rate ≤1% on answered test questions, overall and on the gold-keyed slice.
- Correct refusal ≥90% on C8/C9; over-refusal ≤10% on C1–C7.
- pass^3 reported for every system.
- Beats B2 on wrong-number rate with the gap and N stated.
- A-17 human check done.
- No external accuracy claim until P4-13 is also met.

## Critical files

- New: `backend/app/agent/{tools,compute,answer,gate,llm,loop}.py`,
  `backend/tools/agent_eval/{questions,keys,traps,run,baselines,score}.py`,
  `eval/agent/questions/`, `eval/agent/manifest.sha256`, `docs/adr/ADR-011-agent.md`.
- Modified: `backend/tests/test_architecture_boundaries.py`, `CLAUDE.md` (scoped LLM rule),
  `docs/ROADMAP.md`, `DECISIONS.md`, `eval/RESULTS.md`, CI workflow.
- Reused: `app/store/db.py` (`Store`, `current_bridges`), `app/analytics/history.py`,
  `normalize.py`, `snapshot.py`, `source.py` (citation check), `digest.py` (brief),
  `export/excel.py`, `tools/gold/labels.py` (gold keys), `tools/eval/score.py` (split-by-provenance pattern).

## Verification

- `ruff check backend`, `ruff format --check backend`, `mypy`, `cd backend && pytest` all
  green. The boundary test proves no LLM import outside the allowed modules.
- Gate tests: crafted answers with a bare number, an unknown vid, or an unretrieved vid are
  all rejected.
- `python -m tools.agent_eval.run --split dev --systems B0,B1,B2,A1 --trials 3 --budget-usd <cap>`
  runs, then `--replay` reproduces identical scores with no network access.
- The manifest check fails CI if a test question changes.
- A human (the owner) checks 30 agent answers and 60 keys against sec.gov before anything is
  called done.

## What the owner provides

1. **Anthropic API key** as `ANTHROPIC_API_KEY` in your local env or a GitHub secret, never
   pasted in chat. Set a monthly spend limit in the Anthropic console, and give me a budget
   cap for eval runs. The harness stops at that cap, and I estimate cost from current pricing
   before the first full run.
2. **Sign-off on the governance change (A-00):** an agent track outside the current Phase 0
   (as ADR-010 did), and a scoped exception to "no LLM SDK imports".
3. **About 4–5 hours of review:** 60 answer keys + 30 agent answers checked against sec.gov,
   plus 20–30 real analyst questions.
4. **Optional:** 2–3 credit analysts (ideally from the P0-12 interviews) to read one
   earnings-night brief each. Their reactions double as ICP evidence.
5. **Not needed:** a vector DB, paid hosting, or any new account other than the Anthropic one.
