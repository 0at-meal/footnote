"""
Unit tests for app.model_compilation_service (Step 3).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.model_compilation_service import (
    get_or_compile_provenance,
    try_compile_model_on_the_fly,
)
from app.review.models import ReviewItem, ReviewStatus


def test_try_compile_model_on_the_fly_no_items(tmp_path: Path) -> None:
    """When no review items or classified records exist, returns None."""
    result = try_compile_model_on_the_fly(
        job_id="job_empty",
        data_dir=tmp_path,
        review_items=[],
        classified_records=[],
    )
    assert result is None


def test_get_or_compile_provenance_returns_existing(tmp_path: Path) -> None:
    """When provenance records already exist in repository, returns them directly."""
    mock_prov = [MagicMock(sheet_name="Reconciliation")]
    with patch("app.model_compilation_service.ModelRepository") as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.get_provenance_records.return_value = mock_prov
        mock_repo_cls.return_value = mock_repo

        records = get_or_compile_provenance(
            job_id="job_existing",
            data_dir=tmp_path,
        )
        assert records == mock_prov
        mock_repo.get_provenance_records.assert_called_once_with("job_existing")


def test_try_compile_model_on_the_fly_success(tmp_path: Path) -> None:
    """When valid confirmed review items exist, builds formula tree and generates workbook."""
    items = [
        ReviewItem(
            id="rev_1",
            value="1,000",
            label="Net Income",
            page=1,
            bbox={"x0": 10.0, "y0": 20.0, "x1": 50.0, "y1": 30.0},
            source_file="10k.pdf",
            status=ReviewStatus.locked,
            normalized_label="Net Income",
            statement_type="non_gaap_bridge",
            confidence_band="auto_accepted",
            confidence_score=0.98,
        )
    ]
    mock_prov = [MagicMock(sheet_name="Reconciliation")]
    mock_gen_result = MagicMock()
    mock_gen_result.provenance_records = mock_prov

    with patch(
        "app.model_compilation_service.read_formula_inputs_from_review"
    ) as mock_read, patch(
        "app.model_compilation_service.build_formula_tree"
    ) as mock_tree_builder, patch(
        "app.model_compilation_service.generate_workbook"
    ) as mock_gen_wb, patch(
        "app.model_compilation_service.ModelRepository"
    ) as mock_repo_cls:

        mock_batch = MagicMock()
        mock_batch.nodes = ["node1"]
        mock_read.return_value = mock_batch

        mock_tree = MagicMock()
        mock_tree.is_valid = True
        mock_tree_builder.return_value = mock_tree

        mock_gen_wb.return_value = mock_gen_result

        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        result = try_compile_model_on_the_fly(
            job_id="job_test",
            data_dir=tmp_path,
            review_items=items,
        )

        assert result == mock_prov
        mock_gen_wb.assert_called_once()
        mock_repo.save_generation_result.assert_called_once_with(
            "job_test", mock_gen_result
        )
        mock_repo.save_provenance_records.assert_called_once_with(
            "job_test", mock_prov
        )
