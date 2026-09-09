# PROVENANCE.md — Mapping of Old Files to Volume 4 Baseline

> **Purpose:** For every section in the new Volume 4 `spec.md`, `CONSTITUTION.md`, and `plan.md`, this file traces which older document(s) the content was derived from or supersedes. No old file is deleted — this is a reading guide.

---

## Volume 4 `CONSTITUTION.md` — Provenance Map

| Section / Rule | Derived From | Supersedes |
|---|---|---|
| §1 Coding Standards (rules 1–10) | `docs/CONSTITUTION.md` (scaffold `8ee5b497`, 2026-08-10) | Original §1 |
| §1.1 extended to `classification/models.py` | `docs/updates.md` Ticket A.0.1 (`20d18eee`, 2026-08-24) | Original §1.1 (narrower scope) |
| §2 Naming Conventions | `docs/CONSTITUTION.md` (`8ee5b497`) | Original §2 |
| §3 Folder Structure (rules 1–11) | `docs/CONSTITUTION.md` (`8ee5b497`, with additions at `6c198fa6`, `97c83427`, `c6a3f56b`) | Original §3 |
| §3.12 (`classification/models.py` importable downstream) | `docs/updates.md` Ticket A.0.1 (`20d18eee`, 2026-08-24) | Implied isolation boundary |
| §3.13 (`audit_report/` must use `model_compilation_service`) | `docs/issues_charter.md` Step 13 (`017b406a`, 2026-08-26); `docs/fixes.md` §3 | No prior explicit rule — violation was undocumented |
| §3.14 (`footnote/` module boundary) | `docs/fixes.md` §14.1 (`88072dad`, 2026-09-02) | `footnote/` was undefined scope |
| §3.15 (`narrative/` deferred from pipeline) | `docs/fixes.md` §14.2 (`88072dad`, 2026-09-02) | `business_alignment.md` Step G/H (specced but not yet deferred) |
| §4 Tech Stack (rules 1–8) | `docs/CONSTITUTION.md` (`8ee5b497`) | Original §4 |
| §4.9 (default generator is `bridge_generator.py`) | ADR-003 (`763e3656`, 2026-09-01) | `updates.md` Phase A (which made 6-tab default) |
| §5 External Documentation | `docs/CONSTITUTION.md` (`8ee5b497`) | Original §5 |
| §6 Never Do (rules 1–14) | `docs/CONSTITUTION.md` (`8ee5b497`) | Original §6 |
| §6.15 (never use 6-tab as default without ADR update) | ADR-003 (`763e3656`, 2026-09-01) | New |
| §6.16 (never wire `narrative/` without ADR) | `docs/fixes.md` §14.2 (`88072dad`, 2026-09-02) | New |

---

## Volume 4 `spec.md` — Provenance Map

### Feature 1 (Multi-File PDF Upload & Job Queueing)

| Spec Element | Derived From | Supersedes |
|---|---|---|
| Base feature spec | `docs/archive/specs/spec_feature1.md` (original `spec.md`, scaffold) | `spec_feature1.md` |
| Engineering workbook | `docs/workbook/feature-1-ingestion.md` (`513cb466`, 2026-08-12) | N/A (complementary) |
| `workflow_pack` field on JobRecord | `docs/fixes.md` §7.1 (`88072dad`, 2026-09-02) | `target_metric` as primary selector (original `plan.md` §3) |
| `filing_year`, `company_id` on JobRecord | ADR-004 (`763e3656`, 2026-09-01); `docs/archive/refinement.md` Phase 2.1 | N/A (new fields) |
| `model_skip_reason` on JobRecord | `docs/issues_charter.md` Step 11; `docs/fixes.md` §6.1 | N/A (new field) |

### Feature 2 (Layout-Aware Extraction)

