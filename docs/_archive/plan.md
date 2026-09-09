# Footnote — plan.md (Volume 4)

> **Version:** 4.0 — Re-baselined 2026-09-09  
> **Governed by:** `CONSTITUTION.md` (Volume 4). On conflict, the Constitution wins.  
> **Provenance:** Derived from `docs/plan.md` (`8ee5b497` initial, `6008d647` last updated 2026-09-01), updated with `docs/fixes.md` (2026-09-02) and `docs/business_alignment.md` (2026-08-29) decisions.

---

## 1. Goals

### 1.1 Functional Requirements

| ID | Requirement |
|---|---|
| FR1 | Accept multi-file PDF uploads with workflow_pack selection and queue for extraction. |
| FR2 | Parse PDFs and extract line items, preserving multi-level headers, footnote references, exact page/bbox coordinates. |
| FR3 | Classify extracted line items against the 60–80 item Master Financial Taxonomy; two-level pipeline (deterministic alias match first, Groq for unknowns only). |
| FR4 | Detect when a company redefines or renames a metric year-over-year and link the new definition to its historical baseline. |
| FR5 | Generate a native `.xlsx` workbook where every derived value is a real Excel formula. |
| FR6 | Bind provenance metadata (page, bbox, source file) to every generated cell. |
| FR7 | Provide a side-by-side review UI; default to showing only genuinely uncertain items (status-based filter). |
| FR8 | Allow a user to select any cell and retrieve its full source chain. |
| FR9 | Produce a downloadable, human-readable audit report (PDF). |
| FR10 | Route extraction, generation, and output format by workflow_pack at upload time. |

### 1.2 Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR1 | Identical input filings shall always produce identical formulas and structure. |
| NFR2 | 100% of generated numeric cells shall be traceable to a source location or explicitly marked as a manual hardcode. |
| NFR3 | A single 200-page 10-K shall complete extraction and model generation in under 5 minutes on local/free-tier compute. |
| NFR4 | The system shall run within free-tier or local-machine resource limits for MVP. |
| NFR5 | The architecture shall support a fully local/offline inference path (design principle, not MVP-enforced). |
| NFR6 | Adding a new workflow pack shall not require re-architecting the extraction or formula-generation layers. |
| NFR7 | Cross-year drift history shall survive a backend restart. |

### 1.3 Locked Decisions

| Decision | Value |
|---|---|
| Phase 1 workflow pack | `non_gaap_bridge` (Adjusted EBITDA) |
| Extraction execution environment | Local machine |
| LLM classifier provider | Groq API, `openai/gpt-oss-120b` |
| Excel output (non_gaap_bridge) | 2-tab: Source_Inputs + Reconciliation (ADR-002, ADR-003) |
| 6-tab generator | Beta/legacy only — frozen (ADR-003) |
| Eval harness | Frozen pending pilot client |

---

## 2. Tech Stack

| Layer | Choice |
|---|---|
| Backend framework | FastAPI |
| PDF layout parsing | Docling (≥2GB RAM — local only) |
| PDF coordinate utility | PyMuPDF |
| LLM (classification only) | Groq API, `openai/gpt-oss-120b`. Free tier: 30 RPM / 1,000 RPD / 8,000 TPM / 200,000 TPD |
| Formula engine | Custom Python module, deterministic |
| Excel generation | xlsxwriter (new workbooks only) |
| Graph/state (drift tracking) | NetworkX + SQLite/JSON persistence |
| Frontend framework | React 19 + TypeScript |
| PDF rendering (frontend) | PDF.js |
| Audit report export | ReportLab + WeasyPrint |
| Testing/eval | Pytest, vitest |
| CI/CD | GitHub Actions (deferred — Phase 5 frozen) |
| Docs | Maintained in `docs/` |

---

## 3. Features & Status

| # | Feature | Status | Phase |
|---|---|---|---|
| F1 | Multi-File PDF Upload & Job Queueing | ✅ Complete (+ workflow_pack extension) | Phase 1 + Fixes |
| F2 | Layout-Aware Extraction | ✅ Complete (+ bbox fix, Y-inversion fix, parser_used field) | Phase 1 + Fixes |
| F3 | Classification & Normalization | ✅ Complete (+ Master Taxonomy, two-level pipeline) | Phase 2 + Volume 2 |
| F4 | Deterministic Model Generation | ✅ Complete (non_gaap_bridge: bridge_generator.py; capital_structure: debt_schedule_generator.py) | Phase 2 + Fixes |
| F5 | Extraction Review UI | ✅ Complete (+ status-based filter, pre-locked auto-accepted, content-hash IDs, scale fix) | Phase 3 + Fixes |
| F6 | Audit Trail Lookup | ✅ Complete (+ model_ready gating, dynamic sheet selector, refresh, scale fix) | Phase 3 + Fixes |
| F7 | Cross-Year Drift Detection | ✅ Complete (+ duplicate route fix; semantic drift remains open question OQ-3) | Phase 4 |
| F8 | Audit Report Export | ✅ Complete (+ isolation fix, route normalization) | Phase 4 + Fixes |
| F9 | Evaluation Harness | ⏸ FROZEN — corpus does not exist. No investment until pilot client confirms. | Phase 5 — deferred |
| F10 | Workflow Pack 2: Capital Structure | ✅ Wired (footnote/ module connected to capital_structure pack) | Fixes §14.1 |
| F11 | EDGAR Direct Integration | ➖ Not started. Specified in business_alignment.md §3.2 | Future |
| F12 | MD&A Delta Tracking | ⏸ Deferred — narrative/ module exists but NOT wired to pipeline | Future |
| F13 | Risk Factor Redline Tracking | ⏸ Deferred — narrative/ module exists but NOT wired | Future |

