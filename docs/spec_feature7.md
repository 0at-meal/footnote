# spec.md -- Feature 7: Cross-Year Drift Detection

**Satisfies:** FR4
**Phase:** 4 -- Extensibility & Compliance Output
**Depends on:** Feature 3 (confirmed, normalized labels per filing -- `normalized_label` populated and taxonomy-matched); Feature 5 (only locked/confirmed items feed the drift graph -- items still pending review are excluded)
**Status:** Completed

---

## What This Feature Does

1. **Label comparison against prior-year graph.** For each confirmed, locked extraction record in the current filing (identified by `job_id`), the feature compares that record's `normalized_label` against the drift graph entries for the same entity and target metric from prior years. The comparison is exact string equality -- the same matching rule as Feature 3's taxonomy check. For each target metric (e.g., Adjusted EBITDA), the feature identifies: which normalized labels are present in the current filing but absent in the prior-year graph entry (added components), and which are present in the prior-year graph entry but absent in the current filing (removed components). Both are discrepancies. A filing with no prior-year graph entry for that entity and metric is treated as the baseline year -- no discrepancy is generated, and the graph is initialized with the current filing's component set.

2. **Discrepancy flagging.** When added or removed components are detected for a target metric, a drift flag is generated for that metric and filing. The flag is a structured record containing: the entity identifier, the target metric, the filing year (derived from the job record), the list of added normalized labels, the list of removed normalized labels, and the prior-year graph node it was compared against. The drift flag is persisted to the same SQLite/JSON store as the graph and is retrievable via an API endpoint. It is also surfaced in the job summary so that the user is immediately aware of a definitional change without needing to query separately. A filing where zero discrepancies are found produces no drift flag -- silence means consistency, not a missing check.

3. **Historical graph linkage.** When a discrepancy is detected, the current filing's component set is added to the graph as a new node, and a directed edge is created from the prior-year node to the new node. The edge carries the change metadata: filing year, added labels, removed labels. The prior-year node is never modified or deleted -- the graph is strictly append-only for drift links. If the current filing's component set is identical to the prior year's, no new node is created for that metric; the existing node is reused, and the edge marks the filing year as a continuation. The graph is keyed by (entity, metric) at the top level, with individual nodes representing each distinct definition observed over time.

4. **Graph persistence.** The drift graph is serialized to the SQLite/JSON store after every update -- every node addition and every edge addition triggers a write before the operation is considered complete (NFR7). On backend startup, the graph is reloaded from the persisted store before any drift comparison is run. No graph state is held exclusively in memory; the persisted form is always the authoritative source. The persistence format uses NetworkX's JSON serialization over SQLite, per plan section 2's tech stack (NetworkX + SQLite/JSON). The serialization write is synchronous: the update is not confirmed to the caller until the write has completed.

---

## What This Feature Does NOT Do

