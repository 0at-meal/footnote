"""
Unit tests for app.review.repository.
"""

from pathlib import Path

from app.classification.models import ClassifiedRecord, TaxonomyStatus
from app.classification.repository import ClassificationRepository
from app.extraction.models import (
    ConfidenceBand,
    ExtractedRecord,
    ScoredRecord,
)
from app.ingestion.repository import JobRepository
from app.review.models import ReviewStatus
from app.review.repository import ReviewRepository


def test_from_classified_records_auto_accepted_matched_is_locked(
    tmp_path: Path,
) -> None:
    """
    Test B-6 / Ticket B-4: When confidence_band == auto_accepted AND taxonomy_status == matched,
    the review item status is initialized as locked immediately.
    """
    job_repo = JobRepository(data_dir=tmp_path)
    job = job_repo.save_job(
        filename="test_filing.pdf",
        content=b"%PDF-1.4 sample",
        target_metric="Adjusted EBITDA",
    )
    class_repo = ClassificationRepository(data_dir=tmp_path)

    sr_auto = ScoredRecord(
        record=ExtractedRecord(
            value="1,500",
            label="Operating Expenses / Stock-Based Compensation",
            page=1,
            bbox={"x0": 100, "y0": 100, "x1": 200, "y1": 200},
            source_file="test_filing.pdf",
            is_reconciliation_candidate=True,
        ),
        confidence_score=0.98,
        confidence_band=ConfidenceBand.auto_accepted,
        flags=["value_is_numeric"],
        status="ok",
        is_reconciliation_candidate=True,
    )
    cr_auto = ClassifiedRecord(
        record=sr_auto,
        normalized_label="Stock-Based Compensation",
        taxonomy_status=TaxonomyStatus.matched,
        classifier_confidence=0.99,
        is_confirmed=True,
    )

    sr_pending = ScoredRecord(
        record=ExtractedRecord(
            value="200",
            label="Custom Non-GAAP Charge",
            page=1,
            bbox={"x0": 100, "y0": 250, "x1": 200, "y1": 300},
            source_file="test_filing.pdf",
            is_reconciliation_candidate=True,
        ),
        confidence_score=0.88,
        confidence_band=ConfidenceBand.needs_review,
        flags=[],
        status="ok",
        is_reconciliation_candidate=True,
    )
    cr_pending = ClassifiedRecord(
        record=sr_pending,
        normalized_label=None,
        taxonomy_status=TaxonomyStatus.pending_taxonomy_confirmation,
        classifier_confidence=0.70,
        is_confirmed=False,
    )

    class_repo.save_classified_records(job.job_id, [cr_auto, cr_pending])

    review_repo = ReviewRepository(data_dir=tmp_path)
    items = review_repo.get_review_items(job.job_id)

    assert items is not None
    assert len(items) == 2

    auto_item = next(i for i in items if i.value == "1,500")
    assert auto_item.status == ReviewStatus.locked
    assert auto_item.confidence_band == ConfidenceBand.auto_accepted
    assert auto_item.taxonomy_status == "matched"

    pending_item = next(i for i in items if i.value == "200")
    assert pending_item.status == ReviewStatus.pending_taxonomy_confirmation
