"""
Unit tests for app.ingestion.company_repository.CompanyRepository.

All tests use pytest's tmp_path fixture to ensure filesystem isolation.
Tests verify:
- Creation and persistence of CompanyRecord
- Valid UUIDv4 company_id and ISO 8601 UTC created_at
- Listing and retrieval (by ID and case-insensitive name)
- Idempotent association of job_ids
- Missing entity handling (returns None)
- Deserialization and round-trip fidelity
"""

import json
import re
import uuid
from pathlib import Path

from app.ingestion.company_repository import CompanyRepository
from app.ingestion.models import CompanyRecord


def make_repo(tmp_path: Path) -> CompanyRepository:
    return CompanyRepository(data_dir=tmp_path)


def test_save_company_creates_and_persists_record(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    company = repo.save_company("Acme Corporation", ticker="ACME")

    assert company.name == "Acme Corporation"
    assert company.ticker == "ACME"
    assert company.job_ids == []

    # Validate company_id is a valid UUIDv4
    parsed_uuid = uuid.UUID(company.company_id, version=4)
    assert str(parsed_uuid) == company.company_id

    # Validate created_at ISO 8601 UTC format
    iso_utc_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    assert iso_utc_pattern.match(company.created_at)

    # Check companies.json file directly
    companies_file = tmp_path / "companies.json"
    assert companies_file.exists()
    raw = json.loads(companies_file.read_text(encoding="utf-8"))
    assert len(raw) == 1
    assert raw[0]["company_id"] == company.company_id
    assert raw[0]["name"] == "Acme Corporation"
    assert raw[0]["ticker"] == "ACME"


def test_save_company_with_explicit_fields(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    custom_id = "custom-uuid-123"
    custom_time = "2026-08-20T10:00:00Z"
    custom_jobs = ["job-1", "job-2"]

    company = repo.save_company(
        name="Globex Corp",
        ticker="GLBX",
        company_id=custom_id,
        created_at=custom_time,
        job_ids=custom_jobs,
    )

    assert company.company_id == custom_id
    assert company.name == "Globex Corp"
    assert company.ticker == "GLBX"
    assert company.created_at == custom_time
    assert company.job_ids == ["job-1", "job-2"]


def test_list_companies_empty_and_populated(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    assert repo.list_companies() == []

    c1 = repo.save_company("Company A")
    c2 = repo.save_company("Company B", ticker="CPB")

    companies = repo.list_companies()
    assert len(companies) == 2
    assert companies[0].company_id == c1.company_id
    assert companies[1].company_id == c2.company_id


def test_list_companies_handles_utf8_bom(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    companies_file = tmp_path / "companies.json"
    companies_file.write_bytes(b"\xef\xbb\xbf[]")
    assert repo.list_companies() == []


def test_get_company_returns_record_and_none_for_missing(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    company = repo.save_company("Initech")

    found = repo.get_company(company.company_id)
    assert found is not None
    assert found.company_id == company.company_id
    assert found.name == "Initech"

    assert repo.get_company("nonexistent-id") is None


def test_get_company_by_name(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    company = repo.save_company("Soylent Corporation", ticker="SOY")

    # Exact match
    found = repo.get_company_by_name("Soylent Corporation")
    assert found is not None
    assert found.company_id == company.company_id

    # Case-insensitive and whitespace-stripped match
    found_ci = repo.get_company_by_name("  soylent corporation  ")
    assert found_ci is not None
    assert found_ci.company_id == company.company_id

    # Nonexistent name
    assert repo.get_company_by_name("Nonexistent Corp") is None


def test_add_job_to_company_is_idempotent(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    company = repo.save_company("Wayne Enterprises")

    # Add first job
    updated = repo.add_job_to_company(company.company_id, "job-uuid-1")
    assert updated is not None
    assert updated.job_ids == ["job-uuid-1"]

    # Verify persisted
    persisted = repo.get_company(company.company_id)
    assert persisted is not None
    assert persisted.job_ids == ["job-uuid-1"]

    # Add second job
    updated2 = repo.add_job_to_company(company.company_id, "job-uuid-2")
    assert updated2 is not None
    assert updated2.job_ids == ["job-uuid-1", "job-uuid-2"]

    # Add first job again (idempotent: no duplicates)
    updated3 = repo.add_job_to_company(company.company_id, "job-uuid-1")
    assert updated3 is not None
    assert updated3.job_ids == ["job-uuid-1", "job-uuid-2"]

    # Verify file persisted
    persisted2 = repo.get_company(company.company_id)
    assert persisted2 is not None
    assert persisted2.job_ids == ["job-uuid-1", "job-uuid-2"]


def test_add_job_to_company_returns_none_for_missing_company(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    assert repo.add_job_to_company("nonexistent-id", "job-uuid-1") is None


def test_company_record_round_trip() -> None:
    record = CompanyRecord(
        company_id="c-123",
        name="Umbrella Corp",
        ticker="UMB",
        created_at="2026-08-23T12:00:00Z",
        job_ids=["j-1", "j-2"],
    )
    dumped = record.model_dump()
    loaded = CompanyRecord.model_validate(dumped)
    assert loaded == record
