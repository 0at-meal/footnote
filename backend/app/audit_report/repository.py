"""
Repository for persisting and retrieving generated audit report PDF files (Feature 8).

Follows:
- CONSTITUTION §1.1 (mypy --strict)
- CONSTITUTION §1.9 (atomic persistence via temporary file rename)
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"


class AuditReportRepository:
    """
    Persists and retrieves generated compliance audit report PDF files under data/reports/.
    """

    def __init__(self, data_dir: Path = _DEFAULT_DATA_DIR) -> None:
        self._data_dir = data_dir
        self._reports_dir = data_dir / "reports"

    @property
    def reports_dir(self) -> Path:
        return self._reports_dir

    def _ensure_dirs(self) -> None:
        """Create data/reports/ directory if it does not already exist."""
        self._reports_dir.mkdir(parents=True, exist_ok=True)

    def save_report_pdf(self, job_id: str, pdf_bytes: bytes) -> Path:
        """
        Atomically persists PDF bytes to data/reports/<job_id>_audit_report.pdf.

        Uses temporary file rename to prevent partial or corrupted file writes (CONSTITUTION §1.9).

        Args:
            job_id: UUID of the job.
            pdf_bytes: Raw binary PDF content.

        Returns:
            Absolute Path to the persisted PDF file.
        """
        self._ensure_dirs()
        dest_path = self._reports_dir / f"{job_id}_audit_report.pdf"
        tmp_path = self._reports_dir / f"{job_id}_audit_report.pdf.tmp"

        try:
            tmp_path.write_bytes(pdf_bytes)
            os.replace(tmp_path, dest_path)
            return dest_path
        except (OSError, ValueError) as err:
            logger.error("Failed to write audit report PDF for job %s: %s", job_id, err)
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise

    def get_report_pdf_path(self, job_id: str) -> Path | None:
        """
        Returns Path to the generated audit report PDF if it exists, or None.
        """
        dest_path = self._reports_dir / f"{job_id}_audit_report.pdf"
        if dest_path.exists() and dest_path.is_file() and dest_path.stat().st_size > 0:
            return dest_path
        return None

    def get_report_pdf_bytes(self, job_id: str) -> bytes | None:
        """
        Reads and returns the binary content of the audit report PDF if it exists.
        """
        path = self.get_report_pdf_path(job_id)
        if path is None:
            return None
        try:
            return path.read_bytes()
        except OSError as err:
            logger.error("Failed to read audit report PDF for job %s: %s", job_id, err)
            return None

    def delete_report_pdf(self, job_id: str) -> bool:
        """
        Deletes the generated PDF report for job_id if present.
        """
        path = self.get_report_pdf_path(job_id)
        if path is not None and path.exists():
            try:
                path.unlink()
                return True
            except OSError as err:
                logger.error("Failed to delete audit report PDF for job %s: %s", job_id, err)
                return False
        return False