| Spec Element | Derived From | Supersedes |
|---|---|---|
| Base feature spec | `docs/archive/specs/spec_feature2.md` | `spec_feature2.md` |
| Engineering workbook | `docs/workbook/feature-2-extraction.md` | N/A |
| `is_reconciliation_candidate` | ADR-001 (`6008d647`, 2026-09-01); `docs/archive/refinement.md` Phase 1.1 | Original full-PDF extraction (Volume 1) |
| `parser_used` field | `docs/issues_charter.md` Ticket 1.3 (`017b406a`, 2026-08-26) | N/A (new field) |
| Y-axis inversion | `docs/issues_charter.md` Ticket 1.2; `docs/fixes.md` §1.2 | Flat Y-mapping in original normalizer (bug) |
| PyMuPDF 0-based indexing | `docs/issues_charter.md` Ticket 1.1; `docs/fixes.md` §1.1 | 1-based indexing (confirmed bug) |
| Confidence bonus for reconciliation tables | `docs/issues_charter.md` Step 6, Tickets 6.1-6.2; `docs/fixes.md` §2.4 | Original scorer (no table-context signal) |

### Feature 3 (Classification & Normalization)

| Spec Element | Derived From | Supersedes |
|---|---|---|
| Base feature spec | `docs/archive/specs/spec_feature3.md` | `spec_feature3.md` |
| Engineering workbook | `docs/workbook/feature-3-classification.md` | N/A |
| Master Financial Taxonomy (60–80 items) | `docs/updates.md` Steps A.1-A.2 (`20d18eee`, 2026-08-24) | 10-item flat seed taxonomy (original `plan.md` §3 FR3) |
| Two-level pipeline (alias first, Groq for unknowns) | `docs/updates.md` Step A.3 (`20d18eee`, 2026-08-24) | Groq-first for all items (original) |
| `StatementType` enum | `docs/updates.md` Ticket A.1.1; `docs/glossary.md` (`6008d647`) | N/A (new) |
| `is_target_metric_candidate_item()` tightening | `docs/issues_charter.md` Ticket 3.2; `docs/fixes.md` §2.2 | Broad keyword fallback in original normalizer |
| `isFlagged` frontend predicate (status-based) | `docs/issues_charter.md` Ticket 3.4; ADR-001 §5 | `confidence_score < 0.95` threshold (original — confirmed bug) |

### Feature 4 (Deterministic Model Generation)

| Spec Element | Derived From | Supersedes |
|---|---|---|
| Base feature spec | `docs/archive/specs/spec_feature4.md` | `spec_feature4.md` |
| Engineering workbook | `docs/workbook/feature-4-model-generation.md` | N/A |
| 2-tab Excel format (Source_Inputs + Reconciliation) | ADR-002 (`763e3656`, 2026-09-01) | `=HYPERLINK()` wrappers (original `plan.md` §3 FR5 — bug fix) |
| `bridge_generator.py` as default for non_gaap_bridge | ADR-003 (`763e3656`, 2026-09-01) | `multi_statement_generator.py` as default (from `updates.md` Phase A — overridden) |
| `debt_schedule_generator.py` for capital_structure | `docs/fixes.md` §7.3 (`88072dad`, 2026-09-02) | N/A (new) |
| Workflow pack routing in job_runner.py | `docs/fixes.md` §7.2 (`88072dad`, 2026-09-02); code `290d62fe` (2026-09-03) | Single-path job_runner (original) |

### Feature 5 (Extraction Review UI)

| Spec Element | Derived From | Supersedes |
|---|---|---|
| Base feature spec | `docs/archive/specs/spec_feature5.md` | `spec_feature5.md` |
| Engineering workbook | `docs/workbook/feature-5-review-ui.md` | N/A |
| `PDF_RENDER_SCALE = 1.5` shared constant | `docs/issues_charter.md` Step 15; `docs/fixes.md` §1.5 | Scale 1.3 in AuditTrailView (confirmed mismatch bug) |
| `getBoundingClientRect()` for canvas size | `docs/issues_charter.md` Step 16; `docs/fixes.md` §1.6 | `clientWidth` (includes CSS padding — confirmed bug) |
| Status-based `isFlagged` predicate | `docs/issues_charter.md` Ticket 3.4; ADR-001 | Score-based threshold (confirmed bug) |
| Auto-lock auto_accepted + matched items | `docs/issues_charter.md` Ticket 3.1; ADR-001 §3.2 | Items shown in review despite being auto-acceptable (bug) |
| Content-hash review item IDs | `docs/issues_charter.md` Step 12; `docs/fixes.md` §4.1 | Sequential `{job_id}_{idx}` IDs (fragile — bug) |

