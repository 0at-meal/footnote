"""
Integration tests for Drift API router (Feature 7, Steps 2, 3, 4).

Governed by CONSTITUTION §1.1 (mypy --strict), §1.3 (Pydantic models), spec AC-1, AC-8, AC-9, AC-10, EC-10.
"""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app.drift.comparator import compare_metric_components
from app.drift.graph import HistoricalDriftGraph
from app.drift.models import DriftComparisonResult, DriftFlag
from app.drift.repository import DriftRepository
from app.drift.router import (
    get_drift_graph,
    get_drift_repository,
    get_job_repository,
    get_review_repository,
)
from app.extraction.models import ConfidenceBand
from app.ingestion.repository import JobRepository
from app.main import app
from app.review.models import ReviewItem, ReviewStatus
from app.review.repository import ReviewRepository
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    drift_repo = DriftRepository(data_dir=tmp_path)
    job_repo = JobRepository(data_dir=tmp_path)
    review_repo = ReviewRepository(data_dir=tmp_path)

    app.dependency_overrides[get_drift_repository] = lambda: drift_repo
    app.dependency_overrides[get_job_repository] = lambda: job_repo
    app.dependency_overrides[get_review_repository] = lambda: review_repo

    yield TestClient(app)

    app.dependency_overrides.clear()


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


def test_get_drift_flags_success_with_flags(tmp_path: Path, client: TestClient) -> None:
    drift_repo = DriftRepository(data_dir=tmp_path)
    job_id = "job_with_drift"

    flag = DriftFlag(
        flag_id="flag_123",
        job_id=job_id,
        entity="ACME",
        target_metric="Adjusted EBITDA",
        filing_year=2023,
        added_labels=["Legal Settlement"],
        removed_labels=["Restructuring Charges"],
        prior_node_id="node_2022",
        created_at="2026-08-17T12:00:00Z",
    )
    drift_repo.save_drift_flags(job_id, [flag])

    comparison = DriftComparisonResult(
        entity="ACME",
        target_metric="Adjusted EBITDA",
        filing_year=2023,
        is_baseline=False,
        added_labels=["Legal Settlement"],
        removed_labels=["Restructuring Charges"],
        unchanged_labels=["Stock-Based Compensation"],
        current_labels=["Legal Settlement", "Stock-Based Compensation"],
        prior_node_id="node_2022",
        has_discrepancy=True,
    )
    drift_repo.save_comparison_result(job_id, comparison)

    response = client.get(f"/drift/jobs/{job_id}/flags")
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id
    assert data["entity"] == "ACME"
    assert data["target_metric"] == "Adjusted EBITDA"
    assert data["filing_year"] == 2023
    assert data["is_baseline"] is False
    assert data["total_flags"] == 1
    assert len(data["flags"]) == 1
    assert data["flags"][0]["flag_id"] == "flag_123"
    assert data["flags"][0]["added_labels"] == ["Legal Settlement"]
    assert data["flags"][0]["removed_labels"] == ["Restructuring Charges"]


def test_get_drift_flags_empty_for_baseline_or_no_discrepancies(
    tmp_path: Path, client: TestClient
) -> None:
    drift_repo = DriftRepository(data_dir=tmp_path)
    job_id = "job_baseline"

    comparison = DriftComparisonResult(
        entity="ACME",
        target_metric="Adjusted EBITDA",
        filing_year=2022,
        is_baseline=True,
        added_labels=[],
        removed_labels=[],
        unchanged_labels=["Stock-Based Compensation"],
        current_labels=["Stock-Based Compensation"],
        prior_node_id=None,
        has_discrepancy=False,
    )
    drift_repo.save_comparison_result(job_id, comparison)

    response = client.get(f"/drift/jobs/{job_id}/flags")
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id
    assert data["is_baseline"] is True
    assert data["total_flags"] == 0
    assert data["flags"] == []


