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
