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


def test_content_hash_id_stability_across_shuffled_order(tmp_path: Path) -> None:
    """Ticket 4.1: Review item IDs are stable content hashes regardless of input order."""
    repo = ReviewRepository(data_dir=tmp_path)
    sr1 = ScoredRecord(
        record=ExtractedRecord(
            value="100",
            label="Item A",
            page=1,
            bbox={"x0": 50, "y0": 50, "x1": 150, "y1": 100},
            source_file="doc.pdf",
            is_reconciliation_candidate=True,
        ),
        confidence_score=0.98,
        confidence_band=ConfidenceBand.auto_accepted,
        flags=[],
        status="ok",
        is_reconciliation_candidate=True,
    )
    sr2 = ScoredRecord(
        record=ExtractedRecord(
            value="200",
            label="Item B",
            page=2,
            bbox={"x0": 60, "y0": 70, "x1": 160, "y1": 120},
            source_file="doc.pdf",
            is_reconciliation_candidate=True,
        ),
        confidence_score=0.85,
        confidence_band=ConfidenceBand.needs_review,
        flags=[],
        status="ok",
        is_reconciliation_candidate=True,
    )

    items_forward = repo._from_scored_records("job_hash_test", [sr1, sr2])
    items_reversed = repo._from_scored_records("job_hash_test", [sr2, sr1])

    forward_map = {item.value: item.id for item in items_forward}
    reversed_map = {item.value: item.id for item in items_reversed}

    assert forward_map["100"] == reversed_map["100"]
    assert forward_map["200"] == reversed_map["200"]
    assert forward_map["100"] != forward_map["200"]
