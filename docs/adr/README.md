# Architecture Decision Records

One decision per record. Records are immutable once accepted. To change a decision, write a
new ADR that supersedes the old one, and log the change in [DECISIONS.md](../../DECISIONS.md).
Status values: Proposed, Accepted, Superseded.

| ADR | Decision | Status |
|---|---|---|
| [ADR-005](ADR-005-ingest.md) | Ingest public filings in scheduled batches from EDGAR into a write-once raw store | Accepted |
| [ADR-006](ADR-006-global-vs-tenant-data.md) | Public filing data is global and append-only; customer data is tenant-scoped | Accepted |
| [ADR-007](ADR-007-packs.md) | No "pack" abstraction before Phase 5; when it comes, it is declarative data | Accepted |
| [ADR-008](ADR-008-offline-online.md) | All extraction and normalization runs offline; the online path only reads | Accepted |
| [ADR-009](ADR-009-zero-cost-deploy.md) | $0 infrastructure until first revenue, with migration triggers written in advance | Accepted |

**Retired.** ADR-001 to ADR-004 described the removed PDF → workbook product: target-metric
review triage, the xlsx output format, the 6-tab generator and multi-year company grouping.
They are kept at git tag `v0-extraction` and do not apply to the current direction
(DECISIONS.md, 2026-10-14). Their numbers are not reused.

Sources for all records: [ROADMAP.md](../ROADMAP.md) §4–§6 and DECISIONS.md entries of
2026-10-14 to 2026-10-17.
