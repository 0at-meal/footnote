# Footnote — EBITDA Normalization Specification

> **Version:** v0.1 · **Status:** DRAFT, not frozen. Written 2026-10-17 under P0-13.
> - P0-14: at least 2 interviewed credit analysts critique it
>   ([reviewer brief](discovery/spec-review-brief.md)).
> - It is revised and frozen as v0.2 before Phase 2 opens. See [ROADMAP.md](ROADMAP.md) §3.
>
> Nothing in this document computes a served number until it is frozen. Each frozen version is
> immutable, and results are stored with the version that produced them.
>
> **About the examples.** Every worked example uses a real bridge from the Phase 0 gold set
> (`eval/gold/labels/`, values verified per `verified_by`), cited by accession, line
> (`row_order`) and period. The *category* given to each line is the spec author's
> illustration for review. It is not label memory, it is not a gold label, and nothing
> computes from it.

## 1. Purpose

- **Reported Adjusted EBITDA** is each issuer's own definition. Definitions differ across
  issuers and change over time.
- **Footnote-normalized EBITDA** applies one transparent, versioned policy to every issuer's
  reported bridge. Analysts can then compare issuers like for like and see exactly which
  add-backs were kept, reversed or flagged.
- **A firm can apply its own policy** (customer policy profiles, Phase 5). The default policy
  is a starting point, not a claim about the "right" EBITDA.

## 2. Scope of v0.1

**In scope.**
- The headline EBITDA-type bridge in a US issuer's earnings release (EX-99.1): consolidated,
  in USD, from a GAAP measure (net income, net income attributable to the parent, operating
  income, or income before taxes) to the issuer's headline metric.
- Headline metrics with names other than "Adjusted EBITDA" are included. Gold-set examples:
  "EBITDA As Defined" (TDG), "Adjusted Corporate EBITDA" (HTZ), "Adjusted Property EBITDAR"
  (WYNN) and "Adjusted EBITDA excluding Special Items" (LUMN).

**Out of scope for v0.1.** Each is listed in §12 as an open question:
- segment-level bridges;
- non-USD bridges;
- covenant (credit-agreement) EBITDA;
- pro forma acquired-company EBITDA;
- guidance tables.

## 3. Inputs and terms

A **bridge** is one issuer, one metric and one release. It has **lines** and **periods**
(column headers). Each line has a role:

| Role | Meaning | Normalized? |
|---|---|---|
| `gaap_start` | The GAAP measure the bridge starts from | No. It is the anchor (checked against XBRL) |
| `adjustment` | An add-back or a deduction | **Yes.** It gets a category (§4) and a treatment (§5) |
| `subtotal` | e.g. "EBITDA", "Operating income", "Adjusted Net Income", "Gross Adjustments" | No. Used only for checks |
| `total` | The headline metric: **reported Adjusted EBITDA** | Normalization starts from it |
| `memo` | Shown in the table but not part of the bridge | No |

**Value and contribution.** These follow the gold-label convention (P0-04):
- `value` is the number as shown, in the table's reported scale. Parentheses or a leading
  minus make it negative. A dash is null.
- `sign` is the line's direction in the bridge: +1 if added toward the total, −1 if
  subtracted.
- A line's **contribution** to the total is `sign × value`. The `gaap_start` contribution
  plus all `adjustment` contributions equals the `total`, within the tie-out tolerance of
  max(1, ⌈n/2⌉) units of the reported scale.

Example (top-down layout). THC `0000070318-26-000023`, line 7 "Revenue from contract
termination", `3M-2026-03-31`: value 413, sign −1, so the contribution is −413. The issuer
removes a one-time revenue.

**Quarter.** A 3-month period column. The recurrence rule (§6) uses quarters only. 6-month,
9-month and LTM columns are kept as observations but are not inputs to recurrence.

## 4. Taxonomy (v0.1)

Each adjustment line gets exactly one code. Codes fall into four groups:
- **components**, the parts of EBITDA's own definition;
- **adjustments**, the issuer's non-GAAP add-backs;
- **scope**, items that change what the metric measures;
- **control**, codes that force review.

