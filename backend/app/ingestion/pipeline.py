"""
Background job processing orchestrator for the ingestion pipeline.

This module handles asynchronous job execution and status transitions for
queued files (spec AC-8).

Transitions:
    queued → extracting → done (or failed if unhandled error occurs)

CONSTITUTION §3.8 Isolation Rule:
    ingestion/ must NOT import from extraction/, classification/, formula_engine/,
    excel_export/, or audit_report/.
"""

import logging
import time

from app.ingestion.models import JobStatus
from app.ingestion.repository import JobRepository

logger = logging.getLogger(__name__)


def process_queued_job(job_id: str, repo: JobRepository) -> None:
    """
    Background worker task to process an enqueued PDF job.

    1. Transition job status from 'queued' to 'extracting'.
    2. Simulate / execute ingestion-to-extraction bridge task.
    3. On success: transition status to 'done'.
    4. On failure: transition status to 'failed' and re-raise (CONSTITUTION §1.9).
    """
    logger.info("Starting background processing for job %s", job_id)

    # 1. Update to 'extracting'
    job = repo.update_job_status(job_id, JobStatus.extracting)
    if job is None:
        logger.warning("Job %s not found in repository", job_id)
        return

    try:
        # Simulate processing delay for extraction pipeline pickup (Feature 2 baseline)
        time.sleep(1.0)

        # 2. Update to 'done'
        repo.update_job_status(job_id, JobStatus.done)
        logger.info("Completed processing for job %s", job_id)
    except Exception as err:
        logger.error("Error processing job %s: %s", job_id, err)
        repo.update_job_status(job_id, JobStatus.failed)
        raise
