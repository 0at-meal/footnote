"""
Unit and integration tests for review actions (Feature 5 Step 3).

Validates:
- Confirm action locks item, clears flag, and persists (AC-4, AC-5, AC-7)
- Confirm rejects extraction_error items (EC-1)
- Confirm on pending_taxonomy_confirmation requires add_to_taxonomy confirmation (EC-5)
- Edit modifies value and label without auto-confirming (AC-8, AC-9)
- Edit rejects empty label (EC-4)
- Edit recovers extraction_error items (EC-1)
- Flag transitions item to flagged; rejected on locked items (AC-7, EC-8)
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
from app.ingestion.repository import JobRepository
from app.main import app
from app.review.models import ReviewStatus
from app.review.repository import ReviewRepository
from fastapi.testclient import TestClient

client = TestClient(app)


def _setup_job_with_records(tmp_path: Path) -> tuple[JobRepository, ReviewRepository, str]:
    job_repo = JobRepository(data_dir=tmp_path)
    job = job_repo.save_job(
        filename="test_filing.pdf",
        content=b"%PDF-1.4 sample",
        target_metric="Adjusted EBITDA",
    )

    class_repo = ClassificationRepository(data_dir=tmp_path)

    # Record 1: Auto accepted + matched
    sr1 = ScoredRecord(
        record=ExtractedRecord(
            value="1,000",
            label="Operating Expenses / SBC",
            page=1,
            bbox={"x0": 100, "y0": 100, "x1": 200, "y1": 200},
            source_file="test_filing.pdf",
        ),
        confidence_score=0.98,
        confidence_band=ConfidenceBand.auto_accepted,
        flags=[],
        status="ok",
    )
    cr1 = ClassifiedRecord(
        record=sr1,
        normalized_label="Stock-Based Compensation",
        taxonomy_status=TaxonomyStatus.matched,
        classifier_confidence=0.99,
        is_confirmed=True,
    )

    # Record 2: Pending taxonomy confirmation
    sr2 = ScoredRecord(
        record=ExtractedRecord(
            value="250",
            label="Special litigation contingency",
            page=2,
            bbox={"x0": 100, "y0": 300, "x1": 200, "y1": 400},
            source_file="test_filing.pdf",
        ),
        confidence_score=0.88,
        confidence_band=ConfidenceBand.needs_review,
        flags=[],
        status="ok",
    )
    cr2 = ClassifiedRecord(
        record=sr2,
        normalized_label=None,
        taxonomy_status=TaxonomyStatus.pending_taxonomy_confirmation,
        classifier_confidence=0.70,
        is_confirmed=False,
    )

    # Record 3: Extraction error
    sr3 = ScoredRecord(
        record=ExtractedRecord(
            value="[ERROR]",
            label="Corrupted table row",
            page=3,
            bbox={"x0": 0, "y0": 0, "x1": 10, "y1": 10},
            source_file="test_filing.pdf",
        ),
        confidence_score=0.1,
        confidence_band=ConfidenceBand.manual_required,
        flags=["corrupted"],
        status="extraction_error",
        error_detail="Docling cell parsing failed",
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
    return job_repo, review_repo, job.job_id


def test_edit_item_success(tmp_path: Path) -> None:
    job_repo, review_repo, job_id = _setup_job_with_records(tmp_path)
    item_id = f"{job_id}_0"

    with patch("app.review.router._job_repo", job_repo), patch(
        "app.review.router._review_repo", review_repo
    ):
        res = client.patch(
            f"/review/{job_id}/items/{item_id}/edit",
            json={"value": "1,050", "label": "Operating Expenses / SBC Adjusted"},
        )

    assert res.status_code == 200
    data = res.json()
    assert data["value"] == "1,050"
    assert data["label"] == "Operating Expenses / SBC Adjusted"
    # Ensure status did NOT auto-confirm (AC-8)
    assert data["status"] == ReviewStatus.auto_accepted.value
    # Frozen fields remain untouched (AC-9)
    assert data["page"] == 1
    assert data["source_file"] == "test_filing.pdf"


def test_edit_item_rejects_empty_label(tmp_path: Path) -> None:
    job_repo, review_repo, job_id = _setup_job_with_records(tmp_path)
    item_id = f"{job_id}_0"

    with patch("app.review.router._job_repo", job_repo), patch(
        "app.review.router._review_repo", review_repo
    ):
        res = client.patch(
            f"/review/{job_id}/items/{item_id}/edit",
            json={"label": "   "},
        )

    assert res.status_code == 400
    assert "cannot be empty" in res.json()["detail"].lower()


def test_edit_recovers_extraction_error(tmp_path: Path) -> None:
    job_repo, review_repo, job_id = _setup_job_with_records(tmp_path)
    item_id = f"{job_id}_2"  # Extraction error item

    with patch("app.review.router._job_repo", job_repo), patch(
        "app.review.router._review_repo", review_repo
    ):
        res = client.patch(
            f"/review/{job_id}/items/{item_id}/edit",
            json={"value": "500", "label": "Recovered row label"},
        )

    assert res.status_code == 200
    data = res.json()
    assert data["value"] == "500"
    assert data["status"] == ReviewStatus.manual_required.value
    assert data["error_detail"] is None


def test_confirm_item_locks_record(tmp_path: Path) -> None:
    job_repo, review_repo, job_id = _setup_job_with_records(tmp_path)
    item_id = f"{job_id}_0"

    with patch("app.review.router._job_repo", job_repo), patch(
        "app.review.router._review_repo", review_repo
    ):
        # First flag it
        flag_res = client.post(f"/review/{job_id}/items/{item_id}/flag")
        assert flag_res.status_code == 200
        assert flag_res.json()["status"] == ReviewStatus.flagged.value

        # Confirm should clear flag and lock (AC-4, AC-7)
        confirm_res = client.post(
            f"/review/{job_id}/items/{item_id}/confirm",
            json={"add_to_taxonomy": False},
        )

    assert confirm_res.status_code == 200
    assert confirm_res.json()["status"] == ReviewStatus.locked.value


def test_confirm_rejects_extraction_error_item(tmp_path: Path) -> None:
    job_repo, review_repo, job_id = _setup_job_with_records(tmp_path)
    item_id = f"{job_id}_2"  # extraction_error

    with patch("app.review.router._job_repo", job_repo), patch(
        "app.review.router._review_repo", review_repo
    ):
        res = client.post(
            f"/review/{job_id}/items/{item_id}/confirm",
            json={"add_to_taxonomy": False},
        )

    assert res.status_code == 400
    assert "extraction error" in res.json()["detail"].lower()


def test_confirm_pending_taxonomy_requires_acceptance(tmp_path: Path) -> None:
    job_repo, review_repo, job_id = _setup_job_with_records(tmp_path)
    item_id = f"{job_id}_1"  # pending_taxonomy_confirmation

    with patch("app.review.router._job_repo", job_repo), patch(
        "app.review.router._review_repo", review_repo
    ):
        # 1. Reject if add_to_taxonomy is False
        res1 = client.post(
            f"/review/{job_id}/items/{item_id}/confirm",
            json={"add_to_taxonomy": False},
        )
        assert res1.status_code == 400
        assert "taxonomy" in res1.json()["detail"].lower()

        # 2. Succeed if add_to_taxonomy is True
        res2 = client.post(
            f"/review/{job_id}/items/{item_id}/confirm",
            json={"add_to_taxonomy": True},
        )
        assert res2.status_code == 200
        data = res2.json()
        assert data["status"] == ReviewStatus.locked.value
        assert data["taxonomy_status"] == "matched"


def test_flag_item_and_rejection_when_locked(tmp_path: Path) -> None:
    job_repo, review_repo, job_id = _setup_job_with_records(tmp_path)
    item_id = f"{job_id}_0"

    with patch("app.review.router._job_repo", job_repo), patch(
        "app.review.router._review_repo", review_repo
    ):
        # Flag item
        res1 = client.post(f"/review/{job_id}/items/{item_id}/flag")
        assert res1.status_code == 200
        assert res1.json()["status"] == ReviewStatus.flagged.value

        # Confirm item to lock it
        res_confirm = client.post(
            f"/review/{job_id}/items/{item_id}/confirm",
            json={"add_to_taxonomy": False},
        )
        assert res_confirm.status_code == 200
        assert res_confirm.json()["status"] == ReviewStatus.locked.value

        # Flag on locked item must be rejected (AC-7)
        res_flag_locked = client.post(f"/review/{job_id}/items/{item_id}/flag")
        assert res_flag_locked.status_code == 400
        assert "cannot flag a locked item" in res_flag_locked.json()["detail"].lower()


def test_unlock_item_success_and_rejection_when_not_locked(tmp_path: Path) -> None:
    job_repo, review_repo, job_id = _setup_job_with_records(tmp_path)
    item_id = f"{job_id}_0"

    with patch("app.review.router._job_repo", job_repo), patch(
        "app.review.router._review_repo", review_repo
    ):
        # 1. Unlock when not locked -> 400
        res_fail = client.post(f"/review/{job_id}/items/{item_id}/unlock")
        assert res_fail.status_code == 400
        assert "not currently locked" in res_fail.json()["detail"].lower()

        # 2. Confirm to lock
        res_confirm = client.post(
            f"/review/{job_id}/items/{item_id}/confirm",
            json={"add_to_taxonomy": False},
        )
        assert res_confirm.status_code == 200
        assert res_confirm.json()["status"] == ReviewStatus.locked.value

        # 3. Explicit unlock -> 200, status returns to auto_accepted
        res_unlock = client.post(f"/review/{job_id}/items/{item_id}/unlock")
        assert res_unlock.status_code == 200
        assert res_unlock.json()["status"] == ReviewStatus.auto_accepted.value


def test_locked_status_persists_across_restart(tmp_path: Path) -> None:
    job_repo, review_repo_1, job_id = _setup_job_with_records(tmp_path)
    item_id = f"{job_id}_0"

    with patch("app.review.router._job_repo", job_repo), patch(
        "app.review.router._review_repo", review_repo_1
    ):
        # Confirm and lock item
        res = client.post(
            f"/review/{job_id}/items/{item_id}/confirm",
            json={"add_to_taxonomy": False},
        )
        assert res.status_code == 200
        assert res.json()["status"] == ReviewStatus.locked.value

    # Simulate fresh backend instantiation / restart (EC-6)
    review_repo_2 = ReviewRepository(data_dir=tmp_path)
    with patch("app.review.router._job_repo", job_repo), patch(
        "app.review.router._review_repo", review_repo_2
    ):
        items_res = client.get(f"/review/{job_id}/items")
        assert items_res.status_code == 200
        items = items_res.json()["items"]
        locked_item = next(it for it in items if it["id"] == item_id)
        assert locked_item["status"] == ReviewStatus.locked.value


def test_protect_locked_items_against_extraction_rerun(tmp_path: Path) -> None:
    job_repo, review_repo, job_id = _setup_job_with_records(tmp_path)
    item_id = f"{job_id}_0"

    with patch("app.review.router._job_repo", job_repo), patch(
        "app.review.router._review_repo", review_repo
    ):
        # Lock item 0
        client.post(f"/review/{job_id}/items/{item_id}/confirm", json={"add_to_taxonomy": False})

    # Create new candidate items simulating re-extraction (EC-10)
    items = review_repo.get_review_items(job_id)
    assert items is not None
    modified_candidates = [
        item.model_copy(update={"value": "99,999", "label": "OVERWRITTEN_LABEL"})
        for item in items
    ]

    # Merge with protection
    merged = review_repo.protect_locked_items(job_id, modified_candidates)
    locked_item = next(it for it in merged if it.id == item_id)

    # Locked item retained original confirmed state byte-identically (AC-5, EC-10)
    assert locked_item.value == "1,000"
    assert locked_item.label == "Operating Expenses / SBC"
    assert locked_item.status == ReviewStatus.locked


def test_review_repository_propagates_target_metric_and_table_name(tmp_path: Path) -> None:
    """Ticket 2.3: Verify _from_classified_records propagates candidate and table_name."""
    repo = ReviewRepository(data_dir=tmp_path)

    sr1 = ScoredRecord(
        record=ExtractedRecord(
            value="5,000",
            label="Stock-based compensation",
            page=1,
            bbox={"x0": 10, "y0": 20, "x1": 100, "y1": 50},
            source_file="filing.pdf",
        ),
        confidence_score=0.98,
        confidence_band=ConfidenceBand.auto_accepted,
        flags=[],
        table_name="Adjusted EBITDA Reconciliation",
        status="ok",
    )
    sr2 = ScoredRecord(
        record=ExtractedRecord(
            value="25,000",
            label="Accounts payable",
            page=1,
            bbox={"x0": 10, "y0": 60, "x1": 100, "y1": 90},
            source_file="filing.pdf",
        ),
        confidence_score=0.95,
        confidence_band=ConfidenceBand.auto_accepted,
        flags=[],
        table_name="Consolidated Balance Sheets",
        status="ok",
    )

    cr1 = ClassifiedRecord(
        record=sr1,
        normalized_label="Stock-Based Compensation",
        taxonomy_status=TaxonomyStatus.matched,
        classifier_confidence=0.96,
        is_confirmed=True,
        is_target_metric_candidate=True,
    )
    cr2 = ClassifiedRecord(
        record=sr2,
        normalized_label=None,
        taxonomy_status=TaxonomyStatus.pending_taxonomy_confirmation,
        classifier_confidence=None,
        is_confirmed=False,
        is_target_metric_candidate=False,
    )

    items = repo._from_classified_records("job_123", [cr1, cr2])
    assert len(items) == 2

    assert items[0].id == "job_123_0"
    assert items[0].is_target_metric_candidate is True
    assert items[0].table_name == "Adjusted EBITDA Reconciliation"

    assert items[1].id == "job_123_1"
    assert items[1].is_target_metric_candidate is False
    assert items[1].table_name == "Consolidated Balance Sheets"

    # Save and reload
    repo.save_review_items("job_123", items)
    loaded = repo.get_review_items("job_123")
    assert loaded is not None
    assert len(loaded) == 2
    assert loaded[0].is_target_metric_candidate is True
    assert loaded[0].table_name == "Adjusted EBITDA Reconciliation"
    assert loaded[1].is_target_metric_candidate is False
    assert loaded[1].table_name == "Consolidated Balance Sheets"


def test_confirm_batch_locks_target_candidates_and_skips_errors(tmp_path: Path) -> None:
    """Ticket 4.1 & 4.3: confirm_batch locks candidates, adds pending taxonomy, and skips extraction errors."""
    job_repo, review_repo, job_id = _setup_job_with_records(tmp_path)
    # _setup_job_with_records creates:
    # item 0: matched SBC (candidate=True)
    # item 1: pending litigation (candidate=True)
    # item 2: extraction error (candidate=True)

    items, locked_ids, err = review_repo.confirm_batch(
        job_id=job_id,
        target_candidates_only=True,
        auto_add_pending_taxonomy=True,
    )
    assert err is None
    # 2 items should be locked (item 0 and item 1); item 2 has extraction_error so it's skipped
    assert len(locked_ids) == 2
    assert f"{job_id}_0" in locked_ids
    assert f"{job_id}_1" in locked_ids
    assert f"{job_id}_2" not in locked_ids

    # Item 1 should have had its taxonomy status updated to matched
    item1 = next(it for it in items if it.id == f"{job_id}_1")
    assert item1.status == ReviewStatus.locked
    assert item1.taxonomy_status == "matched"

    # Item 2 should remain extraction_error
    item2 = next(it for it in items if it.id == f"{job_id}_2")
    assert item2.status == ReviewStatus.extraction_error


def test_confirm_batch_router_endpoint(tmp_path: Path) -> None:
    """Ticket 4.3: POST /review/{job_id}/confirm-batch integration test."""
    job_repo, review_repo, job_id = _setup_job_with_records(tmp_path)

    with patch("app.review.router._job_repo", job_repo), patch(
        "app.review.router._review_repo", review_repo
    ):
        res = client.post(
            f"/review/{job_id}/confirm-batch",
            json={"target_candidates_only": True, "auto_add_pending_taxonomy": True},
        )

    assert res.status_code == 200
    data = res.json()
    assert data["job_id"] == job_id
    assert data["total_locked"] == 2
    assert f"{job_id}_0" in data["locked_item_ids"]
    assert f"{job_id}_1" in data["locked_item_ids"]
    assert f"{job_id}_2" not in data["locked_item_ids"]

