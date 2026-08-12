"""
Unit tests for app.ingestion.repository.JobRepository.

All tests use pytest's tmp_path fixture so no real data/ directory is
ever created or touched. Each test constructs its own JobRepository
pointed at a fresh temporary directory.

Tests verify:
- Returned JobRecord shape and field values (AC-5, spec §3)
- PDF written to disk using job_id as key, never filename (EC-8)
- jobs.json updated after each save
- Deduplication is by job_id — two saves with the same filename produce
  two independent records (EC-1)
- Non-ASCII filenames round-trip correctly (EC-8)
- submitted_at is a valid ISO 8601 UTC timestamp
"""

import json
import re
import uuid
from pathlib import Path

import pymupdf
from app.ingestion.models import JobStatus
from app.ingestion.repository import JobRepository

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_minimal_pdf() -> bytes:
    """Return a valid, parseable, unencrypted PDF (one blank page)."""
    doc = pymupdf.open()
    doc.new_page()
    return doc.tobytes()  # type: ignore[no-any-return]


def make_repo(tmp_path: Path) -> JobRepository:
    return JobRepository(data_dir=tmp_path)


# ── Test 1: save_job returns a JobRecord with expected shape ──────────────────


def test_save_job_returns_job_record_with_queued_status(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    pdf = make_minimal_pdf()
    record = repo.save_job("annual.pdf", pdf, "Adjusted EBITDA")

    assert record.status == JobStatus.queued
    assert record.filename == "annual.pdf"
    assert record.file_size_bytes == len(pdf)
    assert record.target_metric == "Adjusted EBITDA"


# ── Test 2: job_id is a valid UUIDv4 ─────────────────────────────────────────


def test_save_job_returns_valid_uuid_job_id(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    record = repo.save_job("report.pdf", make_minimal_pdf(), "EBITDA")

    # Must parse without raising
    parsed = uuid.UUID(record.job_id, version=4)
    assert str(parsed) == record.job_id


# ── Test 3: PDF is written to uploads/<job_id>.pdf, not original name ─────────


def test_save_job_writes_pdf_using_job_id_not_filename(tmp_path: Path) -> None:
    """EC-8: file on disk uses job_id as key, never the original filename."""
    repo = make_repo(tmp_path)
    pdf = make_minimal_pdf()
    record = repo.save_job("original_name.pdf", pdf, "Net Income")

    expected_path = tmp_path / "uploads" / f"{record.job_id}.pdf"
    assert expected_path.exists(), f"Expected PDF at {expected_path}"
    assert expected_path.read_bytes() == pdf

    # The original filename must NOT appear as a file path.
    original_path = tmp_path / "uploads" / "original_name.pdf"
    assert not original_path.exists()


# ── Test 4: job record is appended to jobs.json ───────────────────────────────


def test_save_job_appends_record_to_jobs_json(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    record = repo.save_job("q1.pdf", make_minimal_pdf(), "Free Cash Flow")

    jobs_file = tmp_path / "jobs.json"
    assert jobs_file.exists()
    data = json.loads(jobs_file.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["job_id"] == record.job_id


# ── Test 5: list_jobs returns [] when jobs.json does not exist ────────────────


def test_list_jobs_returns_empty_list_before_any_saves(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    assert repo.list_jobs() == []


# ── Test 6: list_jobs returns all previously saved records ────────────────────


def test_list_jobs_returns_all_saved_records(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    pdf = make_minimal_pdf()
    r1 = repo.save_job("a.pdf", pdf, "Adjusted EBITDA")
    r2 = repo.save_job("b.pdf", pdf, "EBITDA")

    jobs = repo.list_jobs()
    assert len(jobs) == 2
    ids = {j.job_id for j in jobs}
    assert r1.job_id in ids
    assert r2.job_id in ids


# ── Test 7: same filename → two distinct job_ids (EC-1) ──────────────────────


def test_same_filename_twice_produces_two_distinct_job_ids(tmp_path: Path) -> None:
    """EC-1: deduplication is by job_id, not filename."""
    repo = make_repo(tmp_path)
    pdf = make_minimal_pdf()
    r1 = repo.save_job("annual.pdf", pdf, "Adjusted EBITDA")
    r2 = repo.save_job("annual.pdf", pdf, "Adjusted EBITDA")

    assert r1.job_id != r2.job_id
    assert len(repo.list_jobs()) == 2


# ── Test 8: non-ASCII filename round-trips correctly (EC-8) ──────────────────


def test_non_ascii_filename_stored_as_is(tmp_path: Path) -> None:
    """EC-8: non-ASCII filenames must survive the round-trip unchanged."""
    repo = make_repo(tmp_path)
    non_ascii_name = "財務報告書_2024.pdf"
    record = repo.save_job(non_ascii_name, make_minimal_pdf(), "Net Income")

    assert record.filename == non_ascii_name

    jobs = repo.list_jobs()
    assert len(jobs) == 1
    assert jobs[0].filename == non_ascii_name


# ── Test 9: submitted_at is a valid ISO 8601 UTC string ──────────────────────


def test_submitted_at_is_valid_iso8601_utc(tmp_path: Path) -> None:
    """submitted_at must match YYYY-MM-DDTHH:MM:SSZ (spec AC-5)."""
    repo = make_repo(tmp_path)
    record = repo.save_job("ts.pdf", make_minimal_pdf(), "Adjusted EBITDA")

    iso_utc_pattern = re.compile(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
    )
    assert iso_utc_pattern.match(record.submitted_at), (
        f"submitted_at '{record.submitted_at}' does not match ISO 8601 UTC format"
    )


# ── Test 10: update_job_status updates and persists status ───────────────────


def test_update_job_status_updates_record_and_persists(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    record = repo.save_job("test.pdf", make_minimal_pdf(), "Adjusted EBITDA")
    assert record.status == JobStatus.queued

    updated = repo.update_job_status(record.job_id, JobStatus.extracting)
    assert updated is not None
    assert updated.status == JobStatus.extracting

    # Verify persisted in jobs.json
    jobs = repo.list_jobs()
    assert len(jobs) == 1
    assert jobs[0].status == JobStatus.extracting


def test_update_job_status_returns_none_for_missing_job_id(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    res = repo.update_job_status("nonexistent-id", JobStatus.done)
    assert res is None

