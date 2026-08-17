"""
Unit and integration tests for Feature 9 Evaluation Harness corpus loader (eval/corpus_loader.py).
"""

import json
from pathlib import Path

import pymupdf
import pytest

from eval.corpus_loader import (
    DEFAULT_CORPUS_DIR,
    CorpusLoadingError,
    load_corpus,
    load_filing,
    validate_corpus,
)


def test_load_corpus_loads_all_curated_filings() -> None:
    """AC-1: The harness loads at least 5 curated benchmark filings."""
    filings = load_corpus(DEFAULT_CORPUS_DIR)
    assert len(filings) >= 5

    filing_ids = [f.metadata.filing_id for f in filings]
    assert "acme_2023_10k" in filing_ids
    assert "globex_2023_10k" in filing_ids
    assert "initech_2023_10k" in filing_ids
    assert "umbrella_2023_10k" in filing_ids
    assert "wayne_2023_10k" in filing_ids


def test_validate_corpus_integrity() -> None:
    """AC-1: Full corpus data integrity and schema compliance verification."""
    result = validate_corpus(DEFAULT_CORPUS_DIR, min_filings=5)
    assert (
        result.valid is True
    ), f"Corpus validation failed with errors: {result.errors}"
    assert result.filing_count >= 5
    assert result.total_items > 0
    assert len(result.errors) == 0


def test_all_filing_pdfs_are_valid_and_readable() -> None:
    """Confirms all benchmark PDFs exist, are syntactically valid, and open with PyMuPDF."""
    filings = load_corpus(DEFAULT_CORPUS_DIR)
    for filing in filings:
        pdf_path = (
            DEFAULT_CORPUS_DIR
            / filing.metadata.filing_id
            / filing.metadata.pdf_filename
        )
        assert pdf_path.is_file()
        doc = pymupdf.open(pdf_path)
        assert len(doc) == filing.metadata.page_count
        doc.close()


def test_load_filing_direct() -> None:
    filing_dir = DEFAULT_CORPUS_DIR / "acme_2023_10k"
    filing = load_filing(filing_dir)
    assert filing.metadata.company_name == "Acme Corporation"
    assert filing.metadata.ticker == "ACME"
    assert filing.metadata.fiscal_year == 2023
    assert len(filing.ground_truth_items) == 6


def test_load_filing_missing_dir_raises() -> None:
    with pytest.raises(CorpusLoadingError, match="does not exist"):
        load_filing("non_existent_dir_123")


def test_load_filing_missing_gt_raises(tmp_path: Path) -> None:
    with pytest.raises(CorpusLoadingError, match="Missing ground_truth.json"):
        load_filing(tmp_path)


def test_validate_corpus_missing_pdf_detection(tmp_path: Path) -> None:
    """EC-4: A benchmark PDF file missing on disk triggers descriptive error."""
    filing_dir = tmp_path / "test_filing"
    filing_dir.mkdir(parents=True)

    gt_data = {
        "metadata": {
            "filing_id": "test_filing",
            "company_name": "Test Co",
            "ticker": "TEST",
            "fiscal_year": 2023,
            "filing_type": "10-K",
            "pdf_filename": "missing.pdf",
            "page_count": 1,
            "target_metric": "Adjusted EBITDA",
        },
        "ground_truth_items": [
            {
                "value": "100",
                "label": "Net income",
                "normalized_label": "Net Income",
                "page": 1,
                "bbox": {"x0": 10.0, "y0": 20.0, "x1": 30.0, "y1": 40.0},
                "source_file": "missing.pdf",
            }
        ],
    }
    (filing_dir / "ground_truth.json").write_text(json.dumps(gt_data), encoding="utf-8")

    manifest = {
        "corpus_name": "Test",
        "corpus_version": "1.0",
        "target_metric": "Adjusted EBITDA",
        "filing_ids": ["test_filing"],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = validate_corpus(tmp_path, min_filings=1)
    assert result.valid is False
    assert any("not found" in err for err in result.errors)


def test_validate_corpus_page_count_mismatch(tmp_path: Path) -> None:
    """Validates that a PDF page count mismatch against metadata is flagged as an error."""
    filing_dir = tmp_path / "mismatch_filing"
    filing_dir.mkdir(parents=True)

    pdf_filename = "mismatch.pdf"
    doc = pymupdf.open()
    doc.new_page(width=612, height=792)
    doc.save(str(filing_dir / pdf_filename))
    doc.close()

    gt_data = {
        "metadata": {
            "filing_id": "mismatch_filing",
            "company_name": "Mismatch Co",
            "ticker": "MIS",
            "fiscal_year": 2023,
            "filing_type": "10-K",
            "pdf_filename": pdf_filename,
            "page_count": 5,  # Metadata claims 5, but PDF only has 1
            "target_metric": "Adjusted EBITDA",
        },
        "ground_truth_items": [
            {
                "value": "100",
                "label": "Net income",
                "normalized_label": "Net Income",
                "page": 1,
                "bbox": {"x0": 10.0, "y0": 20.0, "x1": 30.0, "y1": 40.0},
                "source_file": pdf_filename,
            }
        ],
    }
    (filing_dir / "ground_truth.json").write_text(json.dumps(gt_data), encoding="utf-8")

    manifest = {
        "corpus_name": "Test",
        "corpus_version": "1.0",
        "target_metric": "Adjusted EBITDA",
        "filing_ids": ["mismatch_filing"],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = validate_corpus(tmp_path, min_filings=1)
    assert result.valid is False
    assert any("Page count mismatch" in err for err in result.errors)


def test_optional_ground_truth_items() -> None:
    """EC-1: Optional ground truth items are supported in schema and loaded correctly."""
    filing = load_filing(DEFAULT_CORPUS_DIR / "wayne_2023_10k")
    optional_items = [item for item in filing.ground_truth_items if item.is_optional]
    assert len(optional_items) >= 1
    assert optional_items[0].normalized_label == "M&A transaction costs"


def test_negative_values_in_parentheses() -> None:
    """EC-2: Negative values formatted in parentheses e.g. (15,000) are parsed correctly."""
    filing = load_filing(DEFAULT_CORPUS_DIR / "initech_2023_10k")
    net_loss = next(
        item for item in filing.ground_truth_items if item.label == "Net loss"
    )
    assert net_loss.value == "(15,000)"
    assert net_loss.parsed_numeric_value == -15000.0


def test_duplicate_labels_across_sections() -> None:
    """EC-10: Preserves distinct ground truth items with duplicate normalized labels across pages/sections."""
    filing = load_filing(DEFAULT_CORPUS_DIR / "umbrella_2023_10k")
    sbc_items = [
        item
        for item in filing.ground_truth_items
        if item.normalized_label == "Stock-based compensation"
    ]
    assert len(sbc_items) == 3
    # Check pages
    pages = {item.page for item in sbc_items}
    assert 1 in pages
    assert 2 in pages
