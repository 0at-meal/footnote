"""
Unit tests for Feature 9 Evaluation Harness data models (eval/models.py).
"""

import pytest
from pydantic import ValidationError

from eval.models import (
    BenchmarkCorpusManifest,
    BenchmarkFiling,
    BenchmarkFilingMetadata,
    CorpusValidationResult,
    GroundTruthBbox,
    GroundTruthItem,
)


def test_ground_truth_bbox_valid() -> None:
    bbox = GroundTruthBbox(x0=100.0, y0=200.0, x1=500.0, y1=600.0)
    assert bbox.x0 == 100.0
    assert bbox.y0 == 200.0
    assert bbox.x1 == 500.0
    assert bbox.y1 == 600.0
    assert bbox.to_dict() == {"x0": 100.0, "y0": 200.0, "x1": 500.0, "y1": 600.0}


def test_ground_truth_bbox_out_of_bounds() -> None:
    with pytest.raises(ValidationError):
        GroundTruthBbox(x0=-1.0, y0=0.0, x1=500.0, y1=600.0)

    with pytest.raises(ValidationError):
        GroundTruthBbox(x0=0.0, y0=0.0, x1=1000.1, y1=600.0)


def test_ground_truth_bbox_inverted_coordinates() -> None:
    with pytest.raises(ValidationError, match="Invalid x coordinates"):
        GroundTruthBbox(x0=500.0, y0=100.0, x1=400.0, y1=200.0)

    with pytest.raises(ValidationError, match="Invalid y coordinates"):
        GroundTruthBbox(x0=100.0, y0=500.0, x1=200.0, y1=400.0)

    with pytest.raises(ValidationError):
        GroundTruthBbox(x0=100.0, y0=100.0, x1=100.0, y1=200.0)


def test_ground_truth_item_valid() -> None:
    item = GroundTruthItem(
        value="50,000",
        label="Net income",
        normalized_label="Net Income",
        page=1,
        bbox=GroundTruthBbox(x0=100.0, y0=200.0, x1=300.0, y1=400.0),
        source_file="filing.pdf",
    )
    assert item.value == "50,000"
    assert item.label == "Net income"
    assert item.normalized_label == "Net Income"
    assert item.page == 1
    assert item.is_optional is False
    assert item.parsed_numeric_value == 50000.0


def test_ground_truth_item_numeric_parsing_variants() -> None:
    # Standard integers and floats
    item1 = GroundTruthItem(
        value="1234.56",
        label="L",
        normalized_label="NL",
        page=1,
        bbox=GroundTruthBbox(x0=10.0, y0=20.0, x1=30.0, y1=40.0),
        source_file="f.pdf",
    )
    assert item1.parsed_numeric_value == 1234.56

    # Currency and commas
    item2 = GroundTruthItem(
        value="$1,234,567",
        label="L",
        normalized_label="NL",
        page=1,
        bbox=GroundTruthBbox(x0=10.0, y0=20.0, x1=30.0, y1=40.0),
        source_file="f.pdf",
    )
    assert item2.parsed_numeric_value == 1234567.0

    # Negative values in parentheses (EC-2)
    item3 = GroundTruthItem(
        value="(15,000)",
        label="Net loss",
        normalized_label="Net Income",
        page=1,
        bbox=GroundTruthBbox(x0=10.0, y0=20.0, x1=30.0, y1=40.0),
        source_file="f.pdf",
    )
    assert item3.parsed_numeric_value == -15000.0

    # Negative decimal with dollar sign in parentheses
    item4 = GroundTruthItem(
        value="($2,500.75)",
        label="L",
        normalized_label="NL",
        page=1,
        bbox=GroundTruthBbox(x0=10.0, y0=20.0, x1=30.0, y1=40.0),
        source_file="f.pdf",
    )
    assert item4.parsed_numeric_value == -2500.75


def test_ground_truth_item_validation_errors() -> None:
    # Empty value
    with pytest.raises(ValidationError):
        GroundTruthItem(
            value="",
            label="Label",
            normalized_label="Norm",
            page=1,
            bbox=GroundTruthBbox(x0=10.0, y0=20.0, x1=30.0, y1=40.0),
            source_file="f.pdf",
        )

    # Page < 1
    with pytest.raises(ValidationError):
        GroundTruthItem(
            value="100",
            label="Label",
            normalized_label="Norm",
            page=0,
            bbox=GroundTruthBbox(x0=10.0, y0=20.0, x1=30.0, y1=40.0),
            source_file="f.pdf",
        )


def test_benchmark_filing_validation() -> None:
    meta = BenchmarkFilingMetadata(
        filing_id="acme_2023",
        company_name="Acme",
        ticker="ACME",
        fiscal_year=2023,
        pdf_filename="acme.pdf",
        page_count=2,
    )
    item = GroundTruthItem(
        value="100",
        label="Net income",
        normalized_label="Net Income",
        page=1,
        bbox=GroundTruthBbox(x0=10.0, y0=20.0, x1=30.0, y1=40.0),
        source_file="acme.pdf",
    )

    filing = BenchmarkFiling(
        metadata=meta,
        ground_truth_items=[item],
        expected_reconciliation_total=100.0,
    )
    assert filing.metadata.filing_id == "acme_2023"
    assert len(filing.ground_truth_items) == 1

    # Empty items list rejected
    with pytest.raises(ValidationError):
        BenchmarkFiling(
            metadata=meta,
            ground_truth_items=[],
        )


def test_manifest_and_validation_result_models() -> None:
    manifest = BenchmarkCorpusManifest(
        corpus_name="Test Corpus",
        corpus_version="1.0.0",
        filing_ids=["f1", "f2"],
    )
    assert len(manifest.filing_ids) == 2

    res = CorpusValidationResult(
        valid=True,
        filing_count=5,
        total_items=25,
        errors=[],
        warnings=[],
    )
    assert res.valid is True
    assert res.filing_count == 5
