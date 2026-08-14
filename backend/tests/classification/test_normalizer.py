"""
Unit tests for record normalizer and label attachment (Feature 3 Step 3).

Validates:
- Confirmed taxonomy label attachment (spec.md §5)
- Non-overwrite of raw label and preservation of numeric value (spec.md AC-6, CONSTITUTION §6.1, §6.2)
- Pending status and None normalized_label for unrecognized/skipped items (spec.md AC-6)
"""

from app.classification.models import (
    ClassificationBatchResult,
    ClassificationItemResult,
    ClassifierInputPayload,
    ClassifierRawResponse,
    TaxonomyStatus,
)
from app.classification.normalizer import normalize_records
from app.classification.taxonomy import SEED_TAXONOMY
from app.extraction.models import (
    ConfidenceBand,
    ExtractedRecord,
    ScoredRecord,
)


def create_sample_scored_record(
    label: str,
    band: ConfidenceBand = ConfidenceBand.auto_accepted,
    status: str = "ok",
    value: str = "123,456",
) -> ScoredRecord:
    record = ExtractedRecord(
        value=value,
        label=label,
        page=1,
        bbox={"x0": 0.0, "y0": 0.0, "x1": 100.0, "y1": 100.0},
        source_file="annual_report.pdf",
    )
    return ScoredRecord(
        record=record,
        confidence_score=0.98 if band == ConfidenceBand.auto_accepted else 0.80,
        confidence_band=band,
        flags=[],
        status="ok" if status == "ok" else "extraction_error",
    )


def test_matched_item_attaches_normalized_label() -> None:
    records = [create_sample_scored_record("Stock compensation expense", value="15,000")]
    batch_result = ClassificationBatchResult(
        results=[
            ClassificationItemResult(
                record_index=0,
                payload=ClassifierInputPayload(label="Stock compensation expense"),
                raw_response=ClassifierRawResponse(label="Stock-Based Compensation", confidence=0.96),
                is_error=False,
            )
        ],
        total_dispatched=1,
        success_count=1,
        error_count=0,
        skipped_count=0,
    )

    classified = normalize_records(records, batch_result, SEED_TAXONOMY)
    assert len(classified) == 1
    item = classified[0]

    assert item.normalized_label == "Stock-Based Compensation"
    assert item.taxonomy_status == TaxonomyStatus.matched
    assert item.is_confirmed is True
    assert item.classifier_confidence == 0.96

    # AC-6: Raw label and value must be strictly preserved and unmodified
    assert item.record.record.label == "Stock compensation expense"
    assert item.record.record.value == "15,000"
    assert item.record.record.page == 1
    assert item.record.record.source_file == "annual_report.pdf"


def test_unrecognized_item_has_none_normalized_label() -> None:
    records = [create_sample_scored_record("Custom hedge adjustment", value="2,500")]
    batch_result = ClassificationBatchResult(
        results=[
            ClassificationItemResult(
                record_index=0,
                payload=ClassifierInputPayload(label="Custom hedge adjustment"),
                raw_response=ClassifierRawResponse(label="Non-Standard Hedging Loss", confidence=0.85),
                is_error=False,
            )
        ],
        total_dispatched=1,
        success_count=1,
        error_count=0,
        skipped_count=0,
    )

    classified = normalize_records(records, batch_result, SEED_TAXONOMY)
    assert len(classified) == 1
    item = classified[0]

    # AC-6: Unrecognized label leaves normalized_label as None, pending confirmation
    assert item.normalized_label is None
    assert item.taxonomy_status == TaxonomyStatus.pending_taxonomy_confirmation
    assert item.is_confirmed is False
    assert item.classifier_confidence == 0.85
    assert item.record.record.label == "Custom hedge adjustment"


def test_skipped_and_error_items_are_pending() -> None:
    records = [
        create_sample_scored_record("Manual entry row", band=ConfidenceBand.manual_required),
        create_sample_scored_record("Corrupted row", status="extraction_error"),
    ]
    batch_result = ClassificationBatchResult(
        results=[],
        total_dispatched=0,
        success_count=0,
        error_count=0,
        skipped_count=2,
    )

    classified = normalize_records(records, batch_result, SEED_TAXONOMY)
    assert len(classified) == 2

    for item in classified:
        assert item.normalized_label is None
        assert item.taxonomy_status == TaxonomyStatus.pending_taxonomy_confirmation
        assert item.is_confirmed is False
        assert item.classifier_confidence is None