- **Does not compare raw `label` fields.** The comparison is exclusively on `normalized_label` -- the taxonomy-matched, human-confirmed label from Feature 3/5. Raw labels from Feature 2 are never fed into the drift graph.
- **Does not run drift detection on unconfirmed or unlocked items.** Records that are still in `pending_taxonomy_confirmation`, `needs_review`, `manual_required`, or `extraction_error` state are excluded from drift graph input. Only `locked` items (Feature 5's confirmed state) are eligible.
- **Does not perform fuzzy or semantic label matching.** Two normalized labels that are "close" but not identical are treated as different components. The same label appearing in two consecutive years produces a continuation, not a discrepancy.
- **Does not modify any extraction record or review status.** Feature 7 reads confirmed records; it does not write back to Feature 2's records or Feature 5's status store.
- **Does not retroactively re-run drift detection on prior filings.** When a new filing is processed, only the current filing is compared to the graph. Prior filings' graph nodes and edges are not recomputed.
- **Does not present a UI for drift review.** Drift flags are surfaced in the job summary and retrievable via API. The review UI for drift flags is not part of this feature's scope.
- **Does not generate the audit report.** Feature 8 reads the drift flags for inclusion in the audit PDF. Feature 7 produces and persists the flags; Feature 8 consumes them.
- **Does not handle multi-entity, multi-metric jobs beyond the job's configured scope.** The drift comparison is scoped to the entity and target metric configured on the job record (from Feature 1). Cross-entity drift is not computed.
- **Does not resolve which entity a filing belongs to.** Entity identification is a prerequisite -- the job record must carry an entity identifier supplied by the user at upload time (Feature 1). Feature 7 reads this identifier; it does not derive it from the filing content.

---

## Acceptance Criteria

1. **Drift history survives a backend restart.** After processing a filing that produces a drift flag and graph update, restarting the backend must result in the graph being reloaded with all prior nodes and edges intact. A drift comparison run immediately after restart produces the same result as a comparison run before restart, given the same input filing.

2. **A known year-over-year redefinition is correctly flagged.** Given a benchmark corpus filing pair (year N and year N+1) where a known label was added or removed from the Adjusted EBITDA reconciliation, the feature must produce a drift flag identifying the correct added and/or removed label(s). The flag must name the specific labels, not just indicate "something changed."

3. **Baseline year produces no drift flag and initializes the graph.** For the first filing processed for a given (entity, metric) pair -- where no prior graph entry exists -- no drift flag is generated. The graph is initialized with that filing's confirmed component set as the baseline node. A subsequent comparison against this baseline operates correctly.

4. **Added and removed components are separately enumerated in the flag.** A drift flag for a metric where two labels were added and one was removed must list exactly two added labels and one removed label. Labels that are present in both years must not appear in either list.

5. **Only locked items contribute to the drift graph.** Given a filing where 80 records are locked and 10 are still in `pending_taxonomy_confirmation`, the drift graph update uses the 80 locked records only. The 10 pending records do not appear in the graph node for this filing, even if they have a `normalized_label` value.

6. **Graph node is reused when component set is unchanged.** If filing year N+1 has an identical confirmed component set to year N for a given (entity, metric) pair, no new graph node is created. The existing node is reused. The edge from year N to year N+1 marks the year as a continuation. The graph does not grow a new node for every filing regardless of whether the definition changed.

7. **Graph update is atomic: no partial writes.** If the graph update (node addition + edge addition + serialization) fails partway through, the graph must not be left in a state where the node exists but the edge is missing, or the in-memory graph and the persisted graph diverge. Either the full update is committed or the graph remains at its prior state.

8. **Drift flag is retrievable via API endpoint without UI dependency.** A drift flag produced for a given job must be retrievable by querying the drift flag API endpoint with that `job_id`. The response includes entity, metric, filing year, added labels, removed labels, and the prior graph node reference. The endpoint is accessible without navigating the UI.

9. **No drift flag is produced for a filing with zero discrepancies.** If the current filing's confirmed component set for a metric exactly matches the prior-year graph node's component set (same labels, no additions, no removals), no drift flag record is created or persisted for that metric. Querying the drift flag endpoint for that job returns an empty list for that metric.

10. **Graph serialization write completes before the update is confirmed.** The API response confirming a drift graph update must not be returned until the SQLite/JSON serialization write has completed. In-memory-only updates that have not yet been serialized must not be treated as durable.

---

## Dependencies / Interfaces with Other Features

### Consumed from Feature 1
- **Entity identifier and `job_id`**: the entity identifier (supplied by the user at upload time) and the filing year (derived from the job record or filing metadata) scope the drift graph lookup. Feature 7 reads these from the job record; it does not derive them from filing content.
- **Target metric**: the configured `target_metric` on the job record determines which metric's component set is compared.

### Consumed from Feature 3
- **`normalized_label`**: the confirmed, taxonomy-matched label on each extraction record. This is the unit of comparison in the drift graph. Feature 7 reads `normalized_label`; it does not modify it.

### Consumed from Feature 5
- **`locked` status**: only records with `status: locked` are eligible for drift graph input. Feature 7 reads the locked status; it does not write to the review status store.

### Exposed for Feature 8
- **Drift flags**: structured records identifying (entity, metric, filing year, added labels, removed labels, prior graph node reference). Feature 8 reads these to include a drift summary in the audit report.
- **Drift graph API endpoint**: queryable by (entity, metric) to retrieve the full historical graph for inclusion in audit artifacts.

### Must Not Break
- The `drift/` module must not import from `classification/`, `extraction/`, or `excel_export/` (CONSTITUTION 3.5). It reads from the shared data store only.
- Every graph update must be followed by a synchronous serialization write. No in-memory-only update path may be left open (NFR7).
- The frozen field names (`value`, `label`, `page`, `bbox`, `source_file`, `normalized_label`) must remain unchanged in any record this feature reads (CONSTITUTION 2.3, NFR7).

---

## Predictable Edge Cases

| # | Edge Case | Required Behavior |
|---|---|---|
| EC-1 | Two filings for the same entity and metric are processed in the same session, in the same order as their filing years. | The second filing is compared against the graph node created by the first. If the component sets differ, a drift flag is created referencing the first filing as the prior node. Graph: baseline node (filing 1) -> new node (filing 2) with edge carrying the discrepancy. |
| EC-2 | A filing is processed out of chronological order (e.g., year N+1 is processed before year N). | The graph compares the current filing against whatever node exists as the most recent prior entry for that (entity, metric) pair, regardless of calendar order. The filing year on the job record is stored in the node and edge; chronological ordering is the user's responsibility at upload time. No silent reordering is performed. |
| EC-3 | All of a filing's locked records for a target metric were subsequently unlocked and are now unconfirmed. | The graph node for that filing's metric reflects only the locked records at the time the drift comparison was run. If all records are later unlocked, the graph is not retroactively updated -- the persisted node remains. A new drift comparison run (manually triggered) would re-evaluate against the current locked set. |
| EC-4 | A filing has zero locked records for a target metric (all records pending or in error). | No drift comparison is run for that metric in that filing. No graph node is created. No drift flag is produced. The job summary notes that drift detection was skipped for that metric due to no confirmed records. |
| EC-5 | The SQLite/JSON serialization write fails (e.g., disk full). | The graph update is rolled back in memory. The in-memory graph reverts to its pre-update state. A serialization error is recorded in the job summary. The drift flag is not persisted. The API response for that update returns an error, not a success. |
| EC-6 | A normalized label in the current filing contains a character that is invalid in the SQLite/JSON key space (e.g., null byte). | The label is stored as-is using JSON string escaping. No truncation or substitution occurs. The graph comparison uses the exact stored string. If the label cannot be serialized as valid JSON, the update fails with an explicit error -- it does not silently substitute a sanitized version. |
| EC-7 | The prior-year graph node for a metric lists 10 component labels, but 3 of those labels were subsequently removed from the seed taxonomy (Feature 3). | The graph node retains the 3 now-removed labels as historical data. Drift detection compares current labels against the stored node regardless of whether the stored labels are still in the active taxonomy. The graph is a historical record, not a live taxonomy reference. |
| EC-8 | The drift comparison is triggered while a batch of records for the same job is still being confirmed in Feature 5 (race condition). | Drift comparison must only be triggered after the job's review phase is explicitly marked complete (a user action). It must not be triggered mid-review. The trigger condition is a job-level state transition (e.g., `review_complete`), not an individual record lock event. |
| EC-9 | Two entities have filings with identical normalized label sets for the same target metric. | The graph is keyed by (entity, metric) -- each entity has its own independent graph subtree. The identical label sets produce two separate baseline nodes, one per entity. No cross-entity linkage is created. |
| EC-10 | A drift flag is queried for a `job_id` that has no prior-year graph entry (baseline year). | The API returns a structured response indicating: no drift flag (baseline year), the graph node that was initialized, and the component set stored. The response is not an error -- a baseline initialization is a valid, expected outcome. |