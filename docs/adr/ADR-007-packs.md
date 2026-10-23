# ADR-007: No "pack" abstraction before Phase 5; when it comes, it is declarative data

- **Status:** Accepted
- **Date:** 2026-10-17 (decision taken 2026-10-14, ROADMAP §1.1 and §7 Phase 5)
- **Deciders:** owner; drafted under P0-15
- **Phase introduced:** 5 (Credit pack)

## Context

The removed product had "footnote packs" with xlsx templates. An external report proposed a
`PackSpec` before Phase 1, and a YAML pack DSL. A pack would bundle, for one user segment
(e.g. credit), the metrics derived from the core data, the alerts and the exports. Today
there is one segment and no derived metrics beyond normalized EBITDA.

## Decision

1. **No pack abstraction, interface or registry before Phase 5.** Phases 1–4 build the
   core data asset (bridges, tie-outs, normalization, change intelligence) for the credit
   persona directly.
2. **When the Credit pack is built (Phase 5), its `PackSpec` is declarative data:**
   - the metrics it derives from core tables, e.g. leverage on reported vs. normalized
     EBITDA using XBRL debt;
   - the alert rules it enables;
   - the export columns.

   It contains **no xlsx templates and no callable validation code**. Any computation it
   names is implemented in reviewed, deterministic, tested code and referenced by
   name.
3. A pack never changes how a filing is ingested, parsed or tied out. It only reads the core
   data.

## Consequences

- Nothing speculative is built before a second segment or a paying customer asks for one.
- Supporting the fallback persona (equity earnings-quality) changes alert and UI emphasis,
  not the engine (ROADMAP §2).
- Phase 5 includes a ticket to define `PackSpec` and to extract the credit-specific code
  behind it.

## Alternatives rejected

- **`PackSpec` before Phase 1:** YAGNI; the abstraction would be shaped by guesses (ROADMAP
  §1.1).
- **A YAML pack DSL with templates or embedded logic:** it moves untested logic into data
  and was rejected with the report (DECISIONS 2026-10-14).
