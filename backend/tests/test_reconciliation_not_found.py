"""
AUD-007 / decision D2: a filing with no non-GAAP reconciliation ends with status "not_found",
an explicit reason, no workbook and an empty review. A real bridge is still detected even when
its title sits above the table (the common EX-99.1 layout).

These run the real pipeline (Docling + PyMuPDF) on SYNTHETIC PDFs built by code; only the LLM
classifier is replaced (it is a network dependency).
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app.classification.models import ClassifierRawResponse
from app.extraction.docling_parser import _parse_pdf_with_pymupdf, parse_pdf_with_report
from app.extraction.repository import ExtractionRepository
from app.ingestion.models import JobStatus
from app.ingestion.repository import JobRepository
from app.job_runner import process_queued_job
from app.review.repository import ReviewRepository

from tests.fixtures.synthetic.pdfs import (
    SYNTHETIC_BALANCE_SHEET,
    SYNTHETIC_EBITDA_BRIDGE,
    write_synthetic_pdf,
)

NOT_FOUND_REASON = "Adjusted EBITDA reconciliation not found in this filing"


def _classifier() -> MagicMock:
    client = MagicMock()
    client.classify.return_value = ClassifierRawResponse(label="Other", confidence=0.5)
    return client


def _run(tmp_path: Path, name: str, table: object) -> tuple[JobRepository, str, MagicMock]:
    repo = JobRepository(data_dir=tmp_path)
    pdf = write_synthetic_pdf(tmp_path / f"{name}.pdf", [table])  # type: ignore[list-item]
    job = repo.save_job(
        filename=f"{name}.pdf",
        content=pdf.read_bytes(),
        target_metric="Adjusted EBITDA",
        filing_year=2025,
        workflow_pack="non_gaap_bridge",
    )
    client = _classifier()
    process_queued_job(job.job_id, repo, classifier_client=client)
    return repo, job.job_id, client


@pytest.mark.parametrize("parser", ["docling", "pymupdf"])
def test_bridge_titled_above_table_is_detected(tmp_path: Path, parser: str) -> None:
    pdf = write_synthetic_pdf(tmp_path / "synthetic_bridge.pdf", [SYNTHETIC_EBITDA_BRIDGE])
    if parser == "docling":
        items, report = parse_pdf_with_report(pdf, "synthetic_bridge.pdf", target_metric="Adjusted EBITDA")
        assert report.parser_used == "docling"
    else:
        items = _parse_pdf_with_pymupdf(pdf, "synthetic_bridge.pdf", "Adjusted EBITDA")
    assert items
    assert all(item.is_reconciliation_candidate for item in items)


def test_filing_without_reconciliation_ends_not_found(tmp_path: Path) -> None:
    repo, job_id, client = _run(tmp_path, "synthetic_balance_sheet", SYNTHETIC_BALANCE_SHEET)

    job = repo.get_job(job_id)
    assert job is not None
    assert job.status == JobStatus.not_found
    assert job.model_skip_reason == NOT_FOUND_REASON
    assert job.model_ready is False
    assert not (tmp_path / "models" / f"{job_id}_model.xlsx").exists()
    client.classify.assert_not_called()

    summary = ExtractionRepository(data_dir=tmp_path).get_extraction_summary(job_id)
    assert summary is not None
    assert summary.target_metric_found is False

    assert ReviewRepository(data_dir=tmp_path).get_review_items(job_id) == []


def test_filing_with_reconciliation_lists_only_bridge_items(tmp_path: Path) -> None:
    repo, job_id, _client = _run(tmp_path, "synthetic_bridge", SYNTHETIC_EBITDA_BRIDGE)

    job = repo.get_job(job_id)
    assert job is not None
    assert job.status == JobStatus.done
    items = ReviewRepository(data_dir=tmp_path).get_review_items(job_id)
    assert items
    labels = {item.label.split(" / ")[0] for item in items}
    assert "Adjusted EBITDA" in labels
    assert "Net income" in labels