---

## 4. Phased Delivery — Current Status

> **Status as of 2026-09-09:** All original Phases 1–4 are complete. Refinement Phases 0/1/2 are complete. Workflow pack architecture and fixes have been applied (2026-09-03 commits). Phase 5 is frozen. The active work is the **Remediation Phase** — fixing the 34+ open bugs before any new feature work.

### Phase 1 — Ingestion Pipeline ✅ COMPLETE
Delivers F1, F2 (complete).

### Phase 2 — Core Trust Loop ✅ COMPLETE
Delivers F3, F4 (complete, 2-tab generator path).

### Phase 3 — Human Trust Layer ✅ COMPLETE
Delivers F5, F6 (complete).

### Phase 4 — Extensibility & Compliance Output ✅ COMPLETE
Delivers F7, F8 (complete).

### Refinement Phase 0 — Unblock Core Loop ✅ COMPLETE
Auto-accept gating, model generation API, frontend download wiring.

### Refinement Phase 1 — Business Model Alignment ✅ COMPLETE
Filtered extraction to reconciliation tables; scoped review UI to flagged items; redesigned Excel to 2-tab banker format; fixed audit trail empty state.

### Refinement Phase 2 — Multi-Year Company Architecture ✅ COMPLETE
CompanyRecord, filing_year, multi-year generator, company API, drift integration.

### Remediation Phase — Fix Open Bugs (ACTIVE)

> This phase must be fully complete before any new feature (F11, F12, F13) is started.

**Priority order per `docs/fixes.md` §§1-13:**

| Priority | Group | Key Issues |
|---|---|---|
| P0 | Core Correctness | PyMuPDF bbox 1-based index bug; Docling Y-axis inversion; PDF render scale mismatch; canvas `clientWidth` bug |
| P0 | Review Queue UX | Review queue overcrowded (`isFlagged` predicate fix — ✅ done in code); auto-lock auto_accepted+matched (verify complete); `is_target_metric_candidate_item()` tightening |
| P0 | Isolation | `audit_report/compiler.py` isolation violation (verify `model_compilation_service.py` is used correctly) |
| P1 | ID Stability | Content-hash review IDs replacing sequential IDs |
| P1 | Audit PDF | Export button gating on `model_ready`; empty state guidance |
| P1 | Pipeline Visibility | `model_skip_reason` populated and surfaced in UI |
| P2 | UX Polish | Inline errors, progress pulse, dynamic sheet selector, target metric detection |
| P2 | Code Quality | Deduplicate `_parse_numeric_value()`; fix DI patterns in `drift/`, `narrative/`, `excel_export/` |
| P3 | Health Check | `db_ok` logic inversion (✅ fixed at `7a256125`) |
| P3 | Route Normalization | Duplicate drift routes (verify after `1784de73`); `/api/` prefix inconsistency |

### Phase 5 — Validation & Hardening ⏸ DEFERRED
Delivers F9 (eval harness). Frozen pending pilot client confirmation.

### Future Phases (require explicit ADR + pilot client validation)
- Phase 6: EDGAR Direct Integration (F11)
- Phase 7: Narrative Intelligence (F12, F13) — after `narrative/` is validated out of pipeline deferral

---

## 5. Technical Constraints

- Docling requires ≥2GB RAM — extraction runs on local machine, not hosted free tier.
- xlsxwriter creates new workbooks only — every regeneration is from scratch.
- Groq free tier for `openai/gpt-oss-120b`: 30 RPM / 1,000 RPD / 8,000 TPM / 200,000 TPD. Token usage dramatically reduced by filtering to reconciliation tables before dispatch.
- Groq serves open-source models only — no proprietary model assumptions in prompts.
- LLM API calls leave the local environment — true data-privacy requires local Ollama (documented path, not enforced at MVP).
- MVP is single-user, single-session — no auth, no multi-tenancy.

---

## 6. Resolved Decisions (Formerly Open Questions)

All 10 ambiguous architectural questions identified during the Volume 4 re-baseline have been formally resolved and documented in `docs/_archive/OPEN_QUESTIONS.md`. Summary of resolved baseline decisions:

| # | Topic | Baselined Decision | Status |
|---|---|---|---|
| OQ-1 | Legacy Jobs Workflow Pack | Default to `non_gaap_bridge`; preserve historical artifacts on disk | ✅ Resolved |
| OQ-2 | Role of `target_metric` | Automatically derived from `workflow_pack`; optional override in advanced UI | ✅ Resolved |
| OQ-3 | Semantic Drift Detection | Deterministic exact match + user-confirmed cosmetic relabeling (`mark-relabeled`) | ✅ Resolved |
| OQ-4 | `narrative/` Re-evaluation Gate | Strict gate: numeric pipeline verified on 3 diverse 10-K test filings | ✅ Resolved |
| OQ-5 | EDGAR Integration Priority | Post-pilot (Phase 6); pilot proceeds with drag-and-drop PDF upload | ✅ Resolved |
| OQ-6 | `cash_conversion` Workflow Pack | Freeze as "under specification"; disable in UI; return skip reason in runner | ✅ Resolved |
| OQ-7 | Excel Numeric Formatting | 0 decimals for bridge amounts (`$#,##0`), 2 for EPS/per-share | ✅ Resolved |
| OQ-8 | 6-Tab Generator Fate | Decouple from pipeline (comply with ADR-003); retain as explicit company export | ✅ Resolved |
| OQ-9 | Health Check Logic | Verified as correct: directory write and SQLite check cleanly decoupled | ✅ Resolved |
| OQ-10 | `fixes_implementation.md` | Archived to `docs/_archive/fixes_implementation.md` | ✅ Resolved |
