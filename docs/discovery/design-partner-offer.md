# Design-partner offer and path to the first paid pilot

> For the owner to send. Nothing here has been sent, and no one has agreed to it. Prices are
> the hypotheses in `docs/research/market.md` §5. Test them in interviews (ICP pass rule,
> ROADMAP §2) before you quote them as firm.

## 1. The offer (paste into a follow-up after a good interview)

> Thanks again for the time on [date]. You said [their words about rebuilding bridges or
> tracking add-backs]. We now run this on 50 leveraged issuers across 8 quarters. Every
> bridge ties out to the filing, and restatements and definition changes are flagged.
>
> We are taking **3 design partners** for 12 weeks:
> - **You get:** the app for your team, alerts on your watchlist (send me up to 25 tickers
>   and we add any we don't cover), Excel export, and your own add-back policy applied
>   across the universe.
> - **We ask:** a 20-minute call every two weeks, and a note when a number or category
>   looks wrong.
> - **After 12 weeks:** if it saves your team time, a paid pilot at [$__] for [n] seats. If
>   not, you keep the export and we part as friends.
>
> Here is your watchlist issuer [ticker] as an example: [one recast or recurring
> add-back from the demo, with its sec.gov link].

Before sending, pick the example from the demo's *Changes* view for an issuer the person
covers. A real change in a name they know is the strongest proof we have.

## 2. Pilot terms to put in writing (one page; have a lawyer review before signing)

| Term | Proposal |
|---|---|
| Scope | Read access to the Footnote app and Excel export for named users; watchlist alerts |
| Term | 3 months, then month to month |
| Fee | [$__] per month, invoiced; or free for design partners for the first 12 weeks |
| Data | Public SEC filings only. No customer data is uploaded in the pilot |
| Accuracy | Internal figures, not a warranty; every number links to its source filing |
| Feedback use | Corrections the partner submits may improve the shared record, anonymized (P4-11, P4-10) |
| Exit | Either side, 30 days' notice; the partner keeps exported files |

A paid pilot needs, in order: a business entity, a bank account, invoicing or a Stripe
Payment Link, and the ToS and privacy policy (P4-10). These are the owner's steps; the
product does not block them.

## 3. Weekly plan from the pitch to the first paid pilot (targets, not results)

| Week | Owner action | Evidence in the repo |
|---|---|---|
| 1 | 40 outreach messages (`recruiting.md`); book 5 calls | `tracker.md` |
| 2 | 5 interviews, scored the same day | `interviews/I-01..05` |
| 3 | 3 more interviews; spec brief to 2 who said yes to T4 | ICP pass/fail in `tracker.md`; `spec-feedback/` |
| 4 | Send this offer to every interviewee who passed A and B | DECISIONS entry |
| 5–6 | Confirm the top 100 categories with `review export/apply` (about 40 min) | label memory `source=human` |
| 6–8 | 3 design partners onboarded; set up the ingest workflow secret | `.github/workflows/ingest.yml` green |
| 12 | First paid pilot signed | Phase 4 gate row "≥1 paid pilot" |

## 4. What the owner can now do in minutes instead of hours

| Task | Command | Time |
|---|---|---|
| Confirm categories | `python -m app.pipeline.cli review export ../review/category-queue.csv`, fill `decision`, then `... review apply ... --reviewer "Name"` | ~20 s per label; ordered by impact |
| Weekly alert for a prospect | `python -m app.pipeline.cli digest --tickers CC CZR --since 2026-10-16 --out digest.html` | 1 min |
| Refresh the data | `python -m app.pipeline.cli ingest` (or the scheduled workflow) | minutes, cached |
| Refresh the demo | `python -m app.pipeline.cli export`, then republish | minutes |
