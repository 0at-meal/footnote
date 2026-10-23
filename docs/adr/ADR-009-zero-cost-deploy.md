# ADR-009: $0 infrastructure until first revenue, with migration triggers written in advance

- **Status:** Accepted
- **Date:** 2026-10-17 (decision taken 2026-10-14, DECISIONS.md; ROADMAP §6)
- **Deciders:** owner; drafted under P0-15
- **Phase introduced:** 1 (storage, cron); 4 (hosting, auth, payments)

## Context

The owner's constraint is strict: no infrastructure spend before the first paying customer.
The workload is bursty: quarterly earnings peaks, small daily runs and a small read API.
Free tiers change, so the limits below were checked on 2026-10-14 (ROADMAP §1, §10) and must
be re-checked before each phase that adopts a service.

## Decision

| Need | Service (free tier) | Phase |
|---|---|---|
| Scheduled ingest | GitHub Actions cron, private repo (2,000 min/month) | 1 |
| Raw documents | Cloudflare R2 (10 GB) | 1 |
| Database | Neon Postgres free (0.5 GB, 100 CU-h/month, scale-to-zero) | 1 |
| Read API | Google Cloud Run (idle instances not billed; never `min-instances`) | 4 |
| Web app | Cloudflare Pages | 4 |
| Auth and orgs | Clerk (50K monthly retained users) | 4 |
| Email digests | Resend free | 4 |
| Payments | Stripe Payment Links (fees only per transaction) | 4 |
| Public demo only | Hugging Face Spaces (sleeps after 48 h; not production) | 4 |

Rules:
- A card is on file only where a provider requires one, with a **$1 budget alert**.
- Secrets live in environment or GitHub secrets, never in the repository or chat.

**Migration triggers** (ROADMAP §6). When one fires, record it in DECISIONS and act:
- Neon storage > 400 MB or > 80 CU-h/month → Neon Launch;
- Cloud Run free tier exceeded → budget alert, then review;
- cron > 1,500 min/month → Cloud Run Jobs + Cloud Scheduler;
- first enterprise isolation request → new ADR (ADR-006).

## Consequences

- The design avoids always-on processes: batch jobs, scale-to-zero, a database that sleeps
  (ADR-005, ADR-008).
- Cold starts and Neon wake-ups are accepted, measured and mitigated only if needed (P4-08,
  P4-09).
- Usage per run (minutes, CU-hours) is logged so a trigger is seen before it is crossed.
- Free-tier terms are a dependency risk. Each service has a named paid step or fallback.

## Alternatives rejected

- **HF Spaces as the production backend:** it sleeps after 48 h and its disk is not
  persistent (DECISIONS 2026-10-14).
- **Paid managed services from day one:** they break the owner's constraint before there is
  revenue.
