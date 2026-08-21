"""
Excel Export & Provenance Repository (Feature 4 Step 4).

Follows CONSTITUTION §1.9:
- Atomic persistence via temporary file rename to prevent partial/corrupted writes.
"""

import json
import logging
import os
from pathlib import Path

from app.excel_export.models import (
    W3CAnnotationRecord,
    WorkbookGenerationResult,
)

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"


class ModelRepository:
    """
    Persist and retrieve generated workbooks and W3C Web Annotation provenance records.
    """

    def __init__(self, data_dir: Path = _DEFAULT_DATA_DIR) -> None:
        self._data_dir = data_dir
        self._models_dir = data_dir / "models"

    @property
    def data_dir(self) -> Path:
        """The root data directory for this repository instance."""
        return self._data_dir

    def _ensure_dirs(self) -> None:
        """Create data/models/ if missing."""
        self._models_dir.mkdir(parents=True, exist_ok=True)

    def get_workbook_path(self, job_id: str) -> Path | None:
        """Returns path to generated .xlsx workbook for job_id if it exists."""
        target = self._models_dir / f"{job_id}_model.xlsx"
        if target.exists():
            return target
        return None

    def save_provenance_records(
        self,
        job_id: str,
        records: list[W3CAnnotationRecord],
    ) -> Path:
        """
        Persists W3C Web Annotation records for job_id to data/models/<job_id>_provenance.json atomically.
        """
        self._ensure_dirs()
        dest_path = self._models_dir / f"{job_id}_provenance.json"
        tmp_path = self._models_dir / f"{job_id}_provenance.json.tmp"

        payload = [record.model_dump(by_alias=True) for record in records]
        tmp_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp_path, dest_path)
        return dest_path

    def get_provenance_records(self, job_id: str) -> list[W3CAnnotationRecord] | None:
        """
        Retrieves all W3C Web Annotation records for job_id from disk.
        """
        target_path = self._models_dir / f"{job_id}_provenance.json"
        if not target_path.exists():
            return None

        try:
            content = target_path.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, list):
                return [W3CAnnotationRecord.model_validate(item) for item in data]
            return None
        except (json.JSONDecodeError, OSError, ValueError) as err:
            logger.error(
                "Failed to load provenance records for job %s: %s", job_id, err
            )
            return None

    def get_cell_provenance(
        self,
        job_id: str,
        sheet_name: str,
        cell_coord: str,
    ) -> W3CAnnotationRecord | None:
        """
        Finds a specific W3C Web Annotation record by sheet name and cell coordinate.
        """
        records = self.get_provenance_records(job_id)
        if not records:
            return None

        target_coord = cell_coord.upper()
        for record in records:
            if (
                record.sheet_name == sheet_name
                and record.cell_coord.upper() == target_coord
            ):
                return record

        return None

    def save_generation_result(
        self,
        job_id: str,
        result: WorkbookGenerationResult,
    ) -> Path:
        """
        Persists WorkbookGenerationResult for job_id to data/models/<job_id>_generation.json atomically.
        """
        self._ensure_dirs()
        dest_path = self._models_dir / f"{job_id}_generation.json"
        tmp_path = self._models_dir / f"{job_id}_generation.json.tmp"

        payload = result.model_dump()
        tmp_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp_path, dest_path)
        return dest_path

    def get_generation_result(self, job_id: str) -> WorkbookGenerationResult | None:
        """
        Retrieves WorkbookGenerationResult for job_id from disk.
        """
        target_path = self._models_dir / f"{job_id}_generation.json"
        if not target_path.exists():
            return None

        try:
            content = target_path.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict):
                return WorkbookGenerationResult.model_validate(data)
            return None
        except (json.JSONDecodeError, OSError, ValueError) as err:
            logger.error("Failed to load generation result for job %s: %s", job_id, err)
            return None
