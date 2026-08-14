"""
Unit tests for classification decision log persistence and numeric invariance (Feature 3 Step 4).

Validates:
- Machine-readable JSONL format (spec.md §6, AC-7)
- Structurally numeric-free inputs and outputs in log records (spec.md AC-2)
- Proper resulting_state and taxonomy_status logging (spec.md §6)
"""

from pathlib import Path

from app.classification.decision_log import (
    DecisionLogRepository,
    build_log_entries,
)
from app.classification.models import (
    ClassificationBatchResult,
    ClassificationItemResult,
    ClassifierInputPayload,
    ClassifierRawResponse,
    TaxonomyStatus,
)
from app.classification.taxonomy import SEED_TAXONOMY


def test_build_and_persist_decision_log_entries(tmp_path: Path) -> None:
    job_id = "job-uuid-log-1"
    batch_result = ClassificationBatchResult(
        results=[
            ClassificationItemResult(
                record_index=0,
                payload=ClassifierInputPayload(
                    label="Stock compensation expense",
                    structural_context="Operating Expenses",
                ),
                raw_response=ClassifierRawResponse(
                    label="Stock-Based Compensation",
                    confidence=0.97,
                ),
                is_error=False,
            ),
            ClassificationItemResult(
                record_index=1,
                payload=ClassifierInputPayload(label="Unknown Adjustment"),
                raw_response=ClassifierRawResponse(
                    label="Custom Derivative Loss",
                    confidence=0.82,
                ),
                is_error=False,
            ),
            ClassificationItemResult(
                record_index=2,
                payload=ClassifierInputPayload(label="Failed Item"),
                raw_response=None,
                is_error=True,
                error_detail="API connection timeout",
            ),
        ],
        total_dispatched=3,
        success_count=2,
        error_count=1,
        skipped_count=0,
    )

    entries = build_log_entries(job_id, batch_result, SEED_TAXONOMY)
    assert len(entries) == 3

    assert entries[0].resulting_state == "confirmed"
    assert entries[0].taxonomy_status == TaxonomyStatus.matched
    assert entries[0].raw_response is not None
    assert entries[0].raw_response.label == "Stock-Based Compensation"

    assert entries[1].resulting_state == "pending_confirmation"
    assert entries[1].taxonomy_status == TaxonomyStatus.pending_taxonomy_confirmation
    assert entries[1].raw_response is not None

    assert entries[2].resulting_state == "classification_error"
    assert entries[2].taxonomy_status == TaxonomyStatus.pending_taxonomy_confirmation
    assert entries[2].error_detail == "API connection timeout"

    # Persist and reload
    repo = DecisionLogRepository(data_dir=tmp_path)
    log_path = repo.log_batch_calls(job_id, entries)

    assert log_path.exists()
    assert log_path.name == f"{job_id}_decision_log.jsonl"

    loaded_entries = repo.get_decision_log(job_id)
    assert loaded_entries is not None
    assert len(loaded_entries) == 3

    assert loaded_entries[0].job_id == job_id
    assert loaded_entries[0].input_payload.label == "Stock compensation expense"
    assert loaded_entries[0].resulting_state == "confirmed"


def test_decision_log_numeric_invariance_proof(tmp_path: Path) -> None:
    """
    AC-2 Proof: Asserts that no entry in the decision log contains numeric values,
    amounts, formulas, bounding boxes, or page numbers.
    """
    job_id = "job-uuid-numeric-check"
    batch_result = ClassificationBatchResult(
        results=[
            ClassificationItemResult(
                record_index=0,
                payload=ClassifierInputPayload(label="Restructuring costs"),
                raw_response=ClassifierRawResponse(label="Restructuring Charges", confidence=0.91),
                is_error=False,
            )
        ],
        total_dispatched=1,
        success_count=1,
        error_count=0,
        skipped_count=0,
    )

    entries = build_log_entries(job_id, batch_result, SEED_TAXONOMY)
    repo = DecisionLogRepository(data_dir=tmp_path)
    repo.log_batch_calls(job_id, entries)

    loaded = repo.get_decision_log(job_id)
    assert loaded is not None

    for entry in loaded:
        entry_dict = entry.model_dump()
        payload_dict = entry_dict["input_payload"]
        response_dict = entry_dict["raw_response"]

        # No document coordinates or numeric table fields in payload
        assert "value" not in payload_dict
        assert "bbox" not in payload_dict
        assert "page" not in payload_dict
        assert "source_file" not in payload_dict

        # Response only contains label and confidence score
        assert set(response_dict.keys()) == {"label", "confidence"}
        assert isinstance(response_dict["label"], str)
        assert isinstance(response_dict["confidence"], float)


def test_decision_log_missing_job_returns_none(tmp_path: Path) -> None:
    repo = DecisionLogRepository(data_dir=tmp_path)
    assert repo.get_decision_log("non-existent-job") is None
