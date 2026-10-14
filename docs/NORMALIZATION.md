# Footnote — EBITDA Normalization Specification

> **Version:** v0.1 (skeleton) · **Status:** DRAFT, not frozen. It is filled in under ticket
> P0-13, critiqued by at least 2 interviewed credit analysts (P0-14), and frozen as v0.2 before
> Phase 2 opens. See [ROADMAP.md](ROADMAP.md) §3.
>
> Nothing in this document is used to compute a served number until it is frozen. Each
> frozen version is immutable; results are stored with the version that produced them.

## 1. Purpose

- **Reported Adjusted EBITDA** is each issuer's own definition. Definitions differ across
  issuers and change over time.
- **Footnote-normalized EBITDA** applies one transparent, versioned policy to every issuer's
  reported bridge. Credit analysts can then compare issuers on a like-for-like basis and see
  exactly which add-backs were accepted or reversed.
- **Firms can apply their own policy** (customer policy profiles, Phase 5).

## 2. Inputs

- **Bridge lines:** a verified bridge for one issuer, one metric, one period. Each line has its
  as-reported label, value, scale, sign and source locator (accession, XPath, quote).
- **Category:** each line's add-back category (§3), assigned by issuer-scoped label memory or
  human review. It is never assigned by an LLM.

## 3. Add-back taxonomy (draft)

Starting point: `backend/app/classification/seed_taxonomy.json` (non-GAAP items) and
`StandardAddBackCategory`. The draft category list for credit:

| Code | Category | Examples |
|---|---|---|
| `DA` | Depreciation & amortization (incl. acquired-intangible amortization) | |
| `INT` | Interest, net | |
| `TAX` | Income taxes | |
| `SBC` | Stock-based compensation | |
| `RESTR` | Restructuring, severance, facility exit | |
| `IMPAIR` | Impairments and write-downs | |
| `MA` | M&A, integration, transaction costs | |
| `LITIG` | Litigation and settlements | |
| `FX` | Foreign-exchange gains/losses | |
| `DERIV` | Fair-value changes (derivatives, contingent consideration, earn-outs) | |
| `DIVEST` | Gains/losses on divestitures and asset sales | |
| `DEBT` | Debt extinguishment / refinancing costs | |
| `SYNERGY` | Pro-forma / run-rate synergies and cost savings | |
| `OTHER_NR` | Other items labelled non-recurring | |
| `OTHER` | Unclassified (forces review) | |

*To complete in P0-13: precise definitions, inclusion and exclusion rules, and boundary
examples taken from the gold set.*

## 4. Default policy (draft treatments)

Each category gets a treatment:
- **accept:** the add-back stays in normalized EBITDA;
- **exclude:** the add-back is reversed;
- **flag:** it stays, but is surfaced to the analyst.

| Category | Draft default | Rationale (to be validated in interviews) |
|---|---|---|
| `DA`, `INT`, `TAX` | accept | Definitional components of EBITDA |
| `SBC` | flag | A real cost; treatment varies by firm |
| `RESTR`, `IMPAIR`, `MA`, `LITIG`, `DIVEST`, `DEBT`, `FX`, `DERIV` | accept, unless *recurring* (§5) → exclude | Genuinely non-recurring items are acceptable |
| `SYNERGY` | exclude | Not yet realized |
| `OTHER_NR` | flag | Needs judgment |
| `OTHER` | flag + review | Never silently accepted |

## 5. Recurrence rule (deterministic)

A category that is added back in ≥3 of the issuer's last 4 reported quarters is marked
**recurring**. *To decide in P0-13:* whether recurring items flip to *exclude* by default.

## 6. Computation

```
normalized_ebitda = reported_adjusted_ebitda − Σ value(line) for lines whose treatment = exclude
```

- Every reversal is itemized with its source line.
- `flag` never changes the number.
- When the reported total and the sum of its lines disagree (a failed tie-out), normalized
  EBITDA is **not computed**. The bridge carries a reason instead.

## 7. Edge cases (to specify in P0-13)

- lines that mix categories → `OTHER` + flag;
- partial add-backs ("a portion of …") → kept as reported + flag;
- bridges starting from operating income or income before taxes instead of net income;
- segment-level or non-USD bridges;
- add-backs presented net of tax;
- a metric renamed between periods (definition change, not a new metric).

## 8. Versioning and change control

- **Version format:** `vMAJOR.MINOR`. A treatment or category change bumps MAJOR; a
  clarification bumps MINOR.
- **Immutability:** each frozen version is immutable. Every normalized value records
  `policy_version`.
- **Change log:** changes are logged in [DECISIONS.md](../DECISIONS.md) with a rationale.

## 9. Customer policy profiles (Phase 5)

An organisation can override per-category treatments. A profile is stored as a tenant-scoped,
versioned policy and applied with the same computation (§6).

## 10. Open questions for analyst review (P0-14)

1. Should SBC default to *accept* or *exclude* for credit?
2. Should recurring "non-recurring" items flip to *exclude* automatically?
3. How should synergies credited under a credit agreement be handled, versus reported
   synergies?
4. Is a single default policy useful, or will every firm need its own profile from day one?
