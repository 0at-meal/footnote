"""
Normalization and taxonomy alignment for classified records (Feature 3 Step 3).

Enforces:
- spec.md AC-6: Verified items get normalized_label populated; pending items retain normalized_label=None.
- CONSTITUTION ? 6.3: Conflicting or unrecognized labels queued for human confirmation.
- Step 2: Identifies and tags target metric candidate items (e.g. Adjusted EBITDA reconciliation bridge).
"""

import logging

from app.classification.models import (
    ClassificationBatchResult,
    ClassifiedRecord,
    MasterTaxonomy,
    TaxonomyStatus,
)
from app.classification.taxonomy import (
    SEED_MASTER_TAXONOMY,
    check_label_against_taxonomy,
    match_canonical_taxonomy,
    match_master_taxonomy,
)
from app.extraction.models import ConfidenceBand, ScoredRecord

logger = logging.getLogger(__name__)

ELIGIBLE_BANDS = {ConfidenceBand.auto_accepted, ConfidenceBand.needs_review}

_RECONCILIATION_KEYWORDS: list[str] = [
    "revenue",
    "gross profit",
    "operating income",
    "ebit",
    "net income",
    "ebitda",
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
    target_metric: str | None = "Adjusted EBITDA",
) -> bool:
    """
    Determines if a record belongs to the reconciliation bridge or financial model.
    The reconciliation tag from the parser is the authoritative signal (Ticket R3.1).
    """
    if target_metric is None or target_metric == "Full Model":
        return True

    # 1. Explicit reconciliation table from parser / record
    return bool(
        record.is_reconciliation_candidate
        or record.record.is_reconciliation_candidate
    )


def normalize_records(
    records: list[ScoredRecord],
    batch_result: ClassificationBatchResult | None = None,
    active_taxonomy: list[str] | MasterTaxonomy | None = None,
    target_metric: str | None = "Adjusted EBITDA",
    pre_classified: list[ClassifiedRecord] | None = None,
) -> list[ClassifiedRecord]:
    """
    Combines ScoredRecords with pre-classified items and classifier batch results.

    Merges deterministically pre-classified items with Groq classifier results in the
    exact original order of records (Feature 3).
    """
    taxonomy = active_taxonomy if active_taxonomy is not None else SEED_MASTER_TAXONOMY

    # Map pre-classified records by ScoredRecord identity
    pre_classified_map = {}
    if pre_classified:
        pre_map = {id(pc.record): pc for pc in pre_classified}
        for idx, rec in enumerate(records):
            if id(rec) in pre_map:
                pre_classified_map[idx] = pre_map[id(rec)]

    result_map = {}
    if batch_result is not None:
        result_map = {res.record_index: res for res in batch_result.results}

    classified_records = []

    for idx, record in enumerate(records):
        if idx in pre_classified_map:
            pc = pre_classified_map[idx]
            classified_records.append(pc)
            continue

        item_res = result_map.get(idx)

        if (
            item_res is not None
            and not item_res.is_error
            and item_res.raw_response is not None
        ):
            match_res = check_label_against_taxonomy(
                item_res.raw_response.label, taxonomy
            )
            if match_res.is_matched and match_res.matched_entry is not None:
                statement_type = (
                    match_res.matched_item.statement_type
                    if match_res.matched_item
                    else None
                )
                is_candidate = is_target_metric_candidate_item(
                    record, match_res.matched_entry, target_metric=target_metric
                )
                classified_records.append(
                    ClassifiedRecord(
                        record=record,
                        normalized_label=match_res.matched_entry,
                        statement_type=statement_type,
                        taxonomy_status=TaxonomyStatus.matched,
                        classifier_confidence=item_res.raw_response.confidence,
                        is_confirmed=True,
                        is_target_metric_candidate=is_candidate,
                    )
                )
            else:
                canonical_item = None
                if isinstance(taxonomy, MasterTaxonomy):
                    canonical_item = match_master_taxonomy(
                        item_res.raw_response.label, taxonomy
                    ) or match_master_taxonomy(record.record.label, taxonomy)

                canonical_entry = (
                    canonical_item.canonical_name
                    if canonical_item
                    else (
                        match_canonical_taxonomy(item_res.raw_response.label, taxonomy)
                        or match_canonical_taxonomy(record.record.label, taxonomy)
                    )
                )
                statement_type = (
                    canonical_item.statement_type if canonical_item else None
                )

                if canonical_entry is not None:
                    is_candidate = is_target_metric_candidate_item(
                        record, canonical_entry, target_metric=target_metric
                    )
                    classified_records.append(
                        ClassifiedRecord(
                            record=record,
                            normalized_label=canonical_entry,
                            statement_type=statement_type,
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
                            statement_type=None,
                            taxonomy_status=TaxonomyStatus.pending_taxonomy_confirmation,
                            classifier_confidence=item_res.raw_response.confidence,
                            is_confirmed=False,
                            is_target_metric_candidate=is_candidate,
                        )
                    )
        else:
            canonical_item = None
            if isinstance(taxonomy, MasterTaxonomy):
                canonical_item = match_master_taxonomy(record.record.label, taxonomy)
            canonical_entry = (
                canonical_item.canonical_name
                if canonical_item
                else match_canonical_taxonomy(record.record.label, taxonomy)
            )
            statement_type = canonical_item.statement_type if canonical_item else None

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
                        statement_type=statement_type,
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
                        statement_type=None,
                        taxonomy_status=TaxonomyStatus.pending_taxonomy_confirmation,
                        classifier_confidence=None,
                        is_confirmed=False,
                        is_target_metric_candidate=is_candidate,
                    )
                )

    return classified_records