### Feature 6 (Audit Trail Lookup)

| Spec Element | Derived From | Supersedes |
|---|---|---|
| Base feature spec | `docs/archive/specs/spec_feature6.md` | `spec_feature6.md` |
| Engineering workbook | `docs/workbook/feature-6-audit-trail.md` | N/A |
| Export PDF button gating | `docs/issues_charter.md` Ticket 2.1; `docs/fixes.md` §5.1 | Always-active link (confirmed bug — download always failed) |
| Dynamic sheet selector | `docs/issues_charter.md` Ticket 8.1; `docs/fixes.md` §9.3 | Hardcoded `["Reconciliation", "Source_Inputs"]` |
| Scale fix + canvas fix | Same as Feature 5 above | Same bugs as Feature 5 |

### Feature 7 (Cross-Year Drift Detection)

| Spec Element | Derived From | Supersedes |
|---|---|---|
| Base feature spec | `docs/archive/specs/spec_feature7.md` | `spec_feature7.md` |
| Engineering workbook | `docs/workbook/feature-7-drift-detection.md` | N/A |
| Single drift route | `docs/fixes.md` §10.1 | Duplicate routes (confirmed bug) |
| Semantic drift (future) | `docs/business_alignment.md` §2.3 | Not yet specified — see OPEN_QUESTIONS OQ-3 |

### Feature 8 (Audit Report Export)

| Spec Element | Derived From | Supersedes |
|---|---|---|
| Base feature spec | `docs/archive/specs/spec_feature8.md` | `spec_feature8.md` |
| Engineering workbook | `docs/workbook/feature-8-audit-report.md` | N/A |
| Isolation via `model_compilation_service` | `docs/issues_charter.md` Step 13; `docs/fixes.md` §3 | Direct imports from `excel_export/` (confirmed isolation violation) |
| Route normalization | `docs/fixes.md` §12 | `/api/` prefix inconsistency (confirmed bug) |

### Feature 9 (Eval Harness — Deferred)

| Spec Element | Derived From | Supersedes |
|---|---|---|
| Full feature spec | `docs/spec_feature9.md` (was `spec.md`) | `spec.md` (renamed `6008d647`) |
| Deferral decision | `docs/business_alignment.md` §1.1 (`54aea539`, 2026-08-29); `docs/plan.md` deferral note (`6008d647`) | Active Phase 5 in original `plan.md` |

### Feature 10 (Workflow Pack 2: Capital Structure)

| Spec Element | Derived From | Supersedes |
|---|---|---|
| Feature specification | `docs/fixes.md` §7, §14.1 (`88072dad`, 2026-09-02) | Orphaned `footnote/` module (was unlinked to pipeline) |
| Business case | `docs/business_alignment.md` §3.1, Steps E, F | N/A |
| Code implementation | Commit `2378d0a1` (2026-09-03) | N/A |

### Feature 11 (EDGAR Integration — Future)

| Spec Element | Derived From | Supersedes |
|---|---|---|
| Feature concept | `docs/business_alignment.md` §3.2, Step D | N/A — no prior requirement |

---

## Archived Files — What Each One Was

