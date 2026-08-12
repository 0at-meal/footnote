"""
Background job processing orchestrator across pipeline stages.

Located at app/job_runner.py to satisfy CONSTITUTION §3.8 isolation rules:
    ingestion/ must NOT import from extraction/.
    job_runner lives at the app root level and coordinates ingestion repository
    and extraction pipeline operations.
"""

import logging

from app.extraction.docling_parser import parse_pdf
from app.ingestion.models import JobStatus
from app.ingestion.repository import JobRepository

logger = logging.getLogger(__name__)


def process_queued_job(job_id: str, repo: JobRepository) -> None:
    """
    Background worker task to process an enqueued PDF job.

    1. Transition job status from 'queued' to 'extracting'.
    2. Retrieve stored PDF and parse using Docling.
    3. Persist raw DoclingItem objects to data/results/<job_id>_docling.json.
    4. On success: transition status to 'done'.
    5. On failure: transition status to 'failed' and re-raise (CONSTITUTION §1.9).
    """
    logger.info("Starting background processing for job %s", job_id)

    job = repo.get_job(job_id)
    if job is None:
        logger.warning("Job %s not found in repository", job_id)
        return

    # 1. Update status to 'extracting'
    repo.update_job_status(job_id, JobStatus.extracting)

    try:
        # 2. Extract layout structures via Docling
        pdf_path = repo.get_pdf_path(job_id)
        docling_items = parse_pdf(pdf_path, job.filename)

        # 3. Persist intermediate Docling items
        repo.save_docling_items(job_id, docling_items)

        # 4. Update status to 'done'
        repo.update_job_status(job_id, JobStatus.done)
        logger.info(
            "Completed extraction for job %s: %d items extracted",
            job_id,
            len(docling_items),
        )
    except Exception as err:
        logger.error("Error processing job %s: %s", job_id, err)
        repo.update_job_status(job_id, JobStatus.failed)
        raise
