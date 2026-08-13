"""
Extraction result repository for the extraction pipeline.

Scope: persist intermediate extraction outputs produced by Feature 2 steps
       to disk under data/results/.

Storage layout (relative to data_dir, default: backend/data/):
    results/<job_id>_docling.json   ← raw DoclingItem list from Step 1

Writes are atomic: content is written to a .tmp sibling and renamed into
place via os.replace so a failed write never leaves a partial file on disk
(CONSTITUTION §1.9).

Isolation (CONSTITUTION §3.8, §3.2):
    This module must NEVER import from ingestion/, classification/,
    formula_engine/, excel_export/, or audit_report/.
"""

import json
import os
from pathlib import Path

from app.extraction.models import DoclingItem, NormalizedItem

# Default data directory: backend/data/ (one level above the app/ package root).
# Tests override this by constructing ExtractionRepository(data_dir=tmp_path).
_DEFAULT_DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"


class ExtractionRepository:
    """Persist extraction stage outputs for the extraction pipeline."""

    def __init__(self, data_dir: Path = _DEFAULT_DATA_DIR) -> None:
        self._data_dir = data_dir
        self._results_dir = data_dir / "results"

    def _ensure_dirs(self) -> None:
        """Create data/results/ if it does not already exist."""
        self._results_dir.mkdir(parents=True, exist_ok=True)

    def save_docling_items(self, job_id: str, items: list[DoclingItem]) -> Path:
        """
        Persist raw DoclingItem objects for job_id to data/results/<job_id>_docling.json.

        Writes are atomic: content is written to a .tmp sibling and renamed
        into place via os.replace (CONSTITUTION §1.9 — no partial writes).

        Args:
            job_id: UUID of the job whose Docling parse results are being stored.
            items:  List of DoclingItem objects produced by docling_parser.parse_pdf().

        Returns:
            The Path to the written JSON file.
        """
        self._ensure_dirs()
        dest_path = self._results_dir / f"{job_id}_docling.json"
        tmp_path = self._results_dir / f"{job_id}_docling.json.tmp"

        payload = [item.model_dump() for item in items]
        tmp_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp_path, dest_path)
        return dest_path

    def save_normalized_items(self, job_id: str, items: list[NormalizedItem]) -> Path:
        """
        Persist NormalizedItem objects for job_id to data/results/<job_id>_normalized.json.

        Writes are atomic: content is written to a .tmp sibling and renamed
        into place via os.replace (CONSTITUTION §1.9 — no partial writes).

        Args:
            job_id: UUID of the job whose normalized items are being stored.
            items:  List of NormalizedItem objects produced by coordinate_normalizer.

        Returns:
            The Path to the written JSON file.
        """
        self._ensure_dirs()
        dest_path = self._results_dir / f"{job_id}_normalized.json"
        tmp_path = self._results_dir / f"{job_id}_normalized.json.tmp"

        payload = [item.model_dump() for item in items]
        tmp_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp_path, dest_path)
        return dest_path
