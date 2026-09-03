"""
Unit tests for Capital Structure Excel Generator (Workflow Pack 2 / Ticket 14.1).
"""

from pathlib import Path

from app.excel_export.debt_schedule_generator import generate_capital_structure_workbook
from app.footnote.models import (
    DebtSchedule,
    DebtTranche,
    LeaseCommitmentYear,
    LeaseSchedule,
)


def test_generate_capital_structure_empty(tmp_path: Path) -> None:
    """Empty schedules return is_success=False with diagnostic error."""
    debt_sched = DebtSchedule(job_id="job_empty")
    lease_sched = LeaseSchedule(job_id="job_empty")

    res = generate_capital_structure_workbook(
        debt_schedule=debt_sched,
        lease_schedule=lease_sched,
        job_id="job_empty",
        output_dir=tmp_path,
    )
    assert res.is_success is False
    assert "No Note 8" in (res.error_detail or "")


def test_generate_capital_structure_with_data(tmp_path: Path) -> None:
    """Generates 2-tab workbook with valid formulas and provenance."""
    job_id = "job_cap_struct"
    tranches = [
        DebtTranche(
            id="tranche_1",
            instrument_name="5.50% Senior Notes due 2028",
            principal_amount=500.0,
            interest_rate=5.50,
            maturity_year=2028,
            senior_subordinated="Senior",
            page=45,
            bbox={"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 250.0},
        ),
        DebtTranche(
            id="tranche_2",
            instrument_name="Revolving Credit Facility",
            principal_amount=150.0,
            is_floating=True,
            benchmark="SOFR",
            spread=1.75,
            maturity_year=2027,
            senior_subordinated="Secured",
            page=46,
            bbox={"x0": 100.0, "y0": 300.0, "x1": 300.0, "y1": 350.0},
        ),
    ]
    debt_sched = DebtSchedule(
        job_id=job_id,
        tranches=tranches,
        total_debt=650.0,
    )

    years = [
        LeaseCommitmentYear(
            year_label="2025",
            operating_amount=40.0,
            finance_amount=10.0,
            total_amount=50.0,
            page=52,
            bbox={"x0": 50.0, "y0": 100.0, "x1": 250.0, "y1": 120.0},
        ),
        LeaseCommitmentYear(
            year_label="2026",
            operating_amount=35.0,
            finance_amount=8.0,
            total_amount=43.0,
            page=52,
            bbox={"x0": 50.0, "y0": 130.0, "x1": 250.0, "y1": 150.0},
        ),
    ]
    lease_sched = LeaseSchedule(
        job_id=job_id,
        years=years,
        operating_total=75.0,
        finance_total=18.0,
    )

    res = generate_capital_structure_workbook(
        debt_schedule=debt_sched,
        lease_schedule=lease_sched,
        job_id=job_id,
        output_dir=tmp_path,
    )
    assert res.is_success is True
    assert Path(res.file_path).exists()
    assert res.sheet_names == ["Debt_Tranches", "Lease_Waterfall"]
    assert res.formula_cells_count >= 2
    assert len(res.provenance_records) >= 3
