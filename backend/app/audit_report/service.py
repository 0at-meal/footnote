"""
Audit Report Generation Service (Feature 8).

Orchestrates data compilation, ReportLab PDF rendering, and atomic file persistence.

Follows:
- CONSTITUTION §1.1 (mypy --strict), §1.9 (no swallowed exceptions), §4.4 (local execution).
- spec.md §1, §2, §3, AC-1, AC-10, EC-6, EC-10.
"""

import logging
from pathlib import Path

from app.audit_report.compiler import compile_audit_dataset
from app.audit_report.renderer import render_audit_report_pdf
from app.audit_report.repository import AuditReportRepository

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"


def generate_audit_report(
    job_id: str,
    data_dir: Path = _DEFAULT_DATA_DIR,
) -> Path:
    """
    Compiles, renders, and persists the compliance audit report PDF for a completed job.

    Args:
        job_id: UUID of the job.
        data_dir: Root data storage directory.

    Returns:
        Absolute Path to the persisted PDF report.

    Raises:
        JobNotFoundError: If job_id does not exist.
        ModelNotCompleteError: If model provenance records are absent (EC-6).
        OSError: If a filesystem persistence error occurs (EC-10).
    """
    logger.info("Compiling audit report dataset for job %s", job_id)
    dataset = compile_audit_dataset(job_id, data_dir=data_dir)

    logger.info("Rendering structured PDF audit report for job %s", job_id)
    pdf_bytes = render_audit_report_pdf(dataset)

    logger.info("Persisting audit report PDF for job %s", job_id)
    repo = AuditReportRepository(data_dir=data_dir)
    return repo.save_report_pdf(job_id, pdf_bytes)
