"""
Repository for persisting and loading Debt Schedules (Feature 8, Step E).

Adheres to:
- CONSTITUTION §1.1: mypy --strict compliance.
- CONSTITUTION §1.9: Atomic file write pattern with tempfile rename.
"""

import json
import logging
import os
from pathlib import Path

from app.extraction.repository import ExtractionRepository
from app.footnote.extractor import (
    compile_debt_schedule,
    extract_customer_concentration,
    extract_lease_schedule,
)
from app.footnote.models import (
    ConcentrationSummary,
    CustomerConcentration,
    DebtSchedule,
    DebtTranche,
    LeaseCommitmentYear,
    LeaseSchedule,
)
from app.ingestion.repository import JobRepository

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"


class DebtScheduleRepository:
    """
    Persists and retrieves DebtSchedule records for extraction jobs.
    """

    def __init__(self, data_dir: Path = _DEFAULT_DATA_DIR) -> None:
        self._data_dir = data_dir
        self._results_dir = data_dir / "results"
        self._results_dir.mkdir(parents=True, exist_ok=True)

    def _schedule_path(self, job_id: str) -> Path:
        return self._results_dir / f"{job_id}_debt.json"

    def get_debt_schedule(self, job_id: str) -> DebtSchedule | None:
        """
        Load persisted DebtSchedule for a job, or compile on demand from extraction records.
        """
        path = self._schedule_path(job_id)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return DebtSchedule.model_validate(data)
            except (json.JSONDecodeError, OSError, ValueError) as err:
                logger.warning(
                    "Failed to read saved debt schedule for %s: %s", job_id, err
                )

        # Compile from extraction records if not already saved
        ext_repo = ExtractionRepository(data_dir=self._data_dir)
        scored_records = ext_repo.get_scored_records(job_id)
        if not scored_records:
            return None

        job_repo = JobRepository(data_dir=self._data_dir)
        job = job_repo.get_job(job_id)

        schedule = compile_debt_schedule(
            job_id=job_id,
            records=scored_records,
            company_id=job.company_id if job else None,
            filing_year=job.filing_year if job else None,
        )
        self.save_debt_schedule(schedule)
        return schedule

    def save_debt_schedule(self, schedule: DebtSchedule) -> Path:
        """
        Save DebtSchedule to disk atomically using atomic tempfile rename.
        """
        target_path = self._schedule_path(schedule.job_id)
        tmp_path = target_path.with_suffix(".tmp")

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(schedule.model_dump(), f, indent=2)

        os.replace(tmp_path, target_path)
        return target_path

    def confirm_debt_schedule(
        self,
        job_id: str,
        tranches: list[DebtTranche],
    ) -> DebtSchedule | None:
        """
        Update tranches and mark debt schedule as confirmed.
        """
        schedule = self.get_debt_schedule(job_id)
        if schedule is None:
            return None

        schedule.tranches = tranches
        schedule.is_confirmed = True

        # Recompute totals
        valid_principals = [
            t.principal_amount for t in tranches if t.principal_amount is not None
        ]
        if valid_principals:
            schedule.total_debt = round(sum(valid_principals), 2)
        else:
            schedule.total_debt = None

        rated_tranches = [
            t
            for t in tranches
            if t.interest_rate is not None and t.principal_amount is not None
        ]
        if rated_tranches:
            rated_sum = sum(
                t.principal_amount
                for t in rated_tranches
                if t.principal_amount is not None
            )
            if rated_sum > 0:
                rate_weight_sum = sum(
                    (t.interest_rate or 0.0) * (t.principal_amount or 0.0)
                    for t in rated_tranches
                )
                schedule.weighted_avg_rate = round(rate_weight_sum / rated_sum, 3)
            else:
                schedule.weighted_avg_rate = None
        else:
            schedule.weighted_avg_rate = None

        self.save_debt_schedule(schedule)
        return schedule


