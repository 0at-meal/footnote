"""
Integration tests for the classification FastAPI router (Feature 3 Step 4).

Validates:
- GET /classification/{job_id}/decision-log returns 200 with DecisionLogResponse (spec.md AC-7)
- GET /classification/{job_id}/decision-log returns 404 for missing jobs
"""

from unittest.mock import patch

from app.classification.decision_log import DecisionLogRepository
from app.classification.models import (
    ClassifierInputPayload,
    ClassifierRawResponse,
    DecisionLogEntry,
    TaxonomyStatus,
)
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_get_decision_log_success_200(tmp_path) -> None:  # type: ignore[no-untyped-def]
    job_id = "test-job-api-1"
    repo = DecisionLogRepository(data_dir=tmp_path)

    sample_entry = DecisionLogEntry(
        job_id=job_id,
        record_index=0,
        timestamp="2026-08-14T20:00:00Z",
        input_payload=ClassifierInputPayload(label="Stock-based comp"),
        raw_response=ClassifierRawResponse(
            label="Stock-Based Compensation", confidence=0.99
        ),
        taxonomy_status=TaxonomyStatus.matched,
        resulting_state="confirmed",
    )
    repo.log_batch_calls(job_id, [sample_entry])

    with patch("app.classification.router.DecisionLogRepository", return_value=repo):
        response = client.get(f"/classification/{job_id}/decision-log")

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id
    assert data["total_calls"] == 1
    assert len(data["entries"]) == 1
    assert data["entries"][0]["input_payload"]["label"] == "Stock-based comp"
    assert data["entries"][0]["raw_response"]["label"] == "Stock-Based Compensation"
    assert data["entries"][0]["resulting_state"] == "confirmed"


def test_get_decision_log_not_found_404(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo = DecisionLogRepository(data_dir=tmp_path)

    with patch("app.classification.router.DecisionLogRepository", return_value=repo):
        response = client.get("/classification/non-existent-job-id/decision-log")

    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()
