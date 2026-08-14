"""
Classification stage repository for persisting and loading classified records (Feature 3).

Follows CONSTITUTION §1.9:
- Atomic persistence via temporary file rename to prevent partial/corrupted writes.
"""

import json
import logging
import os
from pathlib import Path

from app.classification.models import ClassifiedRecord

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"


class ClassificationRepository:
    """
    Persist and retrieve classified records under data/results/.
    """

    def __init__(self, data_dir: Path = _DEFAULT_DATA_DIR) -> None:
        self._data_dir = data_dir
        self._results_dir = data_dir / "results"

    def _ensure_dirs(self) -> None:
        """Create data/results/ if missing."""
        self._results_dir.mkdir(parents=True, exist_ok=True)

    def save_classified_records(
        self,
        job_id: str,
        records: list[ClassifiedRecord],
    ) -> Path:
        """
        Persists ClassifiedRecord objects for job_id to data/results/<job_id>_classified.json atomically.
        """
        self._ensure_dirs()
        dest_path = self._results_dir / f"{job_id}_classified.json"
        tmp_path = self._results_dir / f"{job_id}_classified.json.tmp"

        payload = [record.model_dump() for record in records]
        tmp_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp_path, dest_path)
        return dest_path

    def get_classified_records(self, job_id: str) -> list[ClassifiedRecord] | None:
        """
        Retrieves ClassifiedRecord objects for job_id from data/results/<job_id>_classified.json.
        """
        target_path = self._results_dir / f"{job_id}_classified.json"
        if not target_path.exists():
            return None

        try:
            content = target_path.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, list):
                return [ClassifiedRecord.model_validate(item) for item in data]
            return None
        except (json.JSONDecodeError, OSError, ValueError) as err:
            logger.error("Failed to load classified records for job %s: %s", job_id, err)
            return None