class LeaseScheduleRepository:
    """
    Persists and retrieves LeaseSchedule records for extraction jobs.
    """

    def __init__(self, data_dir: Path = _DEFAULT_DATA_DIR) -> None:
        self._data_dir = data_dir
        self._results_dir = data_dir / "results"
        self._results_dir.mkdir(parents=True, exist_ok=True)

    def _schedule_path(self, job_id: str) -> Path:
        return self._results_dir / f"{job_id}_lease.json"

    def get_lease_schedule(self, job_id: str) -> LeaseSchedule | None:
        """
        Load persisted LeaseSchedule for a job, or compile on demand from extraction records.
        """
        path = self._schedule_path(job_id)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return LeaseSchedule.model_validate(data)
            except (json.JSONDecodeError, OSError, ValueError) as err:
                logger.warning(
                    "Failed to read saved lease schedule for %s: %s", job_id, err
                )

        # Compile from extraction records if not already saved
        ext_repo = ExtractionRepository(data_dir=self._data_dir)
        scored_records = ext_repo.get_scored_records(job_id)
        if not scored_records:
            return None

        job_repo = JobRepository(data_dir=self._data_dir)
        job = job_repo.get_job(job_id)

        schedule = extract_lease_schedule(
            records=scored_records,
            job_id=job_id,
            company_id=job.company_id if job else None,
            filing_year=job.filing_year if job else None,
        )
        if schedule is not None:
            self.save_lease_schedule(schedule)
        return schedule

    def save_lease_schedule(self, schedule: LeaseSchedule) -> Path:
        """
        Save LeaseSchedule to disk atomically using atomic tempfile rename.
        """
        target_path = self._schedule_path(schedule.job_id)
        tmp_path = target_path.with_suffix(".tmp")

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(schedule.model_dump(), f, indent=2)

        os.replace(tmp_path, target_path)
        return target_path

    def confirm_lease_schedule(
        self,
        job_id: str,
        years: list[LeaseCommitmentYear],
        operating_discount_rate: float | None = None,
        finance_discount_rate: float | None = None,
    ) -> LeaseSchedule | None:
        """
        Update lease commitment years and discount rates, marking schedule as confirmed.
        """
        schedule = self.get_lease_schedule(job_id)
        if schedule is None:
            return None

        schedule.years = years
        if operating_discount_rate is not None:
            schedule.operating_discount_rate = operating_discount_rate
        if finance_discount_rate is not None:
            schedule.finance_discount_rate = finance_discount_rate
        schedule.is_confirmed = True

        # Recompute totals
        op_vals = [y.operating_amount for y in years if y.operating_amount is not None]
        fin_vals = [y.finance_amount for y in years if y.finance_amount is not None]
        schedule.operating_total = round(sum(op_vals), 2) if op_vals else None
        schedule.finance_total = round(sum(fin_vals), 2) if fin_vals else None

        self.save_lease_schedule(schedule)
        return schedule


class ConcentrationRepository:
    """
    Persists and retrieves ConcentrationSummary records for extraction jobs.
    """

    def __init__(self, data_dir: Path = _DEFAULT_DATA_DIR) -> None:
        self._data_dir = data_dir
        self._results_dir = data_dir / "results"
        self._results_dir.mkdir(parents=True, exist_ok=True)

    def _concentration_path(self, job_id: str) -> Path:
        return self._results_dir / f"{job_id}_concentration.json"

    def get_concentration(self, job_id: str) -> ConcentrationSummary | None:
        """
        Load persisted ConcentrationSummary for a job, or compile on demand.
        """
        path = self._concentration_path(job_id)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return ConcentrationSummary.model_validate(data)
            except (json.JSONDecodeError, OSError, ValueError) as err:
                logger.warning(
                    "Failed to read saved concentration for %s: %s", job_id, err
                )

        ext_repo = ExtractionRepository(data_dir=self._data_dir)
        scored_records = ext_repo.get_scored_records(job_id)
        if not scored_records:
            return None

        job_repo = JobRepository(data_dir=self._data_dir)
        job = job_repo.get_job(job_id)

        summary = extract_customer_concentration(
            records_or_text=scored_records,
            job_id=job_id,
            company_id=job.company_id if job else None,
            filing_year=job.filing_year if job else None,
        )
        self.save_concentration(summary)
        return summary

    def save_concentration(self, summary: ConcentrationSummary) -> Path:
        """
        Save ConcentrationSummary to disk atomically.
        """
        target_path = self._concentration_path(summary.job_id)
        tmp_path = target_path.with_suffix(".tmp")

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(summary.model_dump(), f, indent=2)

        os.replace(tmp_path, target_path)
        return target_path

    def confirm_concentration(
        self,
        job_id: str,
        customers: list[CustomerConcentration],
        suppliers: list[CustomerConcentration],
    ) -> ConcentrationSummary | None:
        """
        Update concentration entries and mark as confirmed.
        """
        summary = self.get_concentration(job_id)
        if summary is None:
            return None

        summary.customers = customers
        summary.suppliers = suppliers
        summary.has_high_concentration = any(
            (c.revenue_percentage or 0.0) >= 15.0 for c in customers + suppliers
        )
        summary.is_confirmed = True

        self.save_concentration(summary)
        return summary