| File | Role | Status |
|---|---|---|
| `docs/archive/specs/spec_feature1.md` | Original Feature 1 spec (scaffold) | Superseded by `spec.md` §4.F1 |
| `docs/archive/specs/spec_feature2.md` | Original Feature 2 spec | Superseded by `spec.md` §4.F2 |
| `docs/archive/specs/spec_feature3.md` | Original Feature 3 spec | Superseded by `spec.md` §4.F3 |
| `docs/archive/specs/spec_feature4.md` | Original Feature 4 spec | Superseded by `spec.md` §4.F4 |
| `docs/archive/specs/spec_feature5.md` | Original Feature 5 spec | Superseded by `spec.md` §4.F5 |
| `docs/archive/specs/spec_feature6.md` | Original Feature 6 spec | Superseded by `spec.md` §4.F6 |
| `docs/archive/specs/spec_feature7.md` | Original Feature 7 spec | Superseded by `spec.md` §4.F7 |
| `docs/archive/specs/spec_feature8.md` | Original Feature 8 spec | Superseded by `spec.md` §4.F8 |
| `docs/spec_feature9.md` | Feature 9 eval harness spec (still active reference; deferred) | Active reference (deferred, not superseded) |
| `docs/archive/refinement.md` | Phase 0/1/2 refinement roadmap — all tickets complete | Historical reference — superseded by plan.md phases |
| `docs/archive/proposed_changes.md` | Volume 2 proposal for 6-tab multi-statement generator | SUPERSEDED by ADR-003 (6-tab frozen) |
| `docs/archive/README.md` | Archive folder readme | Informational |
| `docs/updates.md` | Volume 2 update doc — Phase A–E architecture decisions | Partially superseded: Master Taxonomy (A.1-A.2) is implemented; 6-tab default (A) is superseded by ADR-003 |
| `docs/business_alignment.md` | Business alignment diagnosis and Steps A–K roadmap | Partially active: Steps A–C mostly addressed; Steps D–K are future |
| `docs/issues_charter.md` | 34-bug issues implementation charter (Steps 1–20) | Active — remediation phase source document |
| `docs/fixes.md` | Comprehensive audit + remediation plan (2026-09-02) | Active — authoritative remediation guide |
| `docs/explainer.md` | Architectural onboarding reference (as of 2026-09-02) | Active — documentation |
| `docs/debugging.md` | Classification debugging notes | Active — reference for classification behavior |
| `docs/glossary.md` | Term definitions | Active |
| `docs/implementation-loop.md` | Standard development loop (Ticket → Step → Phase) | Active |
| `docs/adr/ADR-001-target-metric-scoped-review.md` | Scoped extraction & review triage — Implemented | Active ADR |
| `docs/adr/ADR-002-xlsx-output-format.md` | Excel output format — Implemented | Active ADR |
| `docs/adr/ADR-003-6tab-generator-freeze.md` | 6-tab generator frozen as beta | Active ADR (guard rail) |
| `docs/adr/ADR-004-multi-year-company-architecture.md` | Multi-year company grouping — Implemented | Active ADR |
| `docs/workbook/feature-1-ingestion.md` | Engineering workbook Feature 1 | Active reference |
| `docs/workbook/feature-2-extraction.md` | Engineering workbook Feature 2 | Active reference |
| `docs/workbook/feature-3-classification.md` | Engineering workbook Feature 3 | Active reference |
| `docs/workbook/feature-4-model-generation.md` | Engineering workbook Feature 4 | Active reference |
| `docs/workbook/feature-5-review-ui.md` | Engineering workbook Feature 5 | Active reference |
| `docs/workbook/feature-6-audit-trail.md` | Engineering workbook Feature 6 | Active reference |
| `docs/workbook/feature-7-drift-detection.md` | Engineering workbook Feature 7 | Active reference |
| `docs/workbook/feature-8-audit-report.md` | Engineering workbook Feature 8 | Active reference |
| `docs/_archive/fixes_implementation.md` | Implementation notes (formerly root-level) | Archived per OQ-10 — 14-step implementation log from 2026-09-03 sprint |
| `eval/README.md` | Eval harness freeze notice | Active |
| `eval/reports/evaluation_report.md` | Evaluation run report | Active reference |
| `frontend/README.md` | Frontend setup README | Active |

---

## Key Supersession Events (Chronological)

1. **2026-08-24 (`20d18eee`)**: `updates.md` attempted to make 6-tab generator the default. Superseded by ADR-003 (2026-09-01).
2. **2026-09-01 (`6008d647`)**: `spec.md` renamed to `spec_feature9.md`. Original `spec.md` is now `docs/archive/specs/spec_feature9.md`... wait — `spec.md` was the Volume 1 top-level spec, renamed to `spec_feature9.md` to distinguish it as "the eval harness spec." The 8 feature specs were always `spec_feature{N}.md` in `docs/archive/specs/`.
3. **2026-09-01 (`763e3656`)**: `refinement.md` archived; `proposed_changes.md` archived. ADRs 002–004 formally recorded.
4. **2026-09-02 (`88072dad`)**: `fixes.md` established as the authoritative remediation guide superseding scattered issue tracking.
