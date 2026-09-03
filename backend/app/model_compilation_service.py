"""
Service for on-the-fly financial model compilation (Step 3).

Orchestrates classification, formula engine, and excel export pipelines
at the application root tier without violating layer boundaries in audit_report.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.classification.models import ClassifiedRecord
from app.classification.repository import ClassificationRepository
from app.excel_export.generator import generate_workbook
from app.excel_export.models import W3CAnnotationRecord
from app.excel_export.repository import ModelRepository
from app.formula_engine.reader import (
    read_formula_inputs,
    read_formula_inputs_from_review,
)
from app.formula_engine.tree import build_formula_tree
from app.review.models import ReviewItem
from app.review.repository import ReviewRepository

logger = logging.getLogger(__name__)


def try_compile_model_on_the_fly(
    job_id: str,
    data_dir: Path,
    target_metric: str = "Adjusted EBITDA",
    review_items: list[ReviewItem] | None = None,
    classified_records: list[ClassifiedRecord] | None = None,
) -> list[W3CAnnotationRecord] | None:
    """
    Attempt on-the-fly model compilation if confirmed/locked items exist.
    Compiles formula tree, generates workbook, and saves provenance records.
    """
    if review_items is None:
        review_repo = ReviewRepository(data_dir=data_dir)
        review_items = review_repo.get_review_items(job_id)

    if classified_records is None:
        classification_repo = ClassificationRepository(data_dir=data_dir)
        classified_records = classification_repo.get_classified_records(job_id)

    batch = None
    if review_items is not None and len(review_items) > 0:
        batch = read_formula_inputs_from_review(review_items)
    elif classified_records is not None and len(classified_records) > 0:
        batch = read_formula_inputs(classified_records)

    if batch is not None and len(batch.nodes) > 0:
        formula_tree = build_formula_tree(batch, target_metric=target_metric)
        if formula_tree.is_valid:
            generation_result = generate_workbook(
                formula_tree,
                job_id=job_id,
                output_dir=data_dir,
            )
            model_repo = ModelRepository(data_dir=data_dir)
            model_repo.save_generation_result(job_id, generation_result)
            if generation_result.provenance_records:
                model_repo.save_provenance_records(
                    job_id, generation_result.provenance_records
                )
                return generation_result.provenance_records
        else:
            logger.warning(
                "Audit report model compilation failed for job %s: formula tree invalid (%s)",
                job_id,
                formula_tree.error_message,
            )
    else:
        logger.warning(
            "Audit report model compilation failed for job %s: no confirmed or auto-accepted line items found",
            job_id,
        )

    return None


def get_or_compile_provenance(
    job_id: str,
    data_dir: Path,
    target_metric: str = "Adjusted EBITDA",
) -> list[W3CAnnotationRecord] | None:
    """
    Retrieve existing provenance records from model repository or compile them on-the-fly.
    """
    model_repo = ModelRepository(data_dir=data_dir)
    records = model_repo.get_provenance_records(job_id)
    if records:
        return records

    return try_compile_model_on_the_fly(
        job_id=job_id,
        data_dir=data_dir,
        target_metric=target_metric,
    )
