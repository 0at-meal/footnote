"""
Company repository for managing company entities and multi-year job grouping.

Scope: persist CompanyRecord instances to disk and maintain data/companies.json.
This module is intentionally single-user / single-session (CONSTITUTION §6.10).

Storage layout (relative to data_dir, default: backend/data/):
    companies.json ← JSON array of CompanyRecord objects
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.ingestion.models import CompanyRecord

_DEFAULT_DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"


class CompanyRepository:
    """Persist and query company records for multi-year financial model aggregation."""

    def __init__(self, data_dir: Path = _DEFAULT_DATA_DIR) -> None:
        self._data_dir = data_dir
        self._companies_file = data_dir / "companies.json"

    @property
    def data_dir(self) -> Path:
        """The root data directory for this repository instance."""
        return self._data_dir

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _ensure_dirs(self) -> None:
        """Create data directory if it does not already exist."""
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def _read_records(self) -> list[CompanyRecord]:
        """
        Read companies.json and deserialise into CompanyRecord objects.

        Returns an empty list if the file does not yet exist.
        Any read or parse error propagates (CONSTITUTION §1.9).
        """
        if not self._companies_file.exists():
            return []
        text: str = self._companies_file.read_text(encoding="utf-8-sig")
        raw: Any = json.loads(text)
        return [CompanyRecord.model_validate(item) for item in raw]

    def _write_records(self, records: list[CompanyRecord]) -> None:
        """Serialise CompanyRecord list to companies.json (overwrite in place)."""
        self._ensure_dirs()
        payload: list[dict[str, Any]] = [r.model_dump() for r in records]
        self._companies_file.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def save_company(
        self,
        name: str,
        ticker: str | None = None,
        company_id: str | None = None,
        created_at: str | None = None,
        job_ids: list[str] | None = None,
    ) -> CompanyRecord:
        """
        Create and persist a new CompanyRecord.

        Args:
            name:       Human-readable company name (e.g. 'Acme Corporation').
            ticker:     Optional stock ticker symbol (e.g. 'ACME').
            company_id: Optional UUIDv4 string (auto-generated if omitted).
            created_at: Optional ISO 8601 UTC timestamp (now if omitted).
            job_ids:    Optional initial list of associated job UUIDs.

        Returns:
            The newly created and persisted CompanyRecord.
        """
        if company_id is None:
            company_id = str(uuid.uuid4())

        if created_at is None:
            created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        if job_ids is None:
            job_ids = []

        record = CompanyRecord(
            company_id=company_id,
            name=name,
            ticker=ticker,
            created_at=created_at,
            job_ids=job_ids,
        )

        records = self._read_records()
        records.append(record)
        self._write_records(records)

        return record

    def list_companies(self) -> list[CompanyRecord]:
        """Return all persisted CompanyRecords, oldest first."""
        return self._read_records()

    def get_company(self, company_id: str) -> CompanyRecord | None:
        """Return a single CompanyRecord by company_id, or None if not found."""
        records = self._read_records()
        for rec in records:
            if rec.company_id == company_id:
                return rec
        return None

    def get_company_by_name(self, name: str) -> CompanyRecord | None:
        """
        Look up a company record by name (case-insensitive strip match).

        Returns the first matching CompanyRecord, or None if not found.
        """
        normalized_name: str = name.strip().lower()
        records = self._read_records()
        for rec in records:
            if rec.name.strip().lower() == normalized_name:
                return rec
        return None

    def add_job_to_company(self, company_id: str, job_id: str) -> CompanyRecord | None:
        """
        Associate a job UUID with a company.

        Idempotent: If the job_id is already present in company.job_ids, no duplicate
        entry is created and no write is performed.

        Args:
            company_id: The UUID of the company to update.
            job_id:     The UUID of the job to associate.

        Returns:
            The updated CompanyRecord, or None if company_id is not found.
        """
        records = self._read_records()
        updated_record: CompanyRecord | None = None

        for idx, rec in enumerate(records):
            if rec.company_id == company_id:
                if job_id not in rec.job_ids:
                    new_job_ids: list[str] = list(rec.job_ids) + [job_id]
                    updated_record = rec.model_copy(update={"job_ids": new_job_ids})
                    records[idx] = updated_record
                    self._write_records(records)
                else:
                    updated_record = rec
                break

        return updated_record
