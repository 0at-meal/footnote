"""
Background job processing orchestrator across pipeline stages.

Located at app/job_runner.py to satisfy CONSTITUTION §3.8 isolation rules:
    ingestion/ must NOT import from extraction/.
    job_runner lives at the app root level and coordinates both the ingestion
    repository and the extraction pipeline.
"""

import logging

from app.extraction.assembler import assemble_records
from app.extraction.confidence import score_records
from app.extraction.coordinate_normalizer import normalize_coordinates
from app.extraction.docling_parser import parse_pdf
from app.extraction.flagger import create_extraction_summary
from app.extraction.repository import ExtractionRepository
from app.ingestion.models import JobStatus
from app.ingestion.repository import JobRepository

logger = logging.getLogger(__name__)


def process_queued_job(job_id: str, repo: JobRepository) -> None:
    """
    Background worker task to process an enqueued PDF job through full extraction.

    Pipeline execution sequence:
    1. Transition job status from 'queued' to 'extracting'.
    2. Stage 1 (Docling): Parse layout structures -> save_docling_items.
    3. Stage 2 (PyMuPDF): Normalize bounding box coordinates -> save_normalized_items.
    4. Stage 3 (Assembler): Assemble 5-field schema records -> save_extracted_records.
    5. Stage 4 (Confidence): Compute structural confidence scores -> save_scored_records.
    6. Stage 5 (Summary): Evaluate 15% threshold & statistics -> save_extraction_summary.
    7. On success: Transition status to 'done'.
    8. On unrecoverable crash: Transition status to 'failed' and re-raise (CONSTITUTION §1.9).
    """
    logger.info("Starting background processing for job %s", job_id)

    job = repo.get_job(job_id)
    if job is None:
        logger.warning("Job %s not found in repository", job_id)
        return

    # 1. Update status to 'extracting'
    repo.update_job_status(job_id, JobStatus.extracting)

    extraction_repo = ExtractionRepository(data_dir=repo.data_dir)

    try:
        pdf_path = repo.get_pdf_path(job_id)

        # Stage 1: Docling structural parse
        docling_items = parse_pdf(pdf_path, job.filename)
        extraction_repo.save_docling_items(job_id, docling_items)

        # Stage 2: PyMuPDF 0-1000 coordinate normalization
        normalized_items = normalize_coordinates(pdf_path, docling_items)
        extraction_repo.save_normalized_items(job_id, normalized_items)

        # Stage 3: Frozen 5-field record assembly
        extracted_records = assemble_records(normalized_items)
        extraction_repo.save_extracted_records(job_id, extracted_records)

        # Stage 4: Confidence scoring & routing band assignment
        scored_records = score_records(extracted_records, normalized_items)
        extraction_repo.save_scored_records(job_id, scored_records)

        # Stage 5: Extraction summary & threshold evaluation
        summary = create_extraction_summary(scored_records)
        extraction_repo.save_extraction_summary(job_id, summary)

        # Final status update to 'done'
        repo.update_job_status(job_id, JobStatus.done)
        logger.info(
            "Completed extraction pipeline for job %s: %d records assembled (%d auto-accepted, %d flagged)",
            job_id,
            summary.total_items,
            summary.auto_accepted_count,
            summary.flagged_count,
        )
    except Exception as err:
        logger.error("Error processing job %s: %s", job_id, err)
        repo.update_job_status(job_id, JobStatus.failed)
        raise
