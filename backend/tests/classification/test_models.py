"""
Unit tests for classification domain models (Feature 3 Step 1).

Validates:
- Structurally numeric-free return types (CONSTITUTION §1.2, §6.2)
- Input payload sanitization (CONSTITUTION §6.5)
- Boundary condition validation (EC-1, EC-2)
"""

import pytest
from app.classification.models import (
    ClassificationBatchResult,
    ClassificationItemResult,
    ClassifierInputPayload,
    ClassifierRawResponse,
)
from pydantic import ValidationError


def test_classifier_input_payload_valid() -> None:
    payload = ClassifierInputPayload(label="Stock-Based Compensation")
    assert payload.label == "Stock-Based Compensation"
    assert payload.structural_context is None


def test_classifier_input_payload_with_context() -> None:
    payload = ClassifierInputPayload(
        label="Litigation Settlement",
        structural_context="Operating Expenses / Other Charges",
    )
    assert payload.label == "Litigation Settlement"
    assert payload.structural_context == "Operating Expenses / Other Charges"


def test_classifier_input_payload_rejects_empty_label() -> None:
    with pytest.raises(ValidationError):
        ClassifierInputPayload(label="")


def test_classifier_input_payload_has_no_value_or_numeric_fields() -> None:
    schema = ClassifierInputPayload.model_json_schema()
    properties = schema.get("properties", {})
    assert "value" not in properties
    assert "page" not in properties
    assert "bbox" not in properties
    assert "source_file" not in properties


def test_classifier_raw_response_valid() -> None:
    resp = ClassifierRawResponse(label="Stock-Based Compensation", confidence=0.95)
    assert resp.label == "Stock-Based Compensation"
    assert resp.confidence == 0.95


def test_classifier_raw_response_boundary_confidence() -> None:
    # 0.0 and 1.0 are valid boundary values (EC-6)
    resp_zero = ClassifierRawResponse(label="Impairment Charges", confidence=0.0)
    assert resp_zero.confidence == 0.0

    resp_one = ClassifierRawResponse(label="Impairment Charges", confidence=1.0)
    assert resp_one.confidence == 1.0


def test_classifier_raw_response_rejects_empty_label() -> None:
    with pytest.raises(ValidationError):
        ClassifierRawResponse(label="", confidence=0.85)


def test_classifier_raw_response_rejects_negative_confidence() -> None:
    with pytest.raises(ValidationError):
        ClassifierRawResponse(label="Lease Adjustment", confidence=-0.1)


def test_classifier_raw_response_rejects_confidence_above_one() -> None:
    with pytest.raises(ValidationError):
        ClassifierRawResponse(label="Lease Adjustment", confidence=1.05)


def test_classifier_raw_response_schema_strictly_numeric_free_except_confidence() -> (
    None
):
    schema = ClassifierRawResponse.model_json_schema()
    properties = schema.get("properties", {})
    # Only "label" (string) and "confidence" (number) may exist
    assert set(properties.keys()) == {"label", "confidence"}
    assert properties["label"]["type"] == "string"
    assert properties["confidence"]["type"] == "number"


def test_classification_item_result() -> None:
    payload = ClassifierInputPayload(label="Restructuring")
    raw_resp = ClassifierRawResponse(label="Restructuring Charges", confidence=0.9)
    item = ClassificationItemResult(
        record_index=0,
        payload=payload,
        raw_response=raw_resp,
        is_error=False,
    )
    assert item.record_index == 0
    assert item.raw_response is not None
    assert item.raw_response.label == "Restructuring Charges"
    assert item.is_error is False


def test_classification_batch_result() -> None:
    batch = ClassificationBatchResult(
        results=[],
        total_dispatched=0,
        success_count=0,
        error_count=0,
        skipped_count=2,
    )
    assert batch.total_dispatched == 0
    assert batch.skipped_count == 2
