"""
Unit tests for Customer and Supplier Concentration Footnote Extraction (Step I).

Tests:
- Percentage and counterparty name extraction from disclosure text.
- Negative disclosure parsing ("no single customer accounted for 10%").
- High concentration warning flag (>= 15.0%).
- Segment context association.
- Router endpoints GET /footnote/{job_id}/concentration and POST /footnote/{job_id}/concentration/confirm.
"""

from pathlib import Path

from app.extraction.models import ExtractedRecord, ScoredRecord
from app.extraction.repository import ExtractionRepository
from app.footnote.extractor import extract_customer_concentration
from app.footnote.repository import ConcentrationRepository
from app.footnote.router import (
    get_concentration_repository,
    get_job_repository,
)
from app.ingestion.repository import JobRepository
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_extract_customer_concentration_positive() -> None:
    text = (
        "Note 19. Significant Customers. During 2024, Customer A accounted for approximately 18.5% of consolidated net revenues in the Cloud Infrastructure segment. "
        "Customer B accounted for 11.2% of consolidated net revenues."
    )

    summary = extract_customer_concentration(
        records_or_text=text,
        job_id="job-conc-1",
        filing_year=2024,
    )

    assert len(summary.customers) == 2
    assert summary.customers[0].customer_name == "Customer A"
    assert summary.customers[0].revenue_percentage == 18.5
    assert summary.customers[0].segment == "Cloud Infrastructure"
    assert summary.customers[1].customer_name == "Customer B"
    assert summary.customers[1].revenue_percentage == 11.2

    # 18.5% >= 15% threshold
    assert summary.has_high_concentration is True


def test_extract_customer_concentration_negative_disclosure() -> None:
    text = "Note 19. Concentration of Credit Risk. During 2024, 2023, and 2022, no single customer accounted for 10% or more of consolidated revenues."

    summary = extract_customer_concentration(
        records_or_text=text,
        job_id="job-neg",
        filing_year=2024,
    )

    assert len(summary.customers) == 0
    assert len(summary.suppliers) == 0
    assert summary.has_high_concentration is False


def test_concentration_router_endpoints(tmp_path: Path) -> None:
    job_repo = JobRepository(data_dir=tmp_path)
    job = job_repo.save_job(
        filename="conc_filing.pdf",
        content=b"%PDF-1.4 concentration",
        target_metric="Adjusted EBITDA",
        filing_year=2024,
    )

    ext_repo = ExtractionRepository(data_dir=tmp_path)
    er = ExtractedRecord(
        value="14.0%",
        label="Customer Alpha accounted for 14.0% of revenues",
        page=40,
        bbox={"x0": 0.0, "y0": 0.0, "x1": 10.0, "y1": 10.0},
        source_file="filing.pdf",
        footnote_type="concentration",
    )
    sr = ScoredRecord(
        record=er,
        confidence_score=0.98,
        confidence_band="auto_accepted",  # type: ignore[arg-type]
        flags=[],
        table_name="Note 19. Significant Customers",
    )
    ext_repo.save_scored_records(job.job_id, [sr])

    conc_repo = ConcentrationRepository(data_dir=tmp_path)

    app.dependency_overrides[get_job_repository] = lambda: job_repo
    app.dependency_overrides[get_concentration_repository] = lambda: conc_repo

    try:
        # 1. GET /footnote/{job_id}/concentration
        res = client.get(f"/footnote/{job.job_id}/concentration")
        assert res.status_code == 200
        data = res.json()
        assert data["job_id"] == job.job_id
        assert len(data["customers"]) == 1
        assert data["customers"][0]["customer_name"] == "Customer Alpha"
        assert data["customers"][0]["revenue_percentage"] == 14.0
        assert data["has_high_concentration"] is False

        # 2. POST /footnote/{job_id}/concentration/confirm
        confirm_res = client.post(
            f"/footnote/{job.job_id}/concentration/confirm",
            json={
                "customers": [
                    {
                        "customer_name": "Customer Alpha (Apple)",
                        "revenue_percentage": 16.0,
                        "segment": "Hardware",
                        "disclosure_location": "Note 19",
                        "job_id": job.job_id,
                        "is_supplier": False,
                    }
                ],
                "suppliers": [],
            },
        )
        assert confirm_res.status_code == 200
        confirm_data = confirm_res.json()
        assert confirm_data["is_confirmed"] is True
        assert confirm_data["has_high_concentration"] is True
        assert confirm_data["customers"][0]["customer_name"] == "Customer Alpha (Apple)"
    finally:
        app.dependency_overrides.clear()
