# Footnote — Roadmap

> **Status:** adopted 2026-10-14. **Current phase: 0** (ground truth, ICP validation, normalization spec).
> This is the standing plan. Phases are gates, not dates. Changes to it are recorded in [DECISIONS.md](../DECISIONS.md).

## Context

This roadmap reconciles three inputs:
1. An external research report, *"Brownfield SRS & Decision Document"* (2026-10-13). It was
   written before the 2026-10-14 clean-up, from the public repo only.
2. A first review of that report.
3. An independent stress test of the review.

**Owner decisions:**
- strict **$0 infrastructure until first revenue**;
- **credit / leveraged-finance analysts** as the first customer;
- **the owner hand-labels the gold set** with tooling built here;
- **public SEC filings first**, private documents later.

**Goal:** an enterprise-grade SaaS with a real moat, built one gated phase at a time from atomic
tickets, under strict principles.

---

## 1. Verified facts (re-checked 2026-10-14)

| Claim | Status | Source |
|---|---|---|
| Sidequest is Node.js/TS (not usable from Python) | ✅ true | docs.sidequestjs.com |
| Procrastinate is a Python, Postgres-backed queue (fallback if a queue is ever needed) | ✅ true | procrastinate.readthedocs.io |
| Groq free `gpt-oss-120b`: 30 RPM / 1,000 RPD / 200K tokens per day | ✅ true (report's 14,400 RPD was wrong) | benchlm.ai, Novita |
| Clerk free: 50K monthly *retained* users (since Feb 2026) | ✅ true | clerk.com |
| HF Spaces free: 2 vCPU / 16 GB; sleeps after 48 h; non-persistent disk | ✅ true | huggingface.co docs |
| Neon free: 0.5 GB, 100 CU-hours/month, scale-to-zero after 5 min | ✅ true | neon.com/pricing |
| Cloud Run: idle non-minimum instances are not billed; monthly free vCPU/GiB-seconds | ✅ true (amounts vary by source; check the official page) | cloud.google.com/run/pricing |
| GitHub Actions cron "disabled on private repos for free accounts" (stress test) | ❌ **false.** Private repos get 2,000 free min/month; the 60-day inactivity auto-disable applies to **public** repos | docs.github.com |
| Daloopa is "as reported" | ✅ **stated by Daloopa** ("without editing or adjusting it"). Also: **renamed lines are merged into one item** and **restated numbers are not displayed by default**. This *strengthens* our change-intelligence wedge | docs.daloopa.com |
| Calcbench publishes cross-company add-back studies | ✅ true (competitor for research, not workflow) | Calcbench/Suffolk studies |
| Packaging Corp "×1,000,000 public float" | ❌ unverified; do not cite | sec.gov R1 pages |
| Official EDGAR filings are HTML/iXBRL; non-GAAP bridges sit in untagged EX-99.1 HTML | ✅ true | EDGAR structure |

### 1.1 Stress-test verdicts, reassessed

| Stress-test point | Verdict | Change to the plan |
|---|---|---|
| Normalization methodology undefined (critical) | **Agree** | Spec v0.1 becomes a Phase 0 deliverable, reviewed in interviews. It must be frozen before Phase 2 (§3) |
| ICP assumed, not validated | **Agree** | Phase 1 opens only after ≥5 scored interviews meet a pass rule. A fallback persona is pre-declared (§2) |
| Verification burden underestimated (24–40K reviews at 1,000 issuers) | **Partly wrong.** Issuers reuse the same labels every quarter, and sum + XBRL tie-outs verify *values* automatically | Add **issuer-scoped label memory**; humans review only new labels and failed tie-outs. The cost model (§6) gives ~5–8K one-time decisions at 1,000 issuers, then ~5–10% of issuers per quarter |
| Text-fragment *and* DOM path provenance | **Agree** (half built) | `HtmlLocator` already has `element_path`; `sec_archives_url(text=...)` already builds text fragments. Add a stored `quote` field (P1-03) |
| `PackSpec` before Phase 1 | **Disagree (YAGNI)** | Packs arrive in Phase 5. Spec defined then, *without* xlsx templates or callable validation |
| GitHub Actions private-repo cron | **Wrong claim** | Keep GitHub Actions (private repo). Budget the minutes (§6). Cloud Run Jobs is the fallback |
| Cloud Run cold start | **Agree, mild** | Measure first. If p95 cold start > 2 s, add a business-hours warm-up ping. Never `min-instances` (it costs money) |
| Review console: CLI first | **Agree** | P3-02 becomes a CLI; a web console only when a non-technical reviewer exists |
| LLM label suggestions earlier | **Agree, conditionally** | Phase 3 ticket, triggered only if the unmatched-label rate after label memory is > 10%. Labels only, never numbers; human confirms |
| Point-in-time versioning in the schema from P1 | **Agree** | An append-only *observation* model from P1-01 (§4), simpler than `superseded_by` chains |
| Tie-out tolerance ±1 unit | **Partly wrong.** Too strict with many rounded lines | Tolerance = max(1, ⌈n/2⌉) units of the reported scale; label-mismatched anchors become *review*, not *fail* |
| Caching / rate limiting unspecified | **Already built** | `EdgarClient`: immutable accession cache, ≤10 req/s token bucket, 429 backoff, circuit breaker. Add the R2 raw store (P1-02) |
| Consent for using customer corrections | **Agree** | Org-level opt-in; contributions are anonymized; written into the ToS (P4-10) |
| Cold-start data moat for the first customer | **Agree** | Design partners get free or discounted access in exchange for review feedback. Day-one value comes from verified data plus change alerts, not network effects |

---

## 2. Product thesis, ICP and validation

**Product.** *The verified, versioned, normalized record of how every US-listed issuer defines
and adjusts EBITDA.* Every quarter the product:
- captures each issuer's reported bridge (EX-99.1 and 10-Q/10-K);
- ties it out to XBRL;
- maps every line to a standard add-back taxonomy, with a click-through to the exact sec.gov
  text;
- tracks definition changes and recasts;
- computes a **policy-driven normalized EBITDA**: Footnote's default policy, or the
  customer's own.

**Moat**, compounding:
1. **Point-in-time verified history.** Recasts and definition changes cannot be re-scraped
   later.
2. **Normalization standard plus customer policy profiles.** A firm encodes its own add-back
   policy once and applies it across the universe. This is the lock-in.
3. **Change intelligence.** Daloopa merges renamed lines and hides restatements; we surface
   them.
4. **Trust.** Every number is linked to its source, with published accuracy (N stated).

**ICP:** buy-side credit, direct lenders, high-yield/BDC and leveraged-finance analysts.

**Fallback persona** (pre-declared): equity earnings-quality / forensic analysts. They need the
same data asset; only the alert and UI emphasis change.

**ICP pass rule** (Phase 0 → Phase 1). At least 5 of the first 8 interviewees:
- rebuild or adjust EBITDA bridges manually at least quarterly; **and**
- at least 3 name a price anchor or ask for a trial; **and**
- fewer than half say an existing tool already covers normalization plus change tracking.

If the rule fails, switch to the fallback persona and re-interview 5. The core data engine
(Phases 1–3) is the same either way.

---

## 3. Normalization spec v0.1 (Phase 0 deliverable, frozen before Phase 2)

`docs/NORMALIZATION.md` defines:
1. **Taxonomy:** the add-back categories, starting from the cleaned 84-item seed plus the
   `StandardAddBackCategory` set, extended for credit. Examples:
   - SBC;
   - restructuring/severance;
   - impairment;
   - M&A/integration/transaction;
   - litigation;
   - FX;
   - pro-forma/run-rate synergies;
   - "other non-recurring";
   - D&A, interest and taxes kept separate.
2. **Default treatment per category:** *accept*, *exclude* (reverse the add-back) or *flag*.
   For example, run-rate synergies and recurring "non-recurring" items are excluded by default.
3. **Recurrence rule:** a category added back in ≥3 of the last 4 quarters is flagged
   "recurring". This is deterministic.
4. **Normalized EBITDA** = reported Adjusted EBITDA − Σ(add-backs whose policy treatment is
   *exclude*). Every adjustment is itemized with its source line.
5. **Edge cases:**
   - lines mixing categories map to "other" + flag;
   - partial add-backs are kept as reported + flag;
   - bridges that start from operating income;
   - segment-level bridges.
6. **Versioning:** each methodology version is immutable; results are stored with the policy
   version; changes are logged in DECISIONS.
7. **Customer policy profiles:** an org overrides per-category treatment (Phase 5).

The spec is reviewed by ≥2 interviewed credit analysts before being frozen.

---

## 4. Architecture

```
EDGAR (submissions+paging, filing index, EX-99.1 HTML, 10-K/Q HTML, XBRL companyfacts)
  │ scheduled ingest: GitHub Actions cron (private repo) → fallback Cloud Run Jobs
  ▼ SEC UA, ≤10 req/s, immutable cache
R2 raw_documents (accession/doc, sha256, write-once)
  ▼ parse → bridge → tie-outs → normalize (policy vN)
Neon Postgres — GLOBAL (public data, append-only observations)
  issuers · filings · documents · bridges(accession,table) · bridge_line_observations
  (issuer, metric, period, line_key, value_raw, value, scale, sign, quote, xpath, accession)
  · xbrl_facts · tieouts · label_memory(issuer,label→category) · changes · verifications
  · failures(run, stage, reason)
Neon Postgres — TENANT (RLS, Phase 4+): orgs · users · watchlists · notes · policies
  · corrections(opt-in) · api_keys
  ▼
FastAPI read API (Cloud Run) → Web (Cloudflare Pages) · Excel export · email digests
```

**Point-in-time** is free with this model:
- every value is an *observation* tied to the filing it came from;
- "as first reported" is the earliest observation;
- "current" is the latest;
- a recast is two observations of the same `(issuer, metric, period, line_key)` with
  different values.

**Reused from the current repo:**
- `EdgarClient`;
- `exhibit_99/*`;
- `extract_html_tables` / `parse_numeric_cell`;
- `detect_reconciliation_tables`;
- `parse_ixbrl_facts`;
- `HtmlLocator`, `sec_archives_url`, `require_provenance`;
- `scale_and_sign`;
- `taxonomy.py` + `seed_taxonomy.json`;
- `config.py`;
- the architecture-boundary tests.

---

## 5. Strict principles (mirrored in CLAUDE.md)

1. **Gates, not dates:** numeric exit criteria; the next phase opens only when they pass.
2. **Measured truth:** gold set + `eval/RESULTS.md`, with sample size and label provenance;
   negative results kept.
3. **Deterministic numbers:** no LLM ever produces or alters a value. LLMs may only *suggest
   labels* for human confirmation.
4. **No silent failure:** every skip or failure goes to the `failures` table with a stage and
   reason.
5. **Provenance or it doesn't ship:** every served number has an accession, sha256, XPath and
   quote.
6. **Public data global; customer data tenant-scoped (RLS).**
7. **Append-only observations:** never overwrite a reported value.
8. **Atomic tickets:** ≤1 day, one concern, one PR, tests, `make check` green, docs and
   DECISIONS updated.
9. **Done** = tests + a run on real saved filings + a human check (extraction tickets).
10. **$0 until first revenue;** migration triggers written in advance.

---

## 6. Operational models

**Verification labour.** Assumptions are re-measured in P2-10:

| Item | Estimate |
|---|---|
| Lines per bridge | 8–15 |
| Non-alias labels on first ingest of an issuer | ~3–8 |
| Rate of issuers with a new or changed label in a later quarter | ~5–10% |
| 150 issuers backfill (Phase 3) | ~450–1,200 label decisions, at ~20 s each ≈ 3–7 h, one-time |
| 1,000 issuers backfill (Phase 5) | ~3–8K decisions ≈ 17–45 h one-time; then ~50–100 issuers × ~3 labels per quarter ≈ 1–2 h per quarter |
| Value review | only failed tie-outs (target <10% of bridges) |

**Fallback if labour exceeds capacity:** cap coverage to the highest-value issuers and turn on
LLM label suggestions (P3-08).

**GitHub Actions budget:**
- the quarterly earnings peak is ~150 issuers × 2 filings ≈ minutes of HTTP at 10 req/s;
- daily runs ≈ 1–3 min, so ≪ 2,000 min/month;
- the fallback is Cloud Run Jobs + Cloud Scheduler.

**Neon budget:** ingest runs are bursty and the database scales to zero between them. There
is no always-on worker. Track CU-hours per run in the run log.

**Storage:** raw HTML goes in R2 (10 GB free), not Postgres. The Postgres estimate is 150
issuers × 8 quarters × ~15 lines × ~2 periods ≈ 36K observation rows, which is tiny next to
0.5 GB.

**Migration triggers:**
- Neon storage > 400 MB or CU-hours > 80/month → Neon Launch;
- Cloud Run free tier exceeded → budget alert;
- cron minutes > 1,500/month → Cloud Run Jobs;
- first enterprise isolation request → ADR.

---

## 7. Phases and atomic tickets

`ID — task → acceptance`. `[YOU]` = owner's work; everything else is engineering (agent).

### Phase 0 — Ground truth, ICP validation, normalization spec
**Exit gate (all required):**
- 30-release gold set labelled + 10 double-labelled (agreement reported);
- scorer in CI;
- baseline published;
- ICP pass rule met (§2);
- normalization spec v0.1 reviewed by ≥2 analysts.

- **P0-01** — Propose 15 leveraged issuers (from EDGAR) for the owner to approve →
  `eval/gold/issuers.yaml`.
- **P0-02 [YOU]** — Approve or edit the issuer list.
- **P0-03** — Fetch and save 30 real EX-99.1 releases (15 × 2 quarters), sha256 + sec.gov URL
  manifest → `eval/gold/raw/`.
- **P0-04** — Gold label JSON schema (line, period, value_raw, scale, sign, quote, labeler,
  date, source URL) + validator → tests.
- **P0-05** — `tools/label` CLI: pre-fills a draft from the extractor and opens the sec.gov
  text fragment → works on 3 sample releases.
- **P0-06 [YOU]** — Label 30 releases, verifying each row on sec.gov → validator passes.
- **P0-07 [YOU + second person]** — Independently re-label 10 → agreement % in RESULTS.
- **P0-08** — `eval/score.py`: line exact match, table-found, scale and sign accuracy → tests.
- **P0-09** — Baseline run of current code → first `eval/RESULTS.md` entry.
- **P0-10** — CI job: scorer must not regress below baseline → PR check.
- **P0-11** — Interview script + scoring rubric (workflow, pain, normalization trust, existing
  tools, price anchors, buying process) → `docs/discovery/`.
- **P0-12 [YOU]** — Run 8 interviews (5 before Phase 1 can open) → scored notes.
- **P0-13** — Draft `docs/NORMALIZATION.md` v0.1 (§3) → reviewed by the owner.
- **P0-14 [YOU]** — Get ≥2 interviewed analysts to critique the spec → feedback logged; I
  revise to v0.2.
- **P0-15** — Revised ADRs (ingest, global/tenant data, packs, offline/online, $0 deploy) →
  `docs/adr/`.

### Phase 1 — Filing graph & ingestion
**Exit gate:**
- 50 issuers × 8 quarters ingested;
- re-run creates 0 new rows (idempotent);
- every skip or failure has a reason;
- CU-hours per run logged.

- **P1-01** — Postgres schema v1 (§4 global tables, observation model) + Alembic → up/down
  tested.
- **P1-02** — R2 raw store: write-once by sha256 → tests with moto.
- **P1-03** — `HtmlLocator.quote` field + text-fragment link generation → tests.
- **P1-04** — EDGAR: paginate `filings.files` → multi-page fixture test.
- **P1-05** — EDGAR: 8-K `items` filter (2.02) → test.
- **P1-06** — Settings: cache dir and UA from env; drop the relative default → test.
- **P1-07** — XBRL `companyfacts` client (units, periods, duration vs instant) → typed facts +
  tests.
- **P1-08** — `universe.yaml` + validator (ticker → CIK, segment) → test.
- **P1-09** — `footnote ingest` CLI: idempotent upserts + run log → re-run test.
- **P1-10** — Failures table + retry policy (transient vs. permanent) → test.
- **P1-11** — GitHub Actions scheduled ingest (secrets, manual dispatch) → green run.
- **P1-12** — Backfill 50 × 8 → run report in RESULTS.

### Phase 2 — Bridge engine (requires spec v0.2 frozen)
**Exit gate:**
- ≥95% line-level exact match on the gold set;
- ≥95% table-found;
- ≥90% of ingested bridges pass tie-out;
- every failure has a reason.

- **P2-01** — Bridge / BridgeLine models + `line_key` derivation (stable across quarters) →
  tests.
- **P2-02** — Caption scale → `scale_and_sign` → test.
- **P2-03** — Column → period binding (fiscal-aware) → gold-set delta logged.
- **P2-04** — Headline-bridge selection → table-found ≥95%.
- **P2-05** — Sum tie-out, tolerance max(1, ⌈n/2⌉) units → tests.
- **P2-06** — GAAP anchor tie-out vs XBRL; label-mismatched anchor → *review* → tests.
- **P2-07** — Label memory (issuer + label → category); unmatched → review queue → tests.
- **P2-08** — Taxonomy v2 for credit (versioned file, from spec v0.2) → tests.
- **P2-09** — Persist observations / tie-outs / failures → Postgres integration test.
- **P2-10** — Error analysis on the gold set; re-measure the §6 assumptions → RESULTS.
- **P2-11..13** — Fix the top 3 failure classes (one ticket each) → accuracy delta logged.
- **P2-14** — CI release gate at the exit thresholds → fails below target.

### Phase 3 — Verification ops & change intelligence
**Exit gate:**
- 150 issuers × 8 quarters;
- ≥97% verified-line accuracy on a 100-release gold set;
- alert precision ≥70%;
- review backlog ≤48 h.

- **P3-01** — Verification state + audit log per observation → tests.
- **P3-02** — `footnote review` CLI (queue, source link, approve / fix / reject) → the owner clears
  20 items in under 15 min.
- **P3-03** — Recast detection from observations → recast fixture test.
- **P3-04** — Definition-change diff (added / removed / renamed / recast) → tests.
- **P3-05** — Add-back intensity + recurrence flags → tests.
- **P3-06** — Normalized EBITDA with default policy vN, itemized → tests.
- **P3-07** — Alert generator (rules, deduplication, quotes) → golden-file test.
- **P3-08** — *(Conditional: unmatched-label rate > 10%)* LLM label suggestions via Groq free
  tier; labels only; human confirms → architecture test still forbids LLM imports outside
  `suggest/`.
- **P3-09 [YOU]** — Label the alert sample (true / cosmetic / extraction error) → precision
  report.
- **P3-10** — Extend the gold set to 100 releases (the owner labels 70 more with the CLI) → RESULTS.
- **P3-11** — Expand to 150 issuers + backlog report → coverage report.

### Phase 4 — Product v1 for design partners ($0)
**Exit gate:**
- 3 design partners use it weekly for 4 weeks;
- ≥1 paid pilot (Stripe Payment Link).

- **P4-01** — FastAPI read API + OpenAPI → contract tests.
- **P4-02** — Clerk orgs; tenant tables + RLS; cross-tenant read test fails → test.
- **P4-03** — Web shell on Cloudflare Pages (search, issuer page) → deploys.
- **P4-04** — Bridge history + click-to-source → e2e.
- **P4-05** — Reported vs. normalized + peer add-back comparison → e2e.
- **P4-06** — Watchlists + weekly change digest (Resend free) → test.
- **P4-07** — Excel export (formulas, normalized/reported columns, source comments) → golden
  workbook test.
- **P4-08** — Cloud Run deploy + health + error logging; measure cold start → smoke test +
  report.
- **P4-09** — Warm-up ping *only if* p95 cold start > 2 s → measured.
- **P4-10 [YOU]** — ToS (incl. correction-contribution opt-in), privacy policy, Stripe,
  pricing page → published.
- **P4-11** — Correction submission (opt-in per org, anonymized into the shared record after
  verification) → tests.
- **P4-12** — Public read-only demo on HF Spaces (10 verified issuers) → URL.

### Phase 5 — Commercial scale
**Exit gate:**
- ≥10 paying orgs;
- MRR ≥ projected paid-infra cost;
- security baseline documented.

Split into ≤1-day tickets at phase start:
- customer policy profiles (per-org normalization);
- Credit pack (leverage on reported vs. normalized EBITDA using XBRL debt; `PackSpec`
  defined here);
- Stripe Billing + self-serve signup;
- API keys, rate limits, metering;
- Excel add-in;
- bulk data licence export;
- coverage to ~1,000 issuers;
- observability;
- SOC 2 readiness documents;
- paid migration when a trigger fires.

### Phase 6 — Gated expansions (each needs an ADR + customer pull)

- private credit documents (PDF upload, tenant-private store, compliance certificates);
- comps with licensed market data;
- semantic search (pgvector);
- non-US coverage.

---

## 8. Owner's part — before and during the build

**Before Phase 0 starts:**
- approve the issuer list (P0-02);
- name a second labeler for 10 releases;
- set `SEC_USER_AGENT` (the owner's real name and email) as a GitHub secret.

**During Phase 0:**
- ~8–10 h labelling;
- 8 credit-analyst interviews (script provided);
- 2 analysts to critique the normalization spec;
- confirm the pricing hypothesis afterwards.

**Before Phase 1:** free accounts. Card on file where needed, budget alerts at $1; secrets
shared as environment secrets, never in chat:
- Neon;
- Cloudflare (R2);
- Google Cloud (billing account + budget alert, used from Phase 4).

**Before Phase 4:**
- Clerk, Stripe, Resend, Hugging Face, a domain;
- business entity, ToS/privacy;
- 3–5 design-partner candidates (ideally from the interviewees).

**Ongoing:**
- review CLI time (≈ hours per quarter, per §6);
- alert-precision labelling (~2 h, P3-09);
- 70 more gold labels (P3-10).

---

## 9. Keeping this document honest
- Each phase's exit gate is evidenced in `eval/RESULTS.md` (scorer output, run reports, alert
  precision) before the next phase opens; ICP and spec reviews are evidenced in `docs/discovery/`.
- Ticket status lives in the issue tracker / PRs; this file changes only when scope, gates or
  principles change, with a DECISIONS entry.

## 10. Sources (checked 2026-10-14)
- Sidequest (Node.js/TS): https://docs.sidequestjs.com/introduction/why
- Procrastinate (Python/Postgres queue): https://procrastinate.readthedocs.io
- Groq free-tier limits (gpt-oss-120b): https://benchlm.ai/free-tier/groq ; https://blogs.novita.ai/free-llm-api-comparison-2026/
- Clerk pricing (50K MRU free): https://clerk.com/articles/clerk-pricing-explained
- Hugging Face Spaces runtime (sleep, storage): https://huggingface.co/docs/huggingface_hub/main/guides/manage-spaces ; https://huggingface.co/docs/hub/spaces-overview
- Neon pricing: https://neon.com/pricing
- Cloud Run pricing: https://cloud.google.com/run/pricing
- GitHub Actions billing and scheduled-workflow disabling: https://docs.github.com/en/billing/concepts/product-billing/github-actions ; https://docs.github.com/en/actions/managing-workflow-runs/disabling-and-enabling-a-workflow
- Daloopa data sheets / FAQ ("as reported", renamed lines merged, restatements): https://docs.daloopa.com/docs/data-sheets ; https://docs.daloopa.com/docs/faqs
- Calcbench non-GAAP adjustment studies: https://www.accountingtoday.com/articles/s-p-500-companies-boost-profit-by-stripping-more-items-from-earnings
- Packaging Corp cover-page XBRL (no confirmed ×10⁶ error): https://www.sec.gov/Archives/edgar/data/75677/000095017025028533/R1.htm
