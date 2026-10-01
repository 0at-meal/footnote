# Engineering Workbook — Feature 3: Classification & Normalization

**Module:** Classification Pipeline (`backend/app/classification/`)
**Phase:** 2 — Core Trust Loop
**Satisfies:** FR3
**Status:** Completed
**Author:** Antigravity Engineering

---

## 1. Purpose

Feature 3 is the LLM-as-classifier layer. After Feature 2 produces `ScoredRecord` objects, Feature 3 dispatches each reconciliation-candidate record to the Groq API (`openai/gpt-oss-120b`) to receive a normalized taxonomy label. The classifier's output is strictly limited to `{label, confidence}` — it can never produce a numeric value (CONSTITUTION §6.1, §6.2).

---

## 2. Scope of Change

### Backend — `backend/app/classification/`

| File | Responsibility |
|---|---|
| `models.py` | `TaxonomyItem`, `MasterTaxonomy`, `ClassifiedRecord`, `TaxonomyStatus`, `StatementType` — all strictly typed, no numeric fields |
| `taxonomy.py` | Seed taxonomy (~17 canonical non-GAAP items); `check_taxonomy(label)` → `TaxonomyCheckResult` |
| `client.py` | Groq API client; rate-limit-aware retry/backoff; single-request dispatch; logs input context + returned label + confidence |
| `dispatcher.py` | `dispatch_records_to_classifier(records, target_metric)` — batched dispatch respecting Groq free-tier limits (30 RPM / 1,000 RPD / 8,000 TPM) |
| `normalizer.py` | `normalize_records(classified_records, target_metric)` — taxonomy lookup, `is_target_metric_candidate_item()` tagging |

### Key Data Models

```python
class ClassifiedRecord(BaseModel):
    # All ExtractedRecord fields (frozen 5-field schema preserved)
    value: str
    label: str
    page: int
    bbox: dict
    source_file: str
    # Classification additions
    normalized_label: str | None = None
    taxonomy_status: TaxonomyStatus     # matched / unrecognized / pending_confirmation
    classifier_confidence: float | None = None
    is_target_metric_candidate: bool = False
    table_name: str | None = None
    is_reconciliation_candidate: bool = False
```

**CONSTITUTION compliance note:** `ClassifiedRecord` structurally cannot carry a numeric field (§6.2). The public interface of `classification/` exposes labels only.

---

## 3. Groq API Constraints

| Limit | Value | Mitigation |
|---|---|---|
| RPM | 30 | Batch size tuned; inter-request sleep on threshold |
| RPD | 1,000 | Filter to reconciliation candidates before dispatch (reduces per-filing call count by ~90%) |
| TPM | 8,000 | Context window per call limited to item label + surrounding table context |
| TPD | 200,000 | Within budget for realistic MVP workloads post-filtering |

The Groq client (`client.py`) implements exponential backoff on HTTP 429 responses.

---

## 4. Taxonomy Lookup

`check_taxonomy(label)` performs:
1. **Exact match** against canonical names.
2. **Canonicalized match** (lowercase, strip punctuation).
3. **Alias match** against known aliases in `MasterTaxonomy`.
4. If no match: returns `TaxonomyStatus.unrecognized` → item queued in `pending_taxonomy_confirmation` review status.

Items with `TaxonomyStatus.matched` AND `confidence_band == auto_accepted` are pre-locked in the review repository — they never appear in the analyst's flagged queue.

---

## 5. Decision Logging

Per CONSTITUTION §6.1 and Feature 3 Step 6, every classifier call is logged:
- Input context (item label, table context, target metric)
- Returned label and confidence score
- Taxonomy lookup result

The decision log is exportable (surfaced in the audit report via Feature 8).

---

## 6. Test Suite

| File | Coverage |
|---|---|
| `tests/classification/test_dispatcher.py` | Batching, rate-limit guard, reconciliation-only filtering |
| `tests/classification/test_normalizer.py` | Candidate tagging, taxonomy lookup, pre-lock on auto-accepted+matched |
| `tests/classification/test_taxonomy.py` | Exact/alias/canonicalized matching, unrecognized path |
