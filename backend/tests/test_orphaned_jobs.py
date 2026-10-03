"""
AUD-035: jobs left 'queued'/'extracting' by a stopped server are failed with a reason on startup,
and an 'extracting' job older than JOB_TIMEOUT_SECONDS is failed with a reason when jobs are listed.

Uses the session's isolated data dir (tests/conftest.py), never backend/data.
"""

from datetime import UTC, datetime, timedelta

import pytest
from app.ingestion.models import JobStatus
from app.ingestion.repository import JobRepository
from app.main import app
from fastapi.testclient import TestClient


def _job(repo: JobRepository, name: str) -> str:
    return repo.save_job(filename=name, content=b"%PDF-1.4 test", target_metric="Adjusted EBITDA").job_id


def test_startup_fails_interrupted_jobs_with_reason() -> None:
    repo = JobRepository()
    extracting = _job(repo, "zombie_extracting.pdf")
    queued = _job(repo, "zombie_queued.pdf")
    finished = _job(repo, "finished.pdf")
    repo.update_job_status(extracting, JobStatus.extracting)
    repo.update_job_status(finished, JobStatus.done)

    with TestClient(app):
        pass

    for job_id in (extracting, queued):
        job = repo.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.failed
        assert job.failure_reason is not None
        assert "interrupted" in job.failure_reason.lower()
    done = repo.get_job(finished)
    assert done is not None and done.status == JobStatus.done and done.failure_reason is None


def test_stale_extracting_job_times_out_when_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOB_TIMEOUT_SECONDS", "60")
    with TestClient(app) as client:
        repo = JobRepository()
        stale = _job(repo, "stale.pdf")
        fresh = _job(repo, "fresh.pdf")
        repo.update_job_status(stale, JobStatus.extracting)
        repo.update_job_status(fresh, JobStatus.extracting)
        old = (datetime.now(UTC) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        records = repo._read_records()
        repo._write_records(
            [r.model_copy(update={"started_at": old}) if r.job_id == stale else r for r in records]
        )

        jobs = {j["job_id"]: j for j in client.get("/upload/jobs").json()["jobs"]}

    assert jobs[stale]["status"] == "failed"
    assert "timed out" in jobs[stale]["failure_reason"].lower()
    assert jobs[fresh]["status"] == "extracting"
