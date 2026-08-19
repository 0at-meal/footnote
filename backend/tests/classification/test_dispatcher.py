"""
Unit tests for classifier dispatcher (Feature 3 Step 1).

Validates:
- Precondition filtering (AC-9, EC-9: manual_required & extraction_error excluded)
- Payload data egress sanitization (CONSTITUTION §6.5: no values or file metadata)
- Batch aggregation and non-aborting item errors (AC-3, EC-4)
"""

from unittest.mock import MagicMock

from app.classification.dispatcher import (
    dispatch_records_to_classifier,
    is_record_eligible_for_classification,
)
from app.classification.models import ClassifierRawResponse
from app.extraction.models import (
    ConfidenceBand,
    ExtractedRecord,
    ScoredRecord,
)
from groq import APIConnectionError


def create_sample_scored_record(
    label: str,
    band: ConfidenceBand,
    status: str = "ok",
    value: str = "123,456",
) -> ScoredRecord:
    record = ExtractedRecord(
        value=value,
        label=label,
        page=1,
        bbox={"x0": 0.0, "y0": 0.0, "x1": 100.0, "y1": 100.0},
        source_file="filing.pdf",
    )
    return ScoredRecord(
        record=record,
        confidence_score=0.98 if band == ConfidenceBand.auto_accepted else 0.80,
        confidence_band=band,
        flags=[],
        status="ok" if status == "ok" else "extraction_error",
    )


def test_is_record_eligible_for_classification() -> None:
    rec_auto = create_sample_scored_record("SBC", ConfidenceBand.auto_accepted)
    assert is_record_eligible_for_classification(rec_auto) is True

    rec_review = create_sample_scored_record("Lease", ConfidenceBand.needs_review)
    assert is_record_eligible_for_classification(rec_review) is True

    rec_manual = create_sample_scored_record("Other", ConfidenceBand.manual_required)
    assert is_record_eligible_for_classification(rec_manual) is False

    rec_error = create_sample_scored_record("Error item", ConfidenceBand.auto_accepted, status="extraction_error")
    assert is_record_eligible_for_classification(rec_error) is False


def test_dispatch_records_filters_and_sanitizes_payloads() -> None:
    records = [
        create_sample_scored_record("Stock compensation", ConfidenceBand.auto_accepted, value="10,000"),
        create_sample_scored_record("Manual adjustment", ConfidenceBand.manual_required, value="20,000"),
        create_sample_scored_record("Litigation reserve", ConfidenceBand.needs_review, value="30,000"),
        create_sample_scored_record("Corrupted line", ConfidenceBand.needs_review, status="extraction_error", value="40,000"),
    ]

    mock_client = MagicMock()
    mock_client.classify.side_effect = [
        ClassifierRawResponse(label="Stock-Based Compensation", confidence=0.96),
        ClassifierRawResponse(label="Litigation Charges", confidence=0.88),
    ]

    batch = dispatch_records_to_classifier(records, mock_client)

    assert batch.total_dispatched == 2
    assert batch.skipped_count == 2
    assert batch.success_count == 2
    assert batch.error_count == 0
    assert len(batch.results) == 2

    # Verify indices point to original positions (0 and 2)
    assert batch.results[0].record_index == 0
    assert batch.results[1].record_index == 2

    # Verify outbound payloads sent to client.classify do not contain value
    assert mock_client.classify.call_count == 2
    call_args_list = mock_client.classify.call_args_list
    assert call_args_list[0][0][0].label == "Stock compensation"
    assert not hasattr(call_args_list[0][0][0], "value")
    assert call_args_list[1][0][0].label == "Litigation reserve"


def test_dispatch_records_handles_item_error_without_aborting_batch() -> None:
    records = [
        create_sample_scored_record("SBC 1", ConfidenceBand.auto_accepted),
        create_sample_scored_record("Malformed 2", ConfidenceBand.auto_accepted),
        create_sample_scored_record("SBC 3", ConfidenceBand.auto_accepted),
    ]

    mock_client = MagicMock()
    mock_client.classify.side_effect = [
        ClassifierRawResponse(label="Stock-Based Compensation", confidence=0.95),
        ValueError("Malformed JSON response from Groq classifier"),
        ClassifierRawResponse(label="Stock-Based Compensation", confidence=0.97),
    ]

    batch = dispatch_records_to_classifier(records, mock_client)

    assert batch.total_dispatched == 3
    assert batch.success_count == 2
    assert batch.error_count == 1
    assert batch.skipped_count == 0

    assert batch.results[0].is_error is False
    assert batch.results[0].raw_response is not None

    assert batch.results[1].is_error is True
    assert batch.results[1].raw_response is None
    assert "Malformed JSON" in (batch.results[1].error_detail or "")

    assert batch.results[2].is_error is False
    assert batch.results[2].raw_response is not None


def test_dispatch_records_offline_direct_match_fallback_on_api_error() -> None:
    records = [
        create_sample_scored_record("Restructuring charges", ConfidenceBand.auto_accepted),
        create_sample_scored_record("Unrelated arbitrary label", ConfidenceBand.auto_accepted),
    ]

    mock_client = MagicMock()
    mock_client.classify.side_effect = APIConnectionError(request=MagicMock())

    batch = dispatch_records_to_classifier(records, mock_client)

    assert batch.total_dispatched == 2
    assert batch.success_count == 1
    assert batch.error_count == 1

    # First record falls back to canonical match
    assert batch.results[0].is_error is False
    assert batch.results[0].raw_response is not None
    assert batch.results[0].raw_response.label == "Restructuring Charges"
    assert batch.results[0].raw_response.confidence == 0.95

    # Second record has no match and records error
    assert batch.results[1].is_error is True
    assert batch.results[1].raw_response is None
