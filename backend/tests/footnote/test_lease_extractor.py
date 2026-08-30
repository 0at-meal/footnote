"""
Unit tests for ASC 842 Lease Commitment Footnote Extraction and Endpoints (Step F).

Tests:
- 5-year waterfall parsing with operating and finance columns.
- "Thereafter" row parsing.
- Discount rate extraction.
- Missing finance lease column gracefully producing None without errors.
- Router endpoints GET /footnote/{job_id}/lease, POST /footnote/{job_id}/lease/confirm, GET /footnote/{job_id}/available.
"""

from pathlib import Path

from app.extraction.models import ExtractedRecord, ScoredRecord
from app.extraction.repository import ExtractionRepository
from app.footnote.extractor import extract_lease_schedule
from app.footnote.repository import (
    DebtScheduleRepository,
    LeaseScheduleRepository,
)
from app.footnote.router import (
    get_debt_repository,
    get_job_repository,
    get_lease_repository,
)
from app.ingestion.repository import JobRepository
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _make_lease_record(
    label: str,
    value: str,
    page: int = 55,
    table_name: str = "Note 12. Leases - Maturity of Lease Liabilities",
) -> ScoredRecord:
    er = ExtractedRecord(
        value=value,
        label=label,
        page=page,
        bbox={"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 220.0},
        source_file="filing.pdf",
        footnote_type="lease",
    )
    return ScoredRecord(
        record=er,
        confidence_score=0.98,
        confidence_band="auto_accepted",  # type: ignore[arg-type]
        flags=[],
        table_name=table_name,
        footnote_type="lease",
    )


def test_extract_lease_schedule_5_year_waterfall() -> None:
    records = [
        _make_lease_record("2025 / Operating Lease", "450.0"),
        _make_lease_record("2025 / Finance Lease", "50.0"),
        _make_lease_record("2026 / Operating Lease", "420.0"),
        _make_lease_record("2026 / Finance Lease", "45.0"),
        _make_lease_record("2027 / Operating Lease", "380.0"),
        _make_lease_record("2027 / Finance Lease", "40.0"),
        _make_lease_record("2028 / Operating Lease", "300.0"),
        _make_lease_record("2028 / Finance Lease", "35.0"),
        _make_lease_record("2029 / Operating Lease", "250.0"),
        _make_lease_record("2029 / Finance Lease", "30.0"),
        _make_lease_record("Thereafter / Operating Lease", "1,100.0"),
        _make_lease_record("Thereafter / Finance Lease", "100.0"),
        _make_lease_record(
            "Weighted-average discount rate - Operating Leases", "4.85%"
        ),
        _make_lease_record("Weighted-average discount rate - Finance Leases", "5.10%"),
        _make_lease_record("Total undiscounted lease payments", "3,200.0"),
    ]

    schedule = extract_lease_schedule(
        records=records,
        job_id="job-lease-123",
        filing_year=2024,
    )

    assert schedule is not None
    assert len(schedule.years) == 6
    assert schedule.years[0].year_label == "2025"
    assert schedule.years[0].operating_amount == 450.0
    assert schedule.years[0].finance_amount == 50.0
    assert schedule.years[0].total_amount == 500.0

    assert schedule.years[5].year_label == "Thereafter"
    assert schedule.years[5].operating_amount == 1100.0
    assert schedule.years[5].finance_amount == 100.0
    assert schedule.years[5].total_amount == 1200.0

    assert schedule.operating_total == 2900.0
    assert schedule.finance_total == 300.0
    assert schedule.operating_discount_rate == 4.85
    assert schedule.finance_discount_rate == 5.10


def test_extract_lease_schedule_operating_only() -> None:
    records = [
        _make_lease_record("2025", "120.0"),
        _make_lease_record("2026", "110.0"),
        _make_lease_record("2027", "95.0"),
        _make_lease_record("Thereafter", "400.0"),
        _make_lease_record("Weighted-average discount rate", "4.50%"),
    ]

    schedule = extract_lease_schedule(
        records=records,
        job_id="job-op-only",
        filing_year=2024,
    )

    assert schedule is not None
    assert len(schedule.years) == 4
    assert schedule.years[0].operating_amount == 120.0
    assert schedule.years[0].finance_amount is None
    assert schedule.operating_total == 725.0
    assert schedule.finance_total is None
    assert schedule.operating_discount_rate == 4.50


def test_lease_schedule_endpoints(tmp_path: Path) -> None:
    job_repo = JobRepository(data_dir=tmp_path)
    job = job_repo.save_job(
        filename="lease_filing.pdf",
        content=b"%PDF-1.4 lease test",
        target_metric="Adjusted EBITDA",
        filing_year=2024,
    )

    ext_repo = ExtractionRepository(data_dir=tmp_path)
    records = [
        _make_lease_record("2025 / Operating Lease", "500.0"),
        _make_lease_record("2026 / Operating Lease", "450.0"),
        _make_lease_record("Weighted-average discount rate", "4.75%"),
    ]
    ext_repo.save_scored_records(job.job_id, records)

    debt_repo = DebtScheduleRepository(data_dir=tmp_path)
    lease_repo = LeaseScheduleRepository(data_dir=tmp_path)

    app.dependency_overrides[get_job_repository] = lambda: job_repo
    app.dependency_overrides[get_debt_repository] = lambda: debt_repo
    app.dependency_overrides[get_lease_repository] = lambda: lease_repo

    try:
        # 1. GET /footnote/{job_id}/available
        avail_res = client.get(f"/footnote/{job.job_id}/available")
        assert avail_res.status_code == 200
        avail = avail_res.json()
        assert "lease_schedule" in avail

        # 2. GET /footnote/{job_id}/lease
        res = client.get(f"/footnote/{job.job_id}/lease")
        assert res.status_code == 200
        data = res.json()
        assert data["job_id"] == job.job_id
        assert len(data["years"]) == 2
        assert data["operating_total"] == 950.0
        assert data["operating_discount_rate"] == 4.75
        assert data["is_confirmed"] is False

        # 3. POST /footnote/{job_id}/lease/confirm
        confirm_res = client.post(
            f"/footnote/{job.job_id}/lease/confirm",
            json={
                "years": [
                    {
                        "year_label": "2025",
                        "operating_amount": 550.0,
                        "finance_amount": None,
                        "total_amount": 550.0,
                        "page": 55,
                        "bbox": {"x0": 0.0, "y0": 0.0, "x1": 0.0, "y1": 0.0},
                    }
                ],
                "operating_discount_rate": 4.80,
            },
        )
        assert confirm_res.status_code == 200
        confirm_data = confirm_res.json()
        assert confirm_data["is_confirmed"] is True
        assert confirm_data["operating_total"] == 550.0
        assert confirm_data["operating_discount_rate"] == 4.80
    finally:
        app.dependency_overrides.clear()
