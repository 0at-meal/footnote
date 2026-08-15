"""
Tests for GET /review/{job_id}/items endpoint (Feature 5 Step 1).

Validates:
- 200 returns correctly mapped ReviewItem list from classified records
- 200 falls back to scored records when classified records are absent
- 404 returned when job is not found
- 404 returned when no extraction records exist for job
- Review status derivation correctly covers all confidence bands and edge statuses
"""

from pathlib import Path
from unittest.mock import patch

from app.classification.models import ClassifiedRecord, TaxonomyStatus
from app.classification.repository import ClassificationRepository
from app.extraction.models import (
    ConfidenceBand,
    ExtractedRecord,
    ScoredRecord,
)
from app.extraction.repository import ExtractionRepository
from app.ingestion.repository import JobRepository
from app.main import app
from app.review.models import ReviewStatus
from app.review.repository import ReviewRepository
from fastapi.testclient import TestClient

client = TestClient(app)


def _create_sample_scored_record(
    value: str = "1,250",
    label: str = "Operating Expenses / SBC",
    page: int = 12,
    confidence_band: ConfidenceBand = ConfidenceBand.auto_accepted,
    confidence_score: float = 0.98,
    status: str = "ok",
    error_detail: str | None = None,
) -> ScoredRecord:
    return ScoredRecord(
        record=ExtractedRecord(
            value=value,
            label=label,
            page=page,
            bbox={"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 250.0},
            source_file="test_10k.pdf",
        ),
        confidence_score=confidence_score,
        confidence_band=confidence_band,
        flags=["valid_number"],
        status=status,  # type: ignore[arg-type]
        error_detail=error_detail,
    )


def test_get_review_items_from_classified_records_200(tmp_path: Path) -> None:
    job_repo = JobRepository(data_dir=tmp_path)
    job = job_repo.save_job(
        filename="test_10k.pdf",
        content=b"%PDF-1.4 sample",
        target_metric="Adjusted EBITDA",
    )

    class_repo = ClassificationRepository(data_dir=tmp_path)
    sr1 = _create_sample_scored_record(value="1,250", confidence_band=ConfidenceBand.auto_accepted)
    sr2 = _create_sample_scored_record(
        value="450",
        label="Lease adjustments",
        page=15,
        confidence_band=ConfidenceBand.needs_review,
        confidence_score=0.82,
    )
    sr3 = _create_sample_scored_record(
        value="[Unparsed]",
        label="Table parse failure",
        page=20,
        confidence_band=ConfidenceBand.manual_required,
        confidence_score=0.2,
        status="extraction_error",
        error_detail="Docling cell parsing failed",
    )

    cr1 = ClassifiedRecord(
        record=sr1,
        normalized_label="Stock-Based Compensation",
        taxonomy_status=TaxonomyStatus.matched,
        classifier_confidence=0.99,
        is_confirmed=True,
    )
    cr2 = ClassifiedRecord(
        record=sr2,
        normalized_label="Lease Modification Costs",
        taxonomy_status=TaxonomyStatus.pending_taxonomy_confirmation,
        classifier_confidence=0.75,
        is_confirmed=False,
    )
    cr3 = ClassifiedRecord(
        record=sr3,
        normalized_label=None,
        taxonomy_status=TaxonomyStatus.pending_taxonomy_confirmation,
        classifier_confidence=None,
        is_confirmed=False,
    )

    class_repo.save_classified_records(job.job_id, [cr1, cr2, cr3])
    review_repo = ReviewRepository(data_dir=tmp_path)

    with patch("app.review.router._job_repo", job_repo), patch(
        "app.review.router._review_repo", review_repo
    ):
        response = client.get(f"/review/{job.job_id}/items")

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job.job_id
    assert data["total_items"] == 3

    items = data["items"]
    # Item 1: Auto accepted + matched
    assert items[0]["id"] == f"{job.job_id}_0"
    assert items[0]["value"] == "1,250"
    assert items[0]["page"] == 12
    assert items[0]["normalized_label"] == "Stock-Based Compensation"
    assert items[0]["taxonomy_status"] == "matched"
    assert items[0]["status"] == ReviewStatus.auto_accepted.value

    # Item 2: Pending taxonomy confirmation
    assert items[1]["id"] == f"{job.job_id}_1"
    assert items[1]["value"] == "450"
    assert items[1]["page"] == 15
    assert items[1]["taxonomy_status"] == "pending_taxonomy_confirmation"
    assert items[1]["status"] == ReviewStatus.pending_taxonomy_confirmation.value

    # Item 3: Extraction error takes precedence
    assert items[2]["id"] == f"{job.job_id}_2"
    assert items[2]["value"] == "[Unparsed]"
    assert items[2]["page"] == 20
    assert items[2]["status"] == ReviewStatus.extraction_error.value
    assert items[2]["error_detail"] == "Docling cell parsing failed"


def test_get_review_items_fallback_to_scored_records_200(tmp_path: Path) -> None:
    job_repo = JobRepository(data_dir=tmp_path)
    job = job_repo.save_job(
        filename="test_10k.pdf",
        content=b"%PDF-1.4 sample",
        target_metric="Adjusted EBITDA",
    )

    ext_repo = ExtractionRepository(data_dir=tmp_path)
    sr1 = _create_sample_scored_record(
        value="500",
        confidence_band=ConfidenceBand.needs_review,
        confidence_score=0.78,
    )
    ext_repo.save_scored_records(job.job_id, [sr1])

    review_repo = ReviewRepository(data_dir=tmp_path)

    with patch("app.review.router._job_repo", job_repo), patch(
        "app.review.router._review_repo", review_repo
    ):
        response = client.get(f"/review/{job.job_id}/items")

    assert response.status_code == 200
    data = response.json()
    assert data["total_items"] == 1
    assert data["items"][0]["value"] == "500"
    assert data["items"][0]["normalized_label"] is None
    assert data["items"][0]["status"] == ReviewStatus.needs_review.value


def test_get_review_items_job_not_found_404(tmp_path: Path) -> None:
    job_repo = JobRepository(data_dir=tmp_path)
    review_repo = ReviewRepository(data_dir=tmp_path)

    with patch("app.review.router._job_repo", job_repo), patch(
        "app.review.router._review_repo", review_repo
    ):
        response = client.get("/review/unknown-job-id/items")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_get_review_items_records_not_found_404(tmp_path: Path) -> None:
    job_repo = JobRepository(data_dir=tmp_path)
    job = job_repo.save_job(
        filename="test_10k.pdf",
        content=b"%PDF-1.4 sample",
        target_metric="Adjusted EBITDA",
    )
    review_repo = ReviewRepository(data_dir=tmp_path)

    with patch("app.review.router._job_repo", job_repo), patch(
        "app.review.router._review_repo", review_repo
    ):
        response = client.get(f"/review/{job.job_id}/items")

    assert response.status_code == 404
    assert response.json()["detail"] == "No extraction records found for job"