def test_get_drift_flags_alias_endpoint(tmp_path: Path, client: TestClient) -> None:
    drift_repo = DriftRepository(data_dir=tmp_path)
    job_id = "job_alias_test"

    flag = DriftFlag(
        flag_id="flag_999",
        job_id=job_id,
        entity="BETA",
        target_metric="Adjusted EBITDA",
        filing_year=2024,
        added_labels=["M&A Costs"],
        removed_labels=[],
        prior_node_id="node_2023",
        created_at="2026-08-17T12:00:00Z",
    )
    drift_repo.save_drift_flags(job_id, [flag])

    response = client.get(f"/drift/flags/{job_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["total_flags"] == 1
    assert data["flags"][0]["flag_id"] == "flag_999"


def test_get_drift_flags_not_found(client: TestClient) -> None:
    response = client.get("/drift/jobs/unknown_job_id/flags")
    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()


def test_get_metric_history_and_export_graph(client: TestClient) -> None:
    graph = HistoricalDriftGraph()
    n1, _ = graph.apply_comparison(
        compare_metric_components(
            "GAMMA", "Adjusted EBITDA", 2022, ["LabelA", "LabelB"], None
        )
    )
    _n2, _e2 = graph.apply_comparison(
        compare_metric_components(
            "GAMMA", "Adjusted EBITDA", 2023, ["LabelA", "LabelB", "LabelC"], n1
        )
    )
    app.dependency_overrides[get_drift_graph] = lambda: graph

    # 1. Test history endpoint
    res_history = client.get("/drift/history/GAMMA/Adjusted EBITDA")
    assert res_history.status_code == 200
    data_history = res_history.json()
    assert data_history["entity"] == "GAMMA"
    assert data_history["target_metric"] == "Adjusted EBITDA"
    assert data_history["total_definitions"] == 2
    assert len(data_history["definitions"]) == 2
    assert len(data_history["edges"]) == 1

    # 2. Test graph export endpoint
    res_graph = client.get("/drift/graph?entity=GAMMA")
    assert res_graph.status_code == 200
    data_graph = res_graph.json()
    assert data_graph["total_nodes"] == 2
    assert data_graph["total_edges"] == 1
    assert data_graph["nodes"][0]["entity"] == "GAMMA"


def test_post_evaluate_job_endpoint(tmp_path: Path, client: TestClient) -> None:
    job_repo = JobRepository(data_dir=tmp_path)
    review_repo = ReviewRepository(data_dir=tmp_path)

    # 1. 2022 baseline evaluation via API
    job_2022 = job_repo.save_job("ACME_2022.pdf", b"%PDF-2022", "Adjusted EBITDA")
    _seed_review_items(review_repo, job_2022.job_id, ["Depreciation", "SBC"])

    res_1 = client.post(
        f"/drift/jobs/{job_2022.job_id}/evaluate",
        json={"entity": "ACME", "filing_year": 2022},
    )
    assert res_1.status_code == 200
    d1 = res_1.json()
    assert d1["status"] == "evaluated"
    assert d1["is_baseline"] is True
    assert d1["has_discrepancy"] is False
    assert d1["flag"] is None
    assert d1["active_definition_node"] is not None

    # 2. 2023 redefinition evaluation via API
    job_2023 = job_repo.save_job("ACME_2023.pdf", b"%PDF-2023", "Adjusted EBITDA")
    _seed_review_items(
        review_repo, job_2023.job_id, ["Depreciation", "SBC", "Litigation"]
    )

    res_2 = client.post(
        f"/drift/jobs/{job_2023.job_id}/evaluate",
        json={"entity": "ACME", "filing_year": 2023},
    )
    assert res_2.status_code == 200
    d2 = res_2.json()
    assert d2["status"] == "evaluated"
    assert d2["is_baseline"] is False
    assert d2["has_discrepancy"] is True
    assert d2["flag"] is not None
    assert d2["flag"]["added_labels"] == ["Litigation"]

    # 3. Query flags endpoint to verify persistence (AC-8, AC-10)
    res_flags = client.get(f"/drift/jobs/{job_2023.job_id}/flags")
    assert res_flags.status_code == 200
    d_flags = res_flags.json()
    assert d_flags["total_flags"] == 1
    assert d_flags["flags"][0]["added_labels"] == ["Litigation"]


def test_mark_relabeled_endpoint(tmp_path: Path, client: TestClient) -> None:
    drift_repo = DriftRepository(data_dir=tmp_path)
    job_id = "job_relabel"

    from app.drift.models import RelabeledComponent

    flag = DriftFlag(
        flag_id="flag_rel",
        job_id=job_id,
        entity="CORP",
        target_metric="Adjusted EBITDA",
        filing_year=2024,
        added_labels=[],
        removed_labels=[],
        relabeled_components=[
            RelabeledComponent(
                old_label="Stock-based compensation",
                new_label="Share-based compensation",
                similarity_score=0.85,
                is_confirmed=False,
            )
        ],
        prior_node_id="node_2023",
        created_at="2026-08-30T12:00:00Z",
    )
    drift_repo.save_drift_flags(job_id, [flag])

    res = client.post(
        f"/drift/jobs/{job_id}/mark-relabeled",
        json={
            "old_standard_label": "Stock-based compensation",
            "new_standard_label": "Share-based compensation",
            "justification": "Confirmed identical substance",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data["relabeled_components"]) == 1
    assert data["relabeled_components"][0]["is_confirmed"] is True
    assert (
        data["relabeled_components"][0]["justification"]
        == "Confirmed identical substance"
    )


def test_drift_router_dependency_overrides_isolation() -> None:
    """Ticket R5.2: Verify drift endpoints work with app.dependency_overrides for isolation."""
    mock_drift_repo = MagicMock()
    mock_drift_repo.get_drift_flags.return_value = []
    mock_drift_repo.get_comparison_result.return_value = None

    mock_job_repo = MagicMock()
    mock_job = MagicMock()
    mock_job.target_metric = "Adjusted EBITDA"
    mock_job.entity = "TEST_ENTITY"
    mock_job.filing_year = 2023
    mock_job_repo.get_job.return_value = mock_job

    app.dependency_overrides[get_drift_repository] = lambda: mock_drift_repo
    app.dependency_overrides[get_job_repository] = lambda: mock_job_repo

    try:
        test_client = TestClient(app)
        res = test_client.get("/drift/jobs/override_job/flags")
        assert res.status_code == 200
        data = res.json()
        assert data["job_id"] == "override_job"
        assert data["entity"] == "TEST_ENTITY"
        mock_drift_repo.get_drift_flags.assert_called_once_with("override_job")
        mock_job_repo.get_job.assert_called_once_with("override_job")
    finally:
        app.dependency_overrides.clear()

