"""
Unit tests for evaluate_job_drift service (Feature 7, Step 4).

Governed by CONSTITUTION §1.1 (mypy --strict), spec §1, §2, §3, §4, AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, EC-1, EC-4.
"""

from pathlib import Path

import pytest
from app.drift.models import DriftEdgeType
from app.drift.repository import DriftRepository
from app.drift.service import evaluate_job_drift
from app.extraction.models import ConfidenceBand
from app.ingestion.repository import JobRepository
from app.review.models import ReviewItem, ReviewStatus
from app.review.repository import ReviewRepository


def _seed_review_items(
    review_repo: ReviewRepository,
    job_id: str,
    labels: list[str],
    status: ReviewStatus = ReviewStatus.locked,
) -> None:
    items = [
        ReviewItem(
            id=f"{job_id}_{idx}",
            value="100.0",
            label="Metric Component",
            page=1,
            bbox={"x0": 10.0, "y0": 20.0, "x1": 30.0, "y1": 40.0},
            source_file=f"{job_id}.pdf",
            confidence_band=ConfidenceBand.auto_accepted,
            confidence_score=0.99,
            normalized_label=label,
            taxonomy_status="matched",
            status=status,
        )
        for idx, label in enumerate(labels)
    ]
    review_repo.save_review_items(job_id, items)


def test_evaluate_job_drift_baseline_year(tmp_path: Path) -> None:
    drift_repo = DriftRepository(data_dir=tmp_path)
    job_repo = JobRepository(data_dir=tmp_path)
    review_repo = ReviewRepository(data_dir=tmp_path)

    # 1. Create job
    job = job_repo.save_job("ACME_2022.pdf", b"%PDF-test", "Adjusted EBITDA")
    _seed_review_items(review_repo, job.job_id, ["Depreciation", "Stock-Based Comp"])

    comp, flag, node = evaluate_job_drift(
        job_id=job.job_id,
        repo=drift_repo,
        job_repo=job_repo,
        review_repo=review_repo,
        entity="ACME",
        filing_year=2022,
    )

    assert comp is not None
    assert comp.is_baseline is True
    assert comp.has_discrepancy is False
    assert flag is None
    assert node is not None
    assert node.entity == "ACME"
    assert node.filing_year == 2022

    # Verify SQLite persistence
    graph = drift_repo.load_graph()
    assert graph.get_latest_node("ACME", "Adjusted EBITDA") is not None


def test_evaluate_job_drift_redefinition_and_continuation_flow(tmp_path: Path) -> None:
    drift_repo = DriftRepository(data_dir=tmp_path)
    job_repo = JobRepository(data_dir=tmp_path)
    review_repo = ReviewRepository(data_dir=tmp_path)

    # 1. 2022 Baseline
    job_2022 = job_repo.save_job("ACME_2022.pdf", b"%PDF-2022", "Adjusted EBITDA")
    _seed_review_items(review_repo, job_2022.job_id, ["Depreciation", "Stock-Based Comp", "Restructuring"])
    comp_1, flag_1, node_1 = evaluate_job_drift(
        job_id=job_2022.job_id,
        repo=drift_repo,
        job_repo=job_repo,
        review_repo=review_repo,
        entity="ACME",
        filing_year=2022,
    )
    assert comp_1 is not None and comp_1.is_baseline is True
    assert flag_1 is None

    # 2. 2023 Redefinition (remove Restructuring, add Legal Settlement)
    job_2023 = job_repo.save_job("ACME_2023.pdf", b"%PDF-2023", "Adjusted EBITDA")
    _seed_review_items(review_repo, job_2023.job_id, ["Depreciation", "Stock-Based Comp", "Legal Settlement"])
    comp_2, flag_2, node_2 = evaluate_job_drift(
        job_id=job_2023.job_id,
        repo=drift_repo,
        job_repo=job_repo,
        review_repo=review_repo,
        entity="ACME",
        filing_year=2023,
    )
    assert comp_2 is not None and comp_2.has_discrepancy is True
    assert flag_2 is not None
    assert flag_2.added_labels == ["Legal Settlement"]
    assert flag_2.removed_labels == ["Restructuring"]
    assert node_2 is not None
    assert node_1 is not None
    assert node_2.node_id != node_1.node_id

    # 3. 2024 Continuation (identical labels)
    job_2024 = job_repo.save_job("ACME_2024.pdf", b"%PDF-2024", "Adjusted EBITDA")
    _seed_review_items(review_repo, job_2024.job_id, ["Depreciation", "Stock-Based Comp", "Legal Settlement"])
    comp_3, flag_3, node_3 = evaluate_job_drift(
        job_id=job_2024.job_id,
        repo=drift_repo,
        job_repo=job_repo,
        review_repo=review_repo,
        entity="ACME",
        filing_year=2024,
    )
    assert comp_3 is not None and comp_3.has_discrepancy is False
    assert flag_3 is None
    assert node_3 is not None and node_3.node_id == node_2.node_id  # Node reused (AC-6)

    # 4. Verify durable graph after all steps
    graph = drift_repo.load_graph()
    history = graph.get_history("ACME", "Adjusted EBITDA")
    assert len(history) == 2  # 2 distinct definition nodes
    edges = graph.get_edges("ACME", "Adjusted EBITDA")
    assert len(edges) == 2
    assert edges[0].edge_type == DriftEdgeType.redefinition
    assert edges[1].edge_type == DriftEdgeType.continuation


def test_evaluate_job_drift_skips_when_no_locked_records(tmp_path: Path) -> None:
    drift_repo = DriftRepository(data_dir=tmp_path)
    job_repo = JobRepository(data_dir=tmp_path)
    review_repo = ReviewRepository(data_dir=tmp_path)

    job = job_repo.save_job("ACME_pending.pdf", b"%PDF-test", "Adjusted EBITDA")
    _seed_review_items(
        review_repo,
        job.job_id,
        ["Unconfirmed Label"],
        status=ReviewStatus.pending_taxonomy_confirmation,
    )

    comp, flag, node = evaluate_job_drift(
        job_id=job.job_id,
        repo=drift_repo,
        job_repo=job_repo,
        review_repo=review_repo,
    )
    assert comp is None
    assert flag is None
    assert node is None


def test_evaluate_job_drift_unknown_job_raises_error(tmp_path: Path) -> None:
    drift_repo = DriftRepository(data_dir=tmp_path)
    with pytest.raises(ValueError, match="not found"):
        evaluate_job_drift("non_existent_job_id", repo=drift_repo)
