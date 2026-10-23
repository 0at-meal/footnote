# Market brief: verified EBITDA bridges for credit

> **What this is.** Desk research from public sources, gathered 2026-10-23 by an agent run
> (see [AUTONOMY-LOG.md](../AUTONOMY-LOG.md)). **It is not customer evidence.** Nothing here is
> an interview answer, a review of Footnote, or a statement by any analyst about Footnote.
> The ICP gate (ROADMAP §2) still needs real interviews (P0-12). Figures from third-party
> aggregators are marked *unverified*.

## 1. The problem is documented, large and getting worse

| Evidence | Source |
|---|---|
| S&P's seventh annual add-back study (Apr 2025): add-backs were a **median 28%** of management-adjusted EBITDA at deal inception; median leverage missed forecasts by **2.3x** in year one and **2.6x** in year two | [S&P Global Ratings, 2025-04-17](https://www.spglobal.com/ratings/en/research/articles/250417-addback-levels-remain-high-despite-some-easing-101619461) (summary via search; page returns 403 to fetchers) |
| 2024 edition: add-backs for 2022 deals were **>29%** of projected EBITDA and **almost 55%** of LTM reported EBITDA | [S&P Global Ratings, 2024-03-27](https://www.spglobal.com/ratings/en/research/articles/240327-leveraged-finance-adding-up-ebitda-addback-study-shows-moderate-improvement-in-earnings-projection-accuracy-13045496) |
| Positive correlation between add-back size at inception and the size of management's projection miss | [S&P Global Ratings, 2023-02-16](https://spglobal.com/ratings/en/research/articles/230216-leveraged-finance-fifth-annual-study-of-ebitda-addbacks-finds-management-continues-to-regularly-miss-project-12643170) |
| 72% of S&P 500 companies reported adjusted earnings in 2025. A 2023 study of 200 S&P 500 firms found non-GAAP net income 38% above GAAP, up from 14% the year before | Calcbench / Suffolk University non-GAAP reconciliation studies ([Suffolk](https://www.suffolk.edu/news-features/news/2023/06/06/19/36/wsj-sbs-calcbench-coverage)) |
| The SEC's Dec 2022 non-GAAP C&DI 100.01 update: excluding *normal, recurring cash operating expenses* can be misleading, and an expense that recurs **at irregular intervals** still counts as recurring. Pre-opening costs and legal fees are frequent comment-letter targets | [PwC Viewpoint](https://viewpoint.pwc.com/dt/us/en/pwc/sec_comment_letters/comment_letter_trends_DM/Non_GAAP_measures_main.html); [PLI SEC blog](https://seciblog.pli.edu/?p=2608) |

**Why it matters for the product.** Footnote's recurrence rule (spec §6: a category in ≥3 of
the last 4 quarters is "recurring") puts the SEC's own test into code. The live data
already shows it: of the 50 issuers ingested, the change feed lists every "non-recurring"
add-back that recurs (see the app's *Changes* view).

## 2. What practitioners say today (public forums; old threads, treat as directional)

From public Wall Street Oasis threads ([1](https://www.wallstreetoasis.com/forum/hedge-fund/calculating-ebitda),
[2](https://www.wallstreetoasis.com/forum/investment-banking/need-help-from-credit-lev-fin-fixed-income-analysts),
[3](https://www.wallstreetoasis.com/forums/calculating-ebitda-what-am-i-missing)):
- The standard advice is to **start from the company's own reconciliation in its filings**
  and remove add-backs you disagree with. That is exactly the object Footnote stores.
- Terminal EBITDA (CapIQ, Bloomberg, FactSet) is described as a starting point that you must
  check. Posters say CapIQ recomputes EBITDA from line items and does not fully adjust
  historical LTM figures for non-recurring items.
- Credit work needs the *company's* definition and, separately, the *credit agreement's*
  definition. Covenant EBITDA is out of scope for spec v0.1 (§12 Q4) and is a named Phase 6
  expansion.

Vendor guides on credit spreading ([Crediflow](https://www.crediflow.ai/blog/ebitda-adjustments-credit-analysis),
[Docsumo](https://www.docsumo.com/blog/spreading-financial-statements)) describe the same
workflow: log each adjustment with amount, period, source document and the analyst's
decision, then reconcile adjusted EBITDA back to the spread. Footnote automates the first
three and records the fourth as a policy.

**Gap in this research.** No first-hand, recent analyst reviews of incumbent tools on
non-GAAP bridges were found. G2/Capterra coverage of Daloopa, Calcbench, 9fin and Octus is
thin. The interviews in `docs/discovery/` are the way to get this, and only the owner can
run them.

## 3. Competitors and comparables

| Company | What it does for this job | Signal | Source |
|---|---|---|---|
| **Octus** (ex-Reorg) | Credit news, legal and covenant analysis for sub-IG credit; ~250 analysts; >44,000 customers | **LSEG in talks to buy a controlling stake for $3.5bn** (14 Oct 2026); Permira paid $1.3bn in 2022 | [FStech, 2026-10-14](https://www.fstech.co.uk/fst/LSEG_To_Buy_Finance_Data_Specialist_Octus_For_3_5bn.php) |
| **Daloopa** | Fundamental data "as reported", incl. GAAP-to-non-GAAP lines, for ~5,500 companies. Its own docs say renamed lines are merged into one series and restatements are not shown by default (ROADMAP §1) | $47M Series C, 28 May 2026 (Brighton Park); claims "99.9%" accuracy (no independent audit found) | [Daloopa press release](https://daloopa.com/blog/press-release/47-million-series-c); [FinTech Futures](https://fintechfutures.com/venture-capital-funding/daloopa-banks-47m-series-c-to-scale-data-infrastructure) |
| **Calcbench** | XBRL data plus non-GAAP / KPI extraction from releases; publishes non-GAAP studies | From ~$6,000 a year (*unverified*, third-party site) | [findmymoat](https://www.findmymoat.com/vs/annualreports-com-vs-calcbench); [G2](https://www.g2.com/products/calcbench-xbrl-financial-data-for-g-suite/pricing) |
| **9fin** | Leveraged-finance intelligence platform (news, docs, data) | Raised a Series B (Dec 2024 post; size not confirmed here) | [9fin](https://www.9fin.com/insights/2024-wrap) |
| **Terminals** (CapIQ, FactSet, Bloomberg) | Standardized EBITDA, not the issuer's bridge | Capital IQ Pro ~$13–30k per user per year; FactSet ~$12–40k (*unverified*) | [multiples.vc](https://multiples.vc/compare/pricing) |

**Positioning.** No one above sells *the issuer's own bridge, tied out, point-in-time, with
recasts and definition changes surfaced and a policy-driven normalized number*. Daloopa is
closest on data, and its documented choice to merge renamed lines and hide restatements is
the opposite of what a credit analyst needs. Octus is closest on the buyer and shows what
the buyer pays for credit-specific intelligence.

## 4. Market size (ranges differ by definition)

- Private credit AUM: about **$2.1tn** (Global Market Insights; Houlihan Lokey, Jan 2026)
  to **$3.5tn** (DLA Piper, Q1 2026). Macquarie projects $2.8tn by 2028.
  ([HL](https://cdn.hl.com/pdf/2026/hl-us-private-credit-market-newsletter-january-2026.pdf),
  [DLA Piper](https://www.dlapiper.com/insights/publications/private-credit-pulse/2026/private-credit-pulse-q1-2026),
  [Macquarie](https://www.macquarie.com/at/en/about/company/macquarie-asset-management/insights/outlook/private-credit.html))
- US direct-lending volume: **$247bn** in 2025 (DLA Piper).
- No public source gave a headcount of credit analysts. The bottom-up sizing in the pitch is
  therefore an *assumption* to be replaced by interview data.

## 5. Pricing hypothesis (to test in interviews, not validated)

| Tier | Who | Hypothesis | Anchor |
|---|---|---|---|
| Analyst | Single seat, watchlist + alerts + Excel | $6,000 / seat / year | Calcbench entry (unverified) |
| Desk | Up to 10 seats, custom normalization policy, API | $45,000 / year | Below a Capital IQ seat per user |
| Data licence | Bulk point-in-time history for quant / risk | from $100,000 / year | Octus-style data demand (LSEG deal) |
| Design partner | First 3–5 firms, free 3 months for weekly feedback | $0 → paid pilot | ROADMAP Phase 4 gate |

The ICP pass rule needs ≥3 of the first 8 interviewees to name a price anchor or ask for a
trial before any of this is treated as real.