The seed list in `backend/app/classification/seed_taxonomy.json` (`non_gaap_bridge` items)
and `StandardAddBackCategory` are the starting point. This table supersedes them for
normalization; P2-08 implements it as a versioned file.

### 4.1 Components (part of the definition of EBITDA)

| Code | Category | Includes | Excludes | Gold-set examples (accession, line) |
|---|---|---|---|---|
| `DA` | Depreciation and amortization | D&A in any expense line (split lines are summed); amortization of acquired intangibles | Vehicle or fleet depreciation that the issuer keeps *in* EBITDA, which is never added back | TDG `0001260221-26-000052` l.1 "Depreciation and amortization expense"; CVNA `0001690820-26-000054` l.6–7 "D&A expense in cost of sales / in SG&A"; CAR `0000723612-26-000037` l.3 "Non-vehicle related depreciation and amortization" |
| `INT` | Interest, net | Interest expense, interest income, interest net of capitalized interest | Debt extinguishment (`DEBT`); vehicle or fleet interest kept in EBITDA | WYNN `0001174922-26-000051` l.8 "Interest income", l.9 "Interest expense, net of amounts capitalized"; HTZ `0001657853-26-000045` l.3 "Non-vehicle debt interest, net of interest income" |
| `TAX` | Income taxes | Provision or benefit; the tax effect of other adjustments; "adjustments made to income taxes" | Non-income taxes | CC `0001627223-26-000021` l.11 "Adjustments made to income taxes", l.12 "Provision for (benefit from) income taxes relating to reconciling items", l.17 "All remaining provision for income taxes" |
| `NCI` | Non-controlling interests | Net income attributable to NCI, added back or deducted; EBITDA attributable to NCI | — | CHTR `0001091667-26-000051` l.1 "Plus: Net income attributable to noncontrolling interest"; FUN `0001999001-26-000094` l.16 (deducted, sign −1); BHC `0000885590-26-000051` l.15 "Adjusted EBITDA attributable to noncontrolling interest" |
| `NONOP` | Other non-operating income and expense | Other (income) expense, net; non-operating pension; equity-method results; investment gains and losses | Items with their own code (FX, DERIV, DEBT, DIVEST) when shown separately | LUMN `0000018926-26-000045` l.2 "Total other expense, net"; CC `0001627223-26-000021` l.1 "Non-operating pension and other post-retirement benefit income"; IHRT `0001628280-26-055243` l.5 "Loss on investments, net", l.7 "Equity in loss of nonconsolidated affiliates" |

### 4.2 Adjustments (the issuer's non-GAAP add-backs)

