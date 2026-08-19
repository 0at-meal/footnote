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


def normalize_records(
    records: list[ScoredRecord],
    batch_result: ClassificationBatchResult,
    active_taxonomy: list[str],
) -> list[ClassifiedRecord]:
    """
    Combines ScoredRecords with classification batch results and active taxonomy.

    Attaches normalized_label for confirmed taxonomy matches, keeping pending/unrecognized
    records with normalized_label=None while preserving raw labels and values verbatim (AC-6).

    Args:
        records: List of ScoredRecord objects from Feature 2 extraction.
        batch_result: ClassificationBatchResult from classifier dispatcher.
        active_taxonomy: Active taxonomy string entries.

    Returns:
        List of ClassifiedRecord objects.
    """
    # Index classification results by original record index
    result_map = {res.record_index: res for res in batch_result.results}

    classified_records: list[ClassifiedRecord] = []

    for idx, record in enumerate(records):
        item_res = result_map.get(idx)

        if item_res is not None and not item_res.is_error and item_res.raw_response is not None:
            match_res = check_label_against_taxonomy(item_res.raw_response.label, active_taxonomy)
            if match_res.is_matched and match_res.matched_entry is not None:
                classified_records.append(
                    ClassifiedRecord(
                        record=record,
                        normalized_label=match_res.matched_entry,
                        taxonomy_status=TaxonomyStatus.matched,
                        classifier_confidence=item_res.raw_response.confidence,
                        is_confirmed=True,
                    )
                )
            else:
                # Check canonical match on LLM label or raw record label
                canonical_entry = match_canonical_taxonomy(
                    item_res.raw_response.label, active_taxonomy
                ) or match_canonical_taxonomy(record.record.label, active_taxonomy)

                if canonical_entry is not None:
                    classified_records.append(
                        ClassifiedRecord(
                            record=record,
                            normalized_label=canonical_entry,
                            taxonomy_status=TaxonomyStatus.matched,
                            classifier_confidence=item_res.raw_response.confidence,
                            is_confirmed=True,
                        )
                    )
                else:
                    classified_records.append(
                        ClassifiedRecord(
                            record=record,
                            normalized_label=None,
                            taxonomy_status=TaxonomyStatus.pending_taxonomy_confirmation,
                            classifier_confidence=item_res.raw_response.confidence,
                            is_confirmed=False,
                        )
                    )
        else:
            # Skipped (e.g. manual_required, extraction_error) or classifier failure
            canonical_entry = match_canonical_taxonomy(record.record.label, active_taxonomy)
            if (
                canonical_entry is not None
                and record.confidence_band in ELIGIBLE_BANDS
                and record.status == "ok"
            ):
                classified_records.append(
                    ClassifiedRecord(
                        record=record,
                        normalized_label=canonical_entry,
                        taxonomy_status=TaxonomyStatus.matched,
                        classifier_confidence=0.95,
                        is_confirmed=True,
                    )
                )
            else:
                classified_records.append(
                    ClassifiedRecord(
                        record=record,
                        normalized_label=None,
                        taxonomy_status=TaxonomyStatus.pending_taxonomy_confirmation,
                        classifier_confidence=None,
                        is_confirmed=False,
                    )
                )

    return classified_records
