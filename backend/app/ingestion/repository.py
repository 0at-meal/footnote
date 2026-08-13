"""
Job repository for the ingestion pipeline.

Scope: persist validated PDF bytes to disk and maintain a JSON list of
JobRecords. This module does NOT validate file content (that is
validation.py) and does NOT trigger extraction (that is Feature 1 Step 5).

Storage layout (relative to data_dir, default: backend/data/):
    uploads/<job_id>.pdf   ← file bytes; key is job_id, never filename (EC-8)
    jobs.json              ← JSON array of JobRecord objects

Writes are atomic at the file level: PDF bytes are written to a .tmp
sibling and renamed into place via os.replace before the jobs.json
record is appended. If any step fails, the exception propagates — no
partial record is ever silently left on disk (CONSTITUTION §1.9, spec AC-9).

This module is intentionally single-user / single-session (CONSTITUTION §6.10,
plan.md §5). No locking is implemented; concurrent access is out of scope.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.ingestion.models import JobRecord, JobStatus

# Default data directory: backend/data/ (one level above the app/ package root).
# Tests override this by constructing JobRepository(data_dir=tmp_path).
_DEFAULT_DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"


class JobRepository:
    """Persist job records and PDF files for the ingestion pipeline."""

    def __init__(self, data_dir: Path = _DEFAULT_DATA_DIR) -> None:
        self._data_dir = data_dir
        self._uploads_dir = data_dir / "uploads"
        self._jobs_file = data_dir / "jobs.json"

    @property
    def data_dir(self) -> Path:
        """The root data directory for this repository instance."""
        return self._data_dir

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _ensure_dirs(self) -> None:
        """Create data/uploads/ if it does not already exist."""
        self._uploads_dir.mkdir(parents=True, exist_ok=True)

    def _read_records(self) -> list[JobRecord]:
        """
        Read jobs.json and deserialise into JobRecord objects.

        Returns an empty list if the file does not yet exist (first run).
        Any read or parse error propagates — never silently ignored
        (CONSTITUTION §1.9).
        """
        if not self._jobs_file.exists():
            return []
        text: str = self._jobs_file.read_text(encoding="utf-8-sig")
        raw: Any = json.loads(text)
        return [JobRecord.model_validate(item) for item in raw]

    def _write_records(self, records: list[JobRecord]) -> None:
        """Serialise JobRecord list to jobs.json (overwrite in place)."""
        payload: list[dict[str, Any]] = [r.model_dump() for r in records]
        self._jobs_file.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def save_job(
        self,
        filename: str,
        content: bytes,
        target_metric: str,
    ) -> JobRecord:
        """
        Persist a validated PDF and create a JobRecord.

        Steps:
        1. Generate a UUIDv4 job_id.
        2. Write content to uploads/<job_id>.pdf.tmp, then atomically rename
           to uploads/<job_id>.pdf using os.replace.
        3. Build a JobRecord with status=queued and submitted_at=now (UTC).
        4. Append the record to jobs.json (read → append → write).
        5. Return the JobRecord.

        If any step raises, the exception propagates. The caller must not
        treat a raised exception as a silent no-op (spec AC-9).

        Args:
            filename:      Original filename as supplied by the uploader.
                           Stored as-is (UTF-8) — EC-8.
            content:       Raw validated PDF bytes.
            target_metric: User-selected target metric string.

        Returns:
            The newly created and persisted JobRecord.
        """
        self._ensure_dirs()

        job_id: str = str(uuid.uuid4())
        pdf_path: Path = self._uploads_dir / f"{job_id}.pdf"
        tmp_path: Path = self._uploads_dir / f"{job_id}.pdf.tmp"

        # Atomic write: temp file → rename so a failed write never leaves a
        # partial PDF that could be confused with a valid stored file.
        tmp_path.write_bytes(content)
        os.replace(tmp_path, pdf_path)

        submitted_at: str = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        record = JobRecord(
            job_id=job_id,
            filename=filename,
            file_size_bytes=len(content),
            status=JobStatus.queued,
            target_metric=target_metric,
            submitted_at=submitted_at,
        )

        # Read-modify-write: safe at MVP (single-user, no concurrent writers).
        records = self._read_records()
        records.append(record)
        self._write_records(records)

        return record

    def list_jobs(self) -> list[JobRecord]:
        """
        Return all persisted JobRecords, oldest first.

        Returns an empty list if no jobs have been submitted yet.
        """
        return self._read_records()

    def get_job(self, job_id: str) -> JobRecord | None:
        """Return a single JobRecord by job_id, or None if not found."""
        records = self._read_records()
        for rec in records:
            if rec.job_id == job_id:
                return rec
        return None

    def get_pdf_path(self, job_id: str) -> Path:
        """Return the absolute path to the stored PDF for a job_id."""
        return self._uploads_dir / f"{job_id}.pdf"


    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
    ) -> JobRecord | None:
        """
        Update the status of a specific JobRecord and persist the change to jobs.json.

        This is a read-modify-write operation (read all → patch → write all).
        It is intentionally not atomic at the filesystem level — no file lock,
        no temp-then-rename — which is acceptable for the MVP single-user,
        single-session constraint (CONSTITUTION §6.10, module docstring).

        Args:
            job_id: The UUID of the job to update.
            status: The new JobStatus to set.

        Returns:
            The updated JobRecord if found, or None if no job with job_id exists.
        """
        records = self._read_records()
        updated_record: JobRecord | None = None

        for idx, rec in enumerate(records):
            if rec.job_id == job_id:
                updated_record = rec.model_copy(update={"status": status})
                records[idx] = updated_record
                break

        if updated_record is not None:
            self._write_records(records)

        return updated_record
