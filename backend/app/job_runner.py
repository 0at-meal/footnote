"""
Background job processing orchestrator across pipeline stages.

Located at app/job_runner.py to satisfy CONSTITUTION §3.8 isolation rules:
    ingestion/ must NOT import from extraction/, classification/, formula_engine/, or excel_export/.
    job_runner lives at the app root level and coordinates ingestion, extraction,
    classification, formula_engine, and excel_export pipeline stages.
"""

import logging
from typing import Literal

from app.classification.client import GroqClassifierClient
from app.classification.decision_log import (
    DecisionLogRepository,
    build_log_entries,
)
from app.classification.dispatcher import (
    dispatch_records_to_classifier,
    pre_classify_records,
)
from app.classification.models import ClassificationBatchResult
from app.classification.normalizer import normalize_records
from app.classification.repository import ClassificationRepository
from app.classification.taxonomy import TaxonomyRepository
from app.excel_export.bridge_generator import generate_bridge_workbook
from app.excel_export.multi_statement_generator import generate_multi_statement_workbook
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
from app.formula_engine.tree import build_comprehensive_model_tree, build_formula_tree
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
        target_metric = job.target_metric or "Adjusted EBITDA"
        workflow_pack = getattr(job, "workflow_pack", "non_gaap_bridge") or "non_gaap_bridge"

        # Stage 1: Docling structural parse (bounded extraction per workflow pack, Ticket 7.2)
        docling_items = parse_pdf(
            pdf_path,
            job.filename,
            target_metric=target_metric,
            workflow_pack=workflow_pack,
        )
        extraction_repo.save_docling_items(job_id, docling_items)

        parsers_in_items = {
            getattr(it, "parser_used", "docling") for it in docling_items
        }
        parser_used: Literal["docling", "pymupdf", "mixed"] = "docling"
        if len(parsers_in_items) > 1:
            parser_used = "mixed"
        elif "pymupdf" in parsers_in_items:
            parser_used = "pymupdf"
        else:
            parser_used = "docling"

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
            scored_records,
            image_only_page_count=image_only_page_count,
            parser_used=parser_used,
        )
        extraction_repo.save_extraction_summary(job_id, summary)

        # Stage 6: Two-Level Classification & Taxonomy Normalization (Feature 3)
        client = classifier_client or GroqClassifierClient()
        active_taxonomy = taxonomy_repo.load_taxonomy()

        # Filter to reconciliation candidates before Groq dispatch (Ticket 1.1.3)
        reconciliation_candidates = [
            r for r in scored_records if r.is_reconciliation_candidate
        ]
        if not reconciliation_candidates and scored_records:
            reconciliation_candidates = list(scored_records)

        filtered_out_count = len(scored_records) - len(reconciliation_candidates)
        logger.info(
            "Filtered out %d non-candidate records before classification",
            filtered_out_count,
        )

        # 1. Deterministic alias pre-classification stage (Ticket A.3.1)
        pre_classified, unmatched = pre_classify_records(
            reconciliation_candidates, active_taxonomy
        )

        # 2. Dispatch only genuine unmatched unknowns to Groq (Ticket A.3.3)
        if unmatched:
            batch_result = dispatch_records_to_classifier(unmatched, client)
        else:
            batch_result = ClassificationBatchResult(
                results=[],
                total_dispatched=0,
                success_count=0,
                error_count=0,
                skipped_count=0,
            )

        classified_records = normalize_records(
            reconciliation_candidates,
            batch_result,
            active_taxonomy,
            target_metric=target_metric,
            pre_classified=pre_classified,
        )
        classification_repo.save_classified_records(job_id, classified_records)

        logger.info(
            "Job %s classification: %d pre-classified deterministically, %d dispatched to Groq, %d total classified",
            job_id,
            len(pre_classified),
            len(unmatched),
            len(classified_records),
        )

        # Append-only machine-readable decision log (spec.md AC-2, AC-7)
        log_entries = build_log_entries(job_id, batch_result, active_taxonomy)
        decision_log_repo.log_batch_calls(job_id, log_entries)

        # Stage 7: Formula Engine Input & Model Construction (Workflow Packs Architecture)
        formula_inputs = read_formula_inputs(classified_records)
        model_ready = False
        model_skip_reason: str | None = None

        if len(formula_inputs.nodes) > 0:
            if workflow_pack == "non_gaap_bridge":
                # Stage 8: Primary 2-tab Non-GAAP Bridge Model Generation (Ticket 7.3)
                formula_tree = build_formula_tree(
                    formula_inputs, target_metric=target_metric
                )
                if formula_tree.is_valid:
                    generation_result = generate_bridge_workbook(
                        formula_tree,
                        job_id=job_id,
                        output_dir=repo.data_dir,
                    )
                    model_repo.save_generation_result(job_id, generation_result)
                    if (
                        generation_result.is_success
                        and generation_result.provenance_records
                    ):
                        model_repo.save_provenance_records(
                            job_id, generation_result.provenance_records
                        )
                        model_ready = True
                        model_skip_reason = None
                        logger.info(
                            "Generated draft Non-GAAP bridge model for job %s with %d cells",
                            job_id,
                            generation_result.total_cells_generated,
                        )
                    else:
                        model_skip_reason = (
                            generation_result.error_detail
                            or "Bridge workbook generation failed"
                        )
                else:
                    model_skip_reason = (
                        formula_tree.error_message or "Bridge formula tree invalid"
                    )
            else:
                # Stage 8: Multi-statement / Comprehensive Model Generation
                comp_tree = build_comprehensive_model_tree(formula_inputs)
                if comp_tree.is_valid:
                    generation_result = generate_multi_statement_workbook(
                        company=None,
                        year_trees=[(job, comp_tree)],
                        output_dir=repo.data_dir,
                    )
                    model_repo.save_generation_result(job_id, generation_result)
                    if (
                        generation_result.is_success
                        and generation_result.provenance_records
                    ):
                        model_repo.save_provenance_records(
                            job_id, generation_result.provenance_records
                        )
                        model_ready = True
                        model_skip_reason = None
                        logger.info(
                            "Generated draft Excel model workbook for job %s with %d cells",
                            job_id,
                            generation_result.total_cells_generated,
                        )
                    else:
                        model_skip_reason = (
                            generation_result.error_detail
                            or "Workbook generation failed"
                        )
                else:
                    model_skip_reason = (
                        comp_tree.error_message or "Formula tree validation failed"
                    )
        else:
            model_skip_reason = (
                formula_inputs.error_message
                or "No auto-accepted or confirmed records available"
            )
            logger.warning(
                "No auto-accepted or confirmed records available for draft model in job %s: %s (requires human review/confirmation)",
                job_id,
                model_skip_reason,
            )

        # Final status update to 'done' with model_ready flag and model_skip_reason
        repo.update_job_status(
            job_id,
            JobStatus.done,
            model_ready=model_ready,
            model_skip_reason=model_skip_reason,
        )
        logger.info(
            "Completed pipeline for job %s: %d records assembled, %d classified, model_ready=%s, model_skip_reason=%s",
            job_id,
            summary.total_items,
            len(classified_records),
            model_ready,
            model_skip_reason,
        )
    except Exception as err:
        logger.error("Error processing job %s: %s", job_id, err)
        repo.update_job_status(job_id, JobStatus.failed)
        raise
