"""
Integration tests for Drift API router (Feature 7, Steps 2 & 3).

Governed by CONSTITUTION §1.1 (mypy --strict), §1.3 (Pydantic models), spec AC-8, AC-9, EC-10.
"""

from pathlib import Path

import pytest
from app.drift.comparator import compare_metric_components
from app.drift.graph import HistoricalDriftGraph
from app.drift.models import DriftComparisonResult, DriftFlag
from app.drift.repository import DriftRepository
from app.drift.router import (
    set_drift_graph,
    set_drift_repository,
    set_job_repository,
)
from app.ingestion.repository import JobRepository
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    drift_repo = DriftRepository(data_dir=tmp_path)
    job_repo = JobRepository(data_dir=tmp_path)
    drift_graph = HistoricalDriftGraph()

    set_drift_repository(drift_repo)
    set_job_repository(job_repo)
    set_drift_graph(drift_graph)

    return TestClient(app)


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
        compare_metric_components("GAMMA", "Adjusted EBITDA", 2022, ["LabelA", "LabelB"], None)
    )
    _n2, _e2 = graph.apply_comparison(
        compare_metric_components("GAMMA", "Adjusted EBITDA", 2023, ["LabelA", "LabelB", "LabelC"], n1)
    )
    set_drift_graph(graph)

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
