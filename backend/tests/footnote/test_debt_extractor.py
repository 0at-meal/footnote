"""
Unit tests for Debt Schedule Footnote Extractor and Endpoints (Step E).

Tests:
- Rate parsing (fixed rate, floating rate with spread & benchmark).
- Maturity year extraction.
- Principal amount parsing.
- Tranche extraction and schedule compilation.
- Weighted average rate and total debt calculation.
- Router endpoints GET /footnote/{job_id}/debt and POST /footnote/{job_id}/debt/confirm.
"""

from pathlib import Path

from app.extraction.models import ExtractedRecord, ScoredRecord
from app.extraction.repository import ExtractionRepository
from app.footnote.extractor import (
    compile_debt_schedule,
    extract_debt_tranches,
    parse_maturity_from_text,
    parse_principal_amount,
    parse_rate_from_text,
)
from app.footnote.repository import DebtScheduleRepository
from app.footnote.router import get_debt_repository, get_job_repository
from app.ingestion.repository import JobRepository
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _make_debt_record(
    label: str,
    value: str,
    page: int = 42,
    table_name: str = "Note 8. Debt and Credit Facilities",
) -> ScoredRecord:
    er = ExtractedRecord(
        value=value,
        label=label,
        page=page,
        bbox={"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 220.0},
        source_file="filing.pdf",
        footnote_type="debt",
    )
    return ScoredRecord(
        record=er,
        confidence_score=0.98,
        confidence_band="auto_accepted",  # type: ignore[arg-type]
        flags=[],
        table_name=table_name,
        footnote_type="debt",
    )


def test_parse_rate_from_text() -> None:
    # Fixed rate
    rate, _txt, is_floating, spread, _benchmark = parse_rate_from_text(
        "5.250% Senior Notes due 2028"
    )
    assert rate == 5.250
    assert is_floating is False
    assert spread is None

    # Floating rate
    _rate_f, _txt_f, is_floating_f, spread_f, benchmark_f = parse_rate_from_text(
        "SOFR + 2.50% Term Loan B"
    )
    assert is_floating_f is True
    assert spread_f == 2.50
    assert benchmark_f == "SOFR"


def test_parse_maturity_from_text() -> None:
    assert parse_maturity_from_text("5.250% Senior Notes due 2028") == 2028
    assert parse_maturity_from_text("Term Loan B maturing September 30, 2030") == 2030
    assert parse_maturity_from_text("Revolving Credit Facility (2027)") == 2027


def test_parse_principal_amount() -> None:
    val, txt = parse_principal_amount("$1,500.0")
    assert val == 1500.0
    assert txt == "$1,500.0"

    val_neg, _ = parse_principal_amount("(250)")
    assert val_neg == -250.0


def test_extract_debt_tranches_and_compile_schedule() -> None:
    records = [
        _make_debt_record("5.250% Senior Notes due 2028", "1,500.0"),
        _make_debt_record("SOFR + 2.50% Term Loan B due 2030", "800.0"),
        _make_debt_record(
            "4.000% Convertible Subordinated Debentures due 2029", "500.0"
        ),
        _make_debt_record("Total debt obligations", "2,800.0"),  # Total line
    ]

    tranches = extract_debt_tranches(records)
    # Total line must be excluded
    assert len(tranches) == 3

    assert tranches[0].instrument_name == "5.250% Senior Notes due 2028"
    assert tranches[0].principal_amount == 1500.0
    assert tranches[0].interest_rate == 5.25
    assert tranches[0].maturity_year == 2028
    assert tranches[0].senior_subordinated == "Senior"

    assert tranches[1].instrument_name == "SOFR + 2.50% Term Loan B due 2030"
    assert tranches[1].principal_amount == 800.0
    assert tranches[1].is_floating is True
    assert tranches[1].spread == 2.50
    assert tranches[1].benchmark == "SOFR"

    assert (
        tranches[2].instrument_name
        == "4.000% Convertible Subordinated Debentures due 2029"
    )
    assert tranches[2].principal_amount == 500.0
    assert tranches[2].senior_subordinated == "Subordinated"

    schedule = compile_debt_schedule(
        job_id="test_job_123",
        records=records,
        filing_year=2024,
    )
    assert schedule.total_debt == 2800.0  # 1500 + 800 + 500
    # Weighted average rate of rated items: (5.25 * 1500 + 4.0 * 500) / (1500 + 500) = (7875 + 2000) / 2000 = 4.9375 -> 4.938
    assert schedule.weighted_avg_rate == 4.938


def test_debt_schedule_endpoints(tmp_path: Path) -> None:
    job_repo = JobRepository(data_dir=tmp_path)
    job = job_repo.save_job(
        filename="test_filing.pdf",
        content=b"%PDF-1.4 sample",
        target_metric="Adjusted EBITDA",
        filing_year=2024,
    )

    ext_repo = ExtractionRepository(data_dir=tmp_path)
    records = [
        _make_debt_record("5.250% Senior Notes due 2028", "1,500.0"),
        _make_debt_record("SOFR + 2.50% Term Loan B due 2030", "800.0"),
    ]
    ext_repo.save_scored_records(job.job_id, records)

    debt_repo = DebtScheduleRepository(data_dir=tmp_path)

    app.dependency_overrides[get_job_repository] = lambda: job_repo
    app.dependency_overrides[get_debt_repository] = lambda: debt_repo

    try:
        # 1. GET /footnote/{job_id}/debt
        res = client.get(f"/footnote/{job.job_id}/debt")
        assert res.status_code == 200
        data = res.json()
        assert data["job_id"] == job.job_id
        assert len(data["tranches"]) == 2
        assert data["total_debt"] == 2300.0
        assert data["is_confirmed"] is False

        # 2. POST /footnote/{job_id}/debt/confirm
        confirm_res = client.post(
            f"/footnote/{job.job_id}/debt/confirm",
            json={
                "tranches": [
                    {
                        "id": data["tranches"][0]["id"],
                        "instrument_name": "5.250% Senior Notes due 2028 (Corrected)",
                        "principal_amount": 1600.0,
                        "principal_text": "1,600.0",
                        "interest_rate": 5.25,
                        "rate_text": "5.25%",
                        "maturity_year": 2028,
                        "senior_subordinated": "Senior",
                        "is_floating": False,
                        "page": 42,
                        "bbox": {"x0": 0.0, "y0": 0.0, "x1": 0.0, "y1": 0.0},
                    }
                ]
            },
        )
        assert confirm_res.status_code == 200
        confirm_data = confirm_res.json()
        assert confirm_data["is_confirmed"] is True
        assert confirm_data["total_debt"] == 1600.0
        assert (
            confirm_data["tranches"][0]["instrument_name"]
            == "5.250% Senior Notes due 2028 (Corrected)"
        )
    finally:
        app.dependency_overrides.clear()