| Code | Category | Includes | Excludes | Gold-set examples |
|---|---|---|---|---|
| `SBC` | Stock-based compensation | Share- or stock-based and "non-cash equity" compensation | Cash bonuses | CHTR `0001091667-26-000027` l.5 "Stock compensation expense"; FUN `0001999001-26-000094` l.7 "Non-cash equity compensation expense" |
| `RESTR` | Restructuring and severance | Restructuring, severance, employee termination, facility exit | Programme costs labelled transformation or modernization (`TRANSFORM`) | IHRT `0001628280-26-033471` l.10 "Restructuring expenses"; FUN `0001999001-26-000094` l.13 "Severance"; CYH `0001193125-26-312454` l.7 "Expense related to employee termination benefits and other restructuring charges" |
| `TRANSFORM` | Transformation, modernization, systems | Business transformation, modernization or simplification, cloud-computing implementation | Restructuring (`RESTR`) when shown separately | LUMN `0000018926-26-000045` l.8 "Modernization and simplification"; CAR `0000723612-26-000037` l.11 "Cloud computing costs"; CYH `0001193125-26-312454` l.8 "Expense from business transformation costs" |
| `IMPAIR` | Impairments and write-downs | Goodwill, intangible and asset impairments; property charges | Losses on sale (`DIVEST`) | BHC `0000885590-26-000051` l.5 "Goodwill impairments"; IHRT `0001628280-26-033471` l.8 "Impairment charges" |
| `MA` | M&A, integration, transaction and separation | Transaction, acquisition, integration, merger, separation and spin costs | Earn-out fair-value changes (`DERIV`) | TDG `0001260221-26-000052` l.5 "Acquisition transaction and integration-related expenses"; LUMN `0000018926-26-000045` l.7 "Transaction and separation costs"; FUN `0001999001-26-000094` l.12 "Costs related to the merger" |
| `LITIG` | Litigation and legal settlements | Litigation, investigation, legal matters, settlements, net of recoveries | Environmental remediation (`ENV`) | CC `0001627223-26-000021` l.9 "Litigation-related charges"; THC `0000070318-26-000023` l.10 "Litigation and investigation costs"; CAR `0000723612-26-000037` l.10 "Legal matters, net" |
| `ENV` | Environmental charges | Remediation and environmental charges | — | CC `0001627223-26-000021` l.10 "Environmental charges" |
| `FX` | Foreign-exchange gains and losses | Remeasurement and transaction FX, cash or non-cash | — | CC `0001627223-26-000010` l.2 "Exchange (gains) losses, net"; FUN `0001999001-26-000094` l.6 "Non-cash foreign currency loss (gain)" |
| `DERIV` | Fair-value changes | Derivatives, warrants, contingent consideration and earn-outs, financial instruments | — | WYNN `0001174922-26-000051` l.10 "Change in derivatives fair value"; HTZ `0001657853-26-000045` l.10 "Change in fair value of Public Warrants", l.6 "Net (gains) losses on financial instruments" |
| `DIVEST` | Gains and losses on disposals | Sale of businesses or assets, disposal groups, retirement of fixed assets, deconsolidation | Impairments (`IMPAIR`) | LUMN `0000018926-26-000045` l.6 "Net gain on sale of business"; FUN `0001999001-26-000094` l.8 "Loss on retirement of fixed assets, net", l.10 "Loss on disposal group"; CC `0001627223-26-000021` l.6 "Gain on sales of assets and businesses, net" |
| `DEBT` | Debt extinguishment and refinancing | Gain or loss on extinguishment, debt financing transactions | Recurring interest (`INT`) | CAR `0000723612-26-000037` l.5 "Early extinguishment of debt"; WYNN `0001174922-26-000051` l.11 "Loss on debt financing transactions" |
| `PREOPEN` | Pre-opening and start-up | Pre-opening and launch costs of new sites | — | WYNN `0001174922-26-000051` l.2 "Pre-opening expenses" |
| `REV` | Revenue-side adjustments | Revenue removed from or added to the metric: contract termination revenue, warrant revenue, cost recoveries shown as revenue | — | THC `0000070318-26-000023` l.7 "Revenue from contract termination"; CVNA `0001690820-26-000054` l.10 "Warrant revenue"; CC `0001627223-26-000021` l.8 "Qualified spend recovery" |
| `SYNERGY` | Pro-forma or run-rate synergies and cost savings | Expected, not-yet-realized savings | Realized costs (other codes) | *None in the gold set; typical of covenant EBITDA (§12)* |
| `OTHER_NR` | Other items the issuer labels non-recurring or "other" | "Other", "Other items", "Other, net" lines that are adjustments | Lines whose footnote names a single category (use that category) | LUMN `0000018926-26-000045` l.9 "Other"; CHTR `0001091667-26-000051` l.6 "Other, net"; TDG `0001260221-26-000052` l.7 "Other, net" |

### 4.3 Scope (items that change what the metric measures)

| Code | Category | Includes | Gold-set examples |
|---|---|---|---|
| `RENT` | Lease and rent add-backs | Rent added back to reach EBITDAR; lease-accounting adjustments | WYNN `0001174922-26-000051` l.5 "Triple-net operating lease rent expense" |
| `CORP` | Corporate costs excluded from a property or segment metric | Corporate expenses added back to reach a property-level figure | WYNN `0001174922-26-000051` l.6 "Corporate expenses and other" |

### 4.4 Control

| Code | Meaning |
|---|---|
| `MIXED` | The label names two or more categories, e.g. THC `0000070318-26-000023` l.9 "Impairment and restructuring charges, and acquisition-related costs" (`IMPAIR`+`RESTR`+`MA`) or CYH `0001193125-26-312454` l.6 "Impairment and (gain) loss on sale of businesses, net" (`IMPAIR`+`DIVEST`). The constituent codes are recorded with the line. |
| `OTHER` | Not yet classified. A new label, or one too ambiguous to classify, e.g. HTZ `0001657853-26-000045` l.4 "Vehicle debt-related charges (b)" (could be `INT`, `DEBT` or neither; footnote (b) must be read). It always goes to review and is never silently accepted. |

