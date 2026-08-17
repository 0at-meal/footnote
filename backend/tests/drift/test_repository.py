"""
Unit tests for DriftRepository (Feature 7, Step 2).

Governed by CONSTITUTION §1.1 (mypy --strict), §1.9 (atomic persistence).
"""

from pathlib import Path

from app.drift.models import DriftComparisonResult, DriftFlag
from app.drift.repository import DriftRepository


def test_drift_repository_saves_and_retrieves_flags(tmp_path: Path) -> None:
    repo = DriftRepository(data_dir=tmp_path)
    job_id = "test_job_1"

    flag = DriftFlag(
        flag_id="flag_1",
        job_id=job_id,
        entity="ACME",
        target_metric="Adjusted EBITDA",
        filing_year=2023,
        added_labels=["Legal Settlement"],
        removed_labels=["Restructuring"],
        prior_node_id="node_2022",
        created_at="2026-08-17T12:00:00Z",
    )

    dest = repo.save_drift_flags(job_id, [flag])
    assert dest.exists()

    loaded = repo.get_drift_flags(job_id)
    assert len(loaded) == 1
    assert loaded[0].flag_id == "flag_1"
    assert loaded[0].added_labels == ["Legal Settlement"]
    assert loaded[0].removed_labels == ["Restructuring"]


def test_drift_repository_returns_empty_list_for_missing_job(tmp_path: Path) -> None:
    repo = DriftRepository(data_dir=tmp_path)
    loaded = repo.get_drift_flags("non_existent_job")
    assert loaded == []


def test_drift_repository_saves_and_retrieves_comparison_result(tmp_path: Path) -> None:
    repo = DriftRepository(data_dir=tmp_path)
    job_id = "test_job_2"

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

    dest = repo.save_comparison_result(job_id, comparison)
    assert dest.exists()

    loaded = repo.get_comparison_result(job_id)
    assert loaded is not None
    assert loaded.is_baseline is True
    assert loaded.entity == "ACME"
    assert loaded.unchanged_labels == ["Stock-Based Compensation"]
