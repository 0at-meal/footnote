"""
Record normalization and label attachment engine (Feature 3 Step 3).

Enforces:
- spec.md AC-6: normalized_label does not overwrite raw label.
- spec.md §5: confirmed taxonomy labels are attached; pending labels remain None.
- CONSTITUTION §2.3, NFR7: 5-field schema integrity preserved.
"""

from app.classification.dispatcher import ELIGIBLE_BANDS
from app.classification.models import (
    ClassificationBatchResult,
    ClassifiedRecord,
    TaxonomyStatus,
)
from app.classification.taxonomy import (
    check_label_against_taxonomy,
    match_canonical_taxonomy,
)
from app.extraction.models import ScoredRecord

# Reconciliation bridge keywords (case-insensitive)
_RECONCILIATION_KEYWORDS: list[str] = [
    "reconciliation",
    "non-gaap",
    "adjusted ebitda",
    "ebitda",
    "net income",
    "operating income",
    "operating profit",
    "stock-based compensation",
    "share-based compensation",
    "depreciation",
    "amortization",
    "d&a",
    "restructuring",
    "impairment",
    "acquisition",
    "litigation",
    "interest expense",
    "tax expense",
    "provision for income taxes",
    "other non-operating",
]

# Unrelated filing table patterns to reject if no reconciliation context exists
_UNRELATED_TABLE_KEYWORDS: list[str] = [
    "balance sheet",
    "consolidated balance",
    "property, plant",
    "property and equipment",
    "operating lease",
    "leases",
    "debt",
    "borrowings",
    "credit facility",
    "fair value",
]


def is_target_metric_candidate_item(
    record: ScoredRecord,
    normalized_label: str | None,
    target_metric: str = "Adjusted EBITDA",
) -> bool:
    """
    Determines if a record belongs to the Non-GAAP reconciliation bridge for the target metric.
    """
    table_name = record.table_name or ""
    table_lower = table_name.lower()
    metric_lower = target_metric.lower()
    raw_label = record.record.label.lower()
    norm_label = (normalized_label or "").lower()

    # 1. Table title matches target metric or Non-GAAP reconciliation
    if (
        metric_lower in table_lower
        or "reconciliation" in table_lower
        or "non-gaap" in table_lower
    ):
        return True

    # 2. Check if table is explicitly an unrelated schedule
    is_unrelated_table = any(
        unrelated in table_lower for unrelated in _UNRELATED_TABLE_KEYWORDS
    )

    # 3. Check normalized or raw label against reconciliation bridge components
    for kw in _RECONCILIATION_KEYWORDS:
        if kw in norm_label or kw in raw_label:
            if is_unrelated_table:
                # In unrelated tables, only keep if strongly non-GAAP
                return any(
                    strong in norm_label or strong in raw_label
                    for strong in [
                        "adjusted ebitda",
                        "stock-based",
                        "share-based",
                        "restructuring",
                        "reconciliation",
                        "non-gaap",
                    ]
                )
            return True

    # 4. If table is clearly an unrelated table and didn't match reconciliation keywords
    if is_unrelated_table:
        return False

    # Default to True if table is a general or ambiguous table
    return not (table_name and not table_lower.startswith("table"))


def normalize_records(
    records: list[ScoredRecord],
    batch_result: ClassificationBatchResult,
    active_taxonomy: list[str],
    target_metric: str = "Adjusted EBITDA",
) -> list[ClassifiedRecord]:
    """
    Combines ScoredRecords with classification batch results and active taxonomy.

    Attaches normalized_label for confirmed taxonomy matches, keeping pending/unrecognized
    records with normalized_label=None while preserving raw labels and values verbatim (AC-6),
    and tags records with target metric relevance (Step 2).

    Args:
        records: List of ScoredRecord objects from Feature 2 extraction.
        batch_result: ClassificationBatchResult from classifier dispatcher.
        active_taxonomy: Active taxonomy string entries.
        target_metric: The selected target metric for the extraction job.

    Returns:
        List of ClassifiedRecord objects.
    """
    # Index classification results by original record index
    result_map = {res.record_index: res for res in batch_result.results}

    classified_records: list[ClassifiedRecord] = []

    for idx, record in enumerate(records):
        item_res = result_map.get(idx)

        if (
            item_res is not None
            and not item_res.is_error
            and item_res.raw_response is not None
        ):
            match_res = check_label_against_taxonomy(
                item_res.raw_response.label, active_taxonomy
            )
            if match_res.is_matched and match_res.matched_entry is not None:
                is_candidate = is_target_metric_candidate_item(
                    record, match_res.matched_entry, target_metric=target_metric
                )
                classified_records.append(
                    ClassifiedRecord(
                        record=record,
                        normalized_label=match_res.matched_entry,
                        taxonomy_status=TaxonomyStatus.matched,
                        classifier_confidence=item_res.raw_response.confidence,
                        is_confirmed=True,
                        is_target_metric_candidate=is_candidate,
                    )
                )
            else:
                # Check canonical match on LLM label or raw record label
                canonical_entry = match_canonical_taxonomy(
                    item_res.raw_response.label, active_taxonomy
                ) or match_canonical_taxonomy(record.record.label, active_taxonomy)

                if canonical_entry is not None:
                    is_candidate = is_target_metric_candidate_item(
                        record, canonical_entry, target_metric=target_metric
                    )
                    classified_records.append(
                        ClassifiedRecord(
                            record=record,
                            normalized_label=canonical_entry,
                            taxonomy_status=TaxonomyStatus.matched,
                            classifier_confidence=item_res.raw_response.confidence,
                            is_confirmed=True,
                            is_target_metric_candidate=is_candidate,
                        )
                    )
                else:
                    is_candidate = is_target_metric_candidate_item(
                        record, None, target_metric=target_metric
                    )
                    classified_records.append(
                        ClassifiedRecord(
                            record=record,
                            normalized_label=None,
                            taxonomy_status=TaxonomyStatus.pending_taxonomy_confirmation,
                            classifier_confidence=item_res.raw_response.confidence,
                            is_confirmed=False,
                            is_target_metric_candidate=is_candidate,
                        )
                    )
        else:
            # Skipped (e.g. manual_required, extraction_error) or classifier failure
            canonical_entry = match_canonical_taxonomy(
                record.record.label, active_taxonomy
            )
            if (
                canonical_entry is not None
                and record.confidence_band in ELIGIBLE_BANDS
                and record.status == "ok"
            ):
                is_candidate = is_target_metric_candidate_item(
                    record, canonical_entry, target_metric=target_metric
                )
                classified_records.append(
                    ClassifiedRecord(
                        record=record,
                        normalized_label=canonical_entry,
                        taxonomy_status=TaxonomyStatus.matched,
                        classifier_confidence=0.95,
                        is_confirmed=True,
                        is_target_metric_candidate=is_candidate,
                    )
                )
            else:
                is_candidate = is_target_metric_candidate_item(
                    record, None, target_metric=target_metric
                )
                classified_records.append(
                    ClassifiedRecord(
                        record=record,
                        normalized_label=None,
                        taxonomy_status=TaxonomyStatus.pending_taxonomy_confirmation,
                        classifier_confidence=None,
                        is_confirmed=False,
                        is_target_metric_candidate=is_candidate,
                    )
                )

    return classified_records