### 4.5 Assignment rules

1. A category is assigned by **issuer-scoped label memory** (issuer + normalized label →
   code, P2-07) or by a human reviewer. It is never assigned by an LLM. P3-08 may later
   *suggest* codes for human confirmation.
2. The label decides first. When the label is ambiguous and the issuer's footnote resolves
   it, the footnote decides, and the reviewer records the footnote quote with the decision.
3. A label that names one category plus a residual ("… and other", "… and other related
   charges") gets that category plus the flag `residual_other`. Examples: CZR
   `0001590895-26-000027` l.6 "Transaction costs and other, net" → `MA`; CC
   `0001627223-26-000021` l.3 "Restructuring, asset-related, and other charges" → `RESTR`.
4. A label that names two or more categories gets `MIXED`, with its constituents.
5. Subtotals and totals are never categorized.

## 5. Default policy `footnote-default v0.1` (draft treatments)

Each code has a **treatment**:
- **accept:** the line stays in normalized EBITDA;
- **exclude:** the line's contribution is reversed;
- **flag:** it stays, but is surfaced to the analyst;
- **accept-unless-recurring:** accept, but *exclude* when the recurrence rule (§6) marks the
  category recurring for this issuer.

| Code | Treatment | Rationale (to be tested in P0-14) |
|---|---|---|
| `DA`, `INT`, `TAX` | accept | Definitional components of EBITDA |
| `NCI` | accept | Normalized EBITDA follows the issuer's consolidation choice. Attributable-only EBITDA is a policy option (§12 Q5) |
| `NONOP` | accept | EBITDA is an operating measure; non-operating items sit below it |
| `SBC` | flag | A real, recurring cost; credit practice varies (§12 Q1) |
| `RESTR`, `TRANSFORM`, `MA`, `LITIG`, `ENV` | accept-unless-recurring | Genuinely one-off costs are acceptable; costs that recur every quarter are operating costs |
| `IMPAIR`, `DIVEST`, `DEBT`, `FX`, `DERIV` | accept | Non-cash or non-operating, whether a gain or a loss; gains are reversed by the same line |
| `PREOPEN` | flag | Recurring for a growing operator; judgment needed |
| `REV` | flag | Changes revenue, not cost; direction varies |
| `SYNERGY` | exclude | Not yet realized |
| `RENT`, `CORP` | exclude | Normalized EBITDA is consolidated EBITDA. Add-backs that turn it into EBITDAR or a property-level figure are reversed |
| `OTHER_NR` | flag | Needs judgment, and the footnote usually says what it is |
| `MIXED` | the strictest treatment among its constituents (exclude > accept-unless-recurring > flag > accept), plus the flag `mixed` | Never more lenient than any of its parts |
| `OTHER` | flag + review; normalized EBITDA is **not computed** while any line is `OTHER` | Never silently accepted |

## 6. Recurrence rule (deterministic)

For an issuer, a code *c* and a quarter *q*:
1. Take the issuer's **last 4 fiscal quarters ending at q** (q, q−1, q−2, q−3), by fiscal
   period end date.
2. A quarter **adds back c** if the sum of contributions of the issuer's adjustment lines
   with code *c* in that quarter's 3-month column is **> 0**. `MIXED` lines count toward each
   of their constituents.
3. A quarter's value is **known** when a verified bridge reports a 3-month column for it, from
   that quarter's release or as a comparative column in a later one. Otherwise it is
   **unknown**. A quarter is never derived from LTM or YTD differences in v0.1 (§12 Q8).
4. With *k* = the number of quarters known to add back *c*, and *u* = the number unknown:
   - **recurring** if k ≥ 3;
   - **not recurring** if k + u < 3;
   - **unknown** otherwise. An unknown result never flips a treatment. The line is
     accepted with the flag `recurrence_unknown`.
5. The rule uses the **latest observation** of each quarter. If a later release recasts a
   prior quarter, the recast value is used, and the change is itself a change event (P3-03).

## 7. Computation

```
normalized_ebitda(q) = reported_total(q) − Σ contribution(line, q)   over adjustment lines whose
                                                                   resolved treatment is exclude
```

- The computation runs in the table's reported scale, on as-reported values. Scale is applied
  only on display.
- Every reversal is itemized with its source: accession, line, quote and locator.
- `flag` never changes the number.
- **Not computed** (with an explicit reason, never a guess) when:
  - the bridge fails its sum tie-out (`tieout_failed`);
  - any line is `OTHER` (`unclassified_line`);
  - the scale is unknown (`scale_unknown`).
- Each result records `policy_version` (here `footnote-default v0.1`), the recurrence result
  per code, and every flag.

## 8. Edge cases

| Case | Rule | Gold-set example |
|---|---|---|
| Lines mixing categories | `MIXED` + constituents (§4.5) | THC `0000070318-26-000023` l.9 |
| One category plus residual "other" | that category + `residual_other` | CZR `0001590895-26-000027` l.6 |
| Netted or partial add-backs ("net of insurance recoveries", "a portion of …") | Kept as reported + flag `netted`; never grossed up | BHC `0000885590-26-000051` l.11 "Litigation and other matters, net of insurance recoveries and restitutions" |
| Bridge starts from net income attributable to the parent | The NCI line is `NCI` | CHTR `0001091667-26-000051` l.0–1; WYNN `0001174922-26-000051` l.0–1 |
| Bridge passes through operating income, or is laid out top-down | Contributions use the line's bridge sign, so no special case | THC `0000070318-26-000023` (l.0 → l.6 "Operating income" → l.12); CVNA `0001690820-26-000054` l.4 |
| Bridge passes through another non-GAAP measure | Intermediate measures are `subtotal`; all adjustments above and below count | CC `0001627223-26-000021` l.13 "Adjusted Net Income"; FUN `0001999001-26-000094` l.15 "Modified EBITDA" |
| Two-tier headline (Adjusted EBITDA, then a further adjusted figure) | The `total` is the issuer's headline metric (P0-01 choice); the first tier is a `subtotal` | LUMN `0000018926-26-000045` l.5 "Adjusted EBITDA" → l.10 "Adjusted EBITDA excluding Special Items" |
| Fleet businesses (vehicle D&A and interest kept in EBITDA) | Only "non-vehicle" D&A and interest are `DA` and `INT`; nothing is added back for vehicles | CAR `0000723612-26-000037` l.3; HTZ `0001657853-26-000045` l.2–3 |
| Metric renamed between releases | Same metric if the bridge structure is unchanged; the rename is recorded as a definition-change event (P3-04) | CZR: "Total Adjusted EBITDA" (`0001590895-26-000015` l.8) → "Adjusted EBITDA" (`0001590895-26-000027` l.8) |
| Taxes on adjustments | `TAX` | CC `0001627223-26-000021` l.12 |
| Segment-level or non-USD bridges | Out of scope in v0.1 (§2) | — |

## 9. Worked examples

All values are in the table's reported scale and come from the gold labels. Categories are
illustrative (see the note at the top).

### 9.1 Recurring "non-recurring" items: Chemours (CC), quarter ended 2026-06-30

Sources:
- CC `0001627223-26-000021` (Q2 release): lines 3, 9, 10 and 18, columns `3M-2026-06-30`
  and `3M-2026-03-31`;
- CC `0001627223-26-000010` (Q1 release): the same lines, column `3M-2025-12-31`.

| Quarter (3M ended) | RESTR l.3 | LITIG l.9 | ENV l.10 | Source |
|---|---|---|---|---|
| 2025-09-30 | unknown | unknown | unknown | not reported as a 3-month column in either release |
| 2025-12-31 | 4 | 19 | 20 | `…-26-000010` |
| 2026-03-31 | 13 | 20 | 7 | `…-26-000021` (also in `…-26-000010`) |
| 2026-06-30 | 3 | 225 | 144 | `…-26-000021` |

For each code, k = 3 and u = 1, so the result is **recurring** (k ≥ 3).
- All three are accept-unless-recurring, so all three are **excluded**.
- RESTR also carries `residual_other` (rule 4.5.3).

Reported Adjusted EBITDA (l.18) = **247**.

```
normalized = 247 − (3 + 225 + 144) = 247 − 372 = −125
```

This example shows why §12 Q2 is the most important question in the spec. Under v0.1 defaults,
Chemours' Q2 Adjusted EBITDA of 247 becomes a normalized −125. An analyst might reasonably
treat a large litigation settlement as non-recurring even when litigation costs appear every
quarter.

### 9.2 Recurrence unknown: TransDigm (TDG), quarter ended 2026-06-27

Source: TDG `0001260221-26-000052` l.5 "Acquisition transaction and integration-related
expenses" (`MA`) and l.6 "Non-cash stock and deferred compensation expense" (`SBC`).

- `MA` values:
  - from `…-26-000052`: 35 in `3M-2026-06-27` and 9 in `3M-2025-06-28`;
  - from `…-26-000039`: 19 in `3M-2026-03-28` and 9 in `3M-2025-03-29`.
- The last 4 quarters ending 2026-06-27 are fiscal Q4 2025, Q1 2026, Q2 2026 and Q3 2026.
  Only Q2 (19) and Q3 (35) are known, so k = 2 and u = 2. The result is **unknown**.
- So `MA` is accepted with `recurrence_unknown`. `SBC` 65 is flagged.

```
normalized = reported EBITDA As Defined (l.9) = 1,447   (no exclusions; flags: SBC 65, MA recurrence_unknown)
```

The prior-year comparatives (9, 9) show the item in 4 of the 4 quarters the gold set holds.
Those quarters are not consecutive, so the rule does not use them. Phase 1 history (8
quarters per issuer) resolves cases like this.

### 9.3 EBITDAR to EBITDA: Wynn (WYNN), quarter ended 2026-06-30 (thousands)

Source: WYNN `0001174922-26-000051`, column `3M-2026-06-30`.

| Line | Label | Code | Contribution | Treatment |
|---|---|---|---|---|
| 14 | Adjusted Property EBITDAR (total) | — | 568,309 | — |
| 5 | Triple-net operating lease rent expense | `RENT` | 35,295 | exclude |
| 6 | Corporate expenses and other | `CORP` (+`residual_other`) | 34,209 | exclude |
| 2 | Pre-opening expenses | `PREOPEN` | 9,232 | flag |
| 7 | Stock-based compensation | `SBC` | 16,902 | flag |

```
normalized = 568,309 − 35,295 − 34,209 = 498,805   (flags: PREOPEN 9,232; SBC 16,902; residual_other)
```

The result is a consolidated EBITDA, no longer the issuer's property-level EBITDAR. §12 Q6
asks whether analysts want that.

### 9.4 Gains reversed by the same line: Lumen (LUMN), quarter ended 2026-03-31

Source: LUMN `0000018926-26-000045`, column `3M-2026-03-31`. Headline total: l.10 "Adjusted
EBITDA excluding Special Items" = 849.

| Line | Label | Code | Contribution | Treatment |
|---|---|---|---|---|
| 6 | Net gain on sale of business | `DIVEST` | −596 | accept: the gain stays removed |
| 7 | Transaction and separation costs | `MA` | 53 | accept-unless-recurring → unknown |
| 8 | Modernization and simplification | `TRANSFORM` | 106 | accept-unless-recurring → unknown |
| 9 | Other | `OTHER_NR` | 7 | flag |
| 4 | Stock-based compensation expense | `SBC` | 13 | flag |

The recurrence window ends 2026-03-31, so it runs from Q2 2025 to Q1 2026. Two of its
quarters are known: 3M-2025-06-30, a comparative column in `0000018926-26-000058` (MA 92,
TRANSFORM 41), and 3M-2026-03-31 (53, 106). The Q3 and Q4 2025 releases are not in the
gold set, so k = 2 and u = 2, and both codes come out **unknown**. The prior-year column
3M-2025-03-31 falls outside the window.

```
normalized = 849   (no exclusions; flags: SBC 13, OTHER_NR 7, MA and TRANSFORM recurrence_unknown)
```

### 9.5 Top-down layout and a mixed line: Tenet (THC), quarter ended 2026-03-31

Source: THC `0000070318-26-000023`, column `3M-2026-03-31`. Lines are shown with
income-statement signs, and the bridge sign makes the contribution right:

| Line | Label | Value | Sign | Contribution | Code | Treatment |
|---|---|---|---|---|---|---|
| 7 | Revenue from contract termination | 413 | −1 | −413 | `REV` | flag |
| 9 | Impairment and restructuring charges, and acquisition-related costs | (24) | −1 | +24 | `MIXED` {IMPAIR, RESTR, MA} | strictest = accept-unless-recurring → unknown |
| 10 | Litigation and investigation costs | (27) | −1 | +27 | `LITIG` | accept-unless-recurring → unknown |

```
normalized = reported Adjusted EBITDA (l.12) = 1,162   (flags: REV −413, mixed, recurrence_unknown)
```

### 9.6 Non-controlling interest deducted at the end: Six Flags / FUN, quarter ended 2026-06-28 (thousands)

Source: FUN `0001999001-26-000094`, column `3M-2026-06-28`.
- l.15 "Modified EBITDA" (subtotal) = 268,157.
- l.16 "Net income attributable to non-controlling interests": value 25,084, sign −1, so the
  contribution is −25,084 (`NCI`, accept).
- l.17 "Adjusted EBITDA" = 243,073.
- l.13 "Severance" 16,700 is `RESTR` (accept-unless-recurring, unknown).
- l.7 "Non-cash equity compensation expense" 19,585 is `SBC` (flag).

```
normalized = 243,073   (flags: SBC 19,585; RESTR recurrence_unknown)
```

## 10. Versioning and change control

- **Version format:** `vMAJOR.MINOR`. A treatment or category change bumps MAJOR. A
  clarification that changes no result bumps MINOR.
- **Immutability:** each frozen version is immutable. Every normalized value records
  `policy_version`, and recomputing under a new version creates new results. It never
  overwrites old ones.
- **Policy file (P2-08).** One versioned file per policy:
  - `policy_version`;
  - the code list with definitions;
  - treatment per code;
  - recurrence parameters (window 4, threshold 3);
  - the strictness order for `MIXED`.

  Code and data refer to the version; nothing is hard-coded.
- **Change log:** every change is logged in [DECISIONS.md](../DECISIONS.md) with a rationale.

## 11. Customer policy profiles (Phase 5)

An organization can override, per code:
- the treatment;
- the recurrence parameters.

A profile is a tenant-scoped, versioned policy applied with the same computation (§7).
Results show the default and the profile side by side.

## 12. Open questions for analyst review (P0-14)

1. **SBC.** Should the credit default be *accept*, *exclude* or *flag*?
2. **Recurring "non-recurring" items.** Should a category in ≥3 of the last 4 quarters flip to
   *exclude* by default? Example 9.1 turns Chemours' 247 into −125. Should size or
   materiality matter (e.g. only when the item is > x% of EBITDA)?
3. **Recurrence window.** Is 3 of 4 quarters right? Would 4 of 8 suit seasonal businesses
   better?
4. **Synergies and covenant EBITDA.** How should credit-agreement add-backs (run-rate
   synergies, caps such as "not to exceed 20% of EBITDA") relate to reported bridges? Is a
   covenant-EBITDA view needed in v1?
5. **NCI.** Consolidated EBITDA, or EBITDA attributable to the parent (the borrower group)?
6. **EBITDAR and property-level metrics.** Should normalization always return consolidated
   EBITDA, reversing rent and corporate add-backs (Example 9.3)?
7. **Restructuring vs. transformation.** Is a separate `TRANSFORM` code useful, or is it
   simply restructuring?
8. **Missing quarters.** Should recurrence use quarters derived from LTM or YTD differences?
   For example, Chemours' Q3 2025 litigation is 272 − 19 − 20 − 225 = 8 from the LTM column
   in `…-26-000021`.
9. **`MIXED` lines.** Is "strictest constituent" the right default, or should mixed lines
   always just be flagged?
10. **Revenue-side adjustments (`REV`).** Flag, or reverse by default?
11. **Default policy at all.** Is one published default useful, or does every firm need its
    own profile from day one?
12. **Scope.** Which matters most after v0.1: segment bridges, 10-Q/10-K bridges, or covenant
    EBITDA?
