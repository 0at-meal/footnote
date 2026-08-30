"""
Repository for persisting and loading Narrative Sections and Diffs (Feature 10, Step G).

Adheres to:
- CONSTITUTION §1.1: mypy --strict compliance.
- CONSTITUTION §1.9: Atomic file write pattern with tempfile rename.
"""

import json
import logging
import os
from pathlib import Path

from app.extraction.repository import ExtractionRepository
from app.narrative.extractor import extract_narrative_sections
from app.narrative.models import NarrativeDiff, NarrativeSection

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"


class NarrativeRepository:
    """
    Persists and retrieves narrative sections and diff results.
    """

    def __init__(self, data_dir: Path = _DEFAULT_DATA_DIR) -> None:
        self._data_dir = data_dir
        self._narrative_dir = data_dir / "narratives"
        self._narrative_dir.mkdir(parents=True, exist_ok=True)

    def _sections_path(self, job_id: str) -> Path:
        return self._narrative_dir / f"{job_id}_sections.json"

    def _diff_path(
        self, company_id: str, earlier_job: str, later_job: str, item_no: str
    ) -> Path:
        clean_item = item_no.replace(" ", "_").lower()
        return (
            self._narrative_dir
            / f"{company_id}_{earlier_job}_{later_job}_{clean_item}_diff.json"
        )

    def get_sections(self, job_id: str) -> list[NarrativeSection]:
        """
        Load persisted narrative sections for a job or compile on demand from extraction records.
        """
        path = self._sections_path(job_id)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return [NarrativeSection.model_validate(s) for s in data]
            except (json.JSONDecodeError, OSError, ValueError) as err:
                logger.warning(
                    "Failed to read narrative sections for %s: %s", job_id, err
                )

        ext_repo = ExtractionRepository(data_dir=self._data_dir)
        scored_records = ext_repo.get_scored_records(job_id)
        if not scored_records:
            return []

        sections = extract_narrative_sections(
            job_id=job_id, records_or_items=scored_records
        )
        if sections:
            self.save_sections(job_id, sections)
        return sections

    def save_sections(self, job_id: str, sections: list[NarrativeSection]) -> Path:
        """
        Save narrative sections to disk atomically using atomic tempfile rename.
        """
        target_path = self._sections_path(job_id)
        tmp_path = target_path.with_suffix(".tmp")

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump([s.model_dump() for s in sections], f, indent=2)

        os.replace(tmp_path, target_path)
        return target_path

    def save_diff(self, diff: NarrativeDiff) -> Path:
        """
        Save NarrativeDiff to disk atomically.
        """
        cid = diff.company_id or "general"
        target_path = self._diff_path(
            cid, diff.earlier_job_id, diff.later_job_id, diff.item_number
        )
        tmp_path = target_path.with_suffix(".tmp")

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(diff.model_dump(), f, indent=2)

        os.replace(tmp_path, target_path)
        return target_path

    def get_diff(
        self, company_id: str, earlier_job: str, later_job: str, item_no: str
    ) -> NarrativeDiff | None:
        """
        Load persisted NarrativeDiff if exists.
        """
        path = self._diff_path(company_id, earlier_job, later_job, item_no)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return NarrativeDiff.model_validate(data)
        except (json.JSONDecodeError, OSError, ValueError):
            return None
