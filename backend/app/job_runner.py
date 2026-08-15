"""
Background job processing orchestrator across pipeline stages.

Located at app/job_runner.py to satisfy CONSTITUTION §3.8 isolation rules:
    ingestion/ must NOT import from extraction/, classification/, formula_engine/, or excel_export/.
    job_runner lives at the app root level and coordinates ingestion, extraction,
    classification, formula_engine, and excel_export pipeline stages.
"""

import logging

from app.classification.client import GroqClassifierClient
from app.classification.decision_log import (
    DecisionLogRepository,
    build_log_entries,
)
from app.classification.dispatcher import dispatch_records_to_classifier
from app.classification.normalizer import normalize_records
from app.classification.repository import ClassificationRepository
from app.classification.taxonomy import TaxonomyRepository
from app.excel_export.generator import generate_workbook
from app.excel_export.repository import ModelRepository
from app.extraction.assembler import assemble_records
from app.extraction.confidence import score_records
from app.extraction.coordinate_normalizer import (
    count_image_only_pages,
    normalize_coordinates,
)
from app.extraction.docling_parser import parse_pdf
from app.extraction.flagger import create_extraction_summary
from app.extraction.repository import ExtractionRepository
from app.formula_engine.reader import read_formula_inputs
from app.formula_engine.tree import build_formula_tree
from app.ingestion.models import JobStatus
from app.ingestion.repository import JobRepository

logger = logging.getLogger(__name__)


def process_queued_job(
    job_id: str,
    repo: JobRepository,
    classifier_client: GroqClassifierClient | None = None,
) -> None:
    """
    Background worker task to process an enqueued PDF job through full extraction, classification,
    and deterministic Excel model generation.

    Pipeline execution sequence:
    1. Transition job status from 'queued' to 'extracting'.
    2. Stage 1 (Docling): Parse layout structures -> save_docling_items.
    3. Stage 2 (PyMuPDF): Normalize bounding box coordinates -> save_normalized_items.
    4. Stage 3 (Assembler): Assemble 5-field schema records -> save_extracted_records.
    5. Stage 4 (Confidence): Compute structural confidence scores -> save_scored_records.
    6. Stage 5 (Summary): Evaluate 15% threshold & statistics -> save_extraction_summary.
    7. Stage 6 (Classification): Dispatch eligible records -> Normalize -> save_classified_records & decision_log.
    8. Stage 7 (Formula Engine): Read confirmed line items -> Build deterministic FormulaTree.
    9. Stage 8 (Excel Export): Generate .xlsx workbook with dynamic formulas and W3C provenance metadata.
    10. On success: Transition status to 'done'.
    11. On unrecoverable crash: Transition status to 'failed' and re-raise (CONSTITUTION §1.9).
    """
    logger.info("Starting background processing for job %s", job_id)

    job = repo.get_job(job_id)
    if job is None:
        logger.warning("Job %s not found in repository", job_id)
        return

    # 1. Update status to 'extracting'
    repo.update_job_status(job_id, JobStatus.extracting)

    extraction_repo = ExtractionRepository(data_dir=repo.data_dir)
    classification_repo = ClassificationRepository(data_dir=repo.data_dir)
    taxonomy_repo = TaxonomyRepository(data_dir=repo.data_dir)
    decision_log_repo = DecisionLogRepository(data_dir=repo.data_dir)
    model_repo = ModelRepository(data_dir=repo.data_dir)

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
        image_only_page_count = count_image_only_pages(pdf_path)
        summary = create_extraction_summary(
            scored_records, image_only_page_count=image_only_page_count
        )
        extraction_repo.save_extraction_summary(job_id, summary)

        # Stage 6: Classification & Taxonomy Normalization (Feature 3)
        client = classifier_client or GroqClassifierClient()
        active_taxonomy = taxonomy_repo.load_taxonomy()

        batch_result = dispatch_records_to_classifier(scored_records, client)
        classified_records = normalize_records(scored_records, batch_result, active_taxonomy)
        classification_repo.save_classified_records(job_id, classified_records)

        # Append-only machine-readable decision log (spec.md §6, AC-2, AC-7)
        log_entries = build_log_entries(job_id, batch_result, active_taxonomy)
        decision_log_repo.log_batch_calls(job_id, log_entries)

        # Stage 7: Formula Engine Input & Tree Construction (Feature 4 Steps 1-2)
        formula_inputs = read_formula_inputs(classified_records)
        target_metric = job.target_metric or "Adjusted EBITDA"
        formula_tree = build_formula_tree(formula_inputs, target_metric=target_metric)

        # Stage 8: Excel Export & Provenance Tagging (Feature 4 Steps 3-4)
        generation_result = generate_workbook(
            formula_tree,
            job_id=job_id,
            output_dir=repo.data_dir,
        )
        if generation_result.is_success and generation_result.provenance_records:
            model_repo.save_provenance_records(job_id, generation_result.provenance_records)

        # Final status update to 'done'
        repo.update_job_status(job_id, JobStatus.done)
        logger.info(
            "Completed pipeline for job %s: %d records assembled, %d classified, %d model cells generated",
            job_id,
            summary.total_items,
            len(classified_records),
            generation_result.total_cells_generated,
        )
    except Exception as err:
        logger.error("Error processing job %s: %s", job_id, err)
        repo.update_job_status(job_id, JobStatus.failed)
        raise
