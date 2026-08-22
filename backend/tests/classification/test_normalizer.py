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
    records = [
        create_sample_scored_record("Stock compensation expense", value="15,000")
    ]
    batch_result = ClassificationBatchResult(
        results=[
            ClassificationItemResult(
                record_index=0,
                payload=ClassifierInputPayload(label="Stock compensation expense"),
                raw_response=ClassifierRawResponse(
                    label="Stock-Based Compensation", confidence=0.96
                ),
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
                raw_response=ClassifierRawResponse(
                    label="Non-Standard Hedging Loss", confidence=0.85
                ),
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
        create_sample_scored_record(
            "Manual entry row", band=ConfidenceBand.manual_required
        ),
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


def test_canonical_taxonomy_match_attaches_normalized_label() -> None:
    records = [create_sample_scored_record("Stock based compensation", value="20,000")]
    batch_result = ClassificationBatchResult(
        results=[
            ClassificationItemResult(
                record_index=0,
                payload=ClassifierInputPayload(label="Stock based compensation"),
                raw_response=ClassifierRawResponse(
                    label="stock-based compensation", confidence=0.92
                ),
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
    assert item.classifier_confidence == 0.92


def test_offline_fallback_normalizer_attaches_seed_taxonomy() -> None:
    records = [
        create_sample_scored_record("Restructuring charges", value="5,000"),
        create_sample_scored_record("Random custom note", value="1,000"),
    ]
    # Simulate failed/empty batch result
    batch_result = ClassificationBatchResult(
        results=[],
        total_dispatched=0,
        success_count=0,
        error_count=0,
        skipped_count=0,
    )

    classified = normalize_records(records, batch_result, SEED_TAXONOMY)
    assert len(classified) == 2

    # First record matches SEED_TAXONOMY canonically
    assert classified[0].normalized_label == "Restructuring Charges"
    assert classified[0].taxonomy_status == TaxonomyStatus.matched
    assert classified[0].is_confirmed is True
    assert classified[0].classifier_confidence == 0.95

    # Second record does not match and remains pending
    assert classified[1].normalized_label is None
    assert classified[1].taxonomy_status == TaxonomyStatus.pending_taxonomy_confirmation
    assert classified[1].is_confirmed is False
    assert classified[1].classifier_confidence is None


def test_target_metric_candidate_tagging_reconciliation_vs_balance_sheet() -> None:
    """Ticket 2.3: Reconciliation bridge items are marked candidates; balance sheet items are not."""
    # 1. Non-GAAP reconciliation table items
    rec_sbc = create_sample_scored_record(
        "Stock-based compensation expense", value="12,000"
    )
    rec_sbc.table_name = "Reconciliation of Net Income to Non-GAAP Adjusted EBITDA"

    rec_da = create_sample_scored_record(
        "Depreciation and amortization", value="34,000"
    )
    rec_da.table_name = "Non-GAAP Financial Measures"

    rec_restruct = create_sample_scored_record(
        "Restructuring and severance charges", value="5,000"
    )
    rec_restruct.table_name = "Adjusted EBITDA Reconciliation"

    # 2. Balance sheet / lease / PPE items
    rec_cash = create_sample_scored_record("Cash and cash equivalents", value="150,000")
    rec_cash.table_name = "Consolidated Balance Sheets"

    rec_ppe = create_sample_scored_record(
        "Property, plant and equipment, net", value="850,000"
    )
    rec_ppe.table_name = "Property and Equipment Schedule"

    rec_lease = create_sample_scored_record(
        "Operating lease liabilities, non-current", value="45,000"
    )
    rec_lease.table_name = "Operating Lease Commitments"

    records = [rec_sbc, rec_da, rec_restruct, rec_cash, rec_ppe, rec_lease]
    batch_result = ClassificationBatchResult(
        results=[],
        total_dispatched=0,
        success_count=0,
        error_count=0,
        skipped_count=6,
    )

    classified = normalize_records(
        records, batch_result, SEED_TAXONOMY, target_metric="Adjusted EBITDA"
    )
    assert len(classified) == 6

    # Reconciliation items should be target metric candidates
    assert classified[0].is_target_metric_candidate is True
    assert classified[1].is_target_metric_candidate is True
    assert classified[2].is_target_metric_candidate is True

    # Balance sheet and lease items must NOT be target metric candidates
    assert classified[3].is_target_metric_candidate is False
    assert classified[4].is_target_metric_candidate is False
    assert classified[5].is_target_metric_candidate is False
