"""
Review repository for loading extraction and classification records for human review (Feature 5).

Governed by CONSTITUTION §1.1 (mypy --strict), §3.9 (review stage isolation).
"""

import json
import logging
from pathlib import Path

from app.classification.models import ClassifiedRecord, TaxonomyStatus
from app.classification.repository import ClassificationRepository
from app.extraction.models import ConfidenceBand, ScoredRecord
from app.extraction.repository import ExtractionRepository
from app.review.models import ReviewItem, ReviewStatus

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"


class ReviewRepository:
    """
    Loads extraction items for a job from classified or scored result stores.
    """

    def __init__(self, data_dir: Path = _DEFAULT_DATA_DIR) -> None:
        self._data_dir = data_dir
        self._classification_repo = ClassificationRepository(data_dir=data_dir)
        self._extraction_repo = ExtractionRepository(data_dir=data_dir)
        self._results_dir = data_dir / "results"

    def get_review_items(self, job_id: str) -> list[ReviewItem] | None:
        """
        Retrieve review items for a job.

        First attempts to load classified records; if unavailable, falls back to
        scored extraction records. Returns None if neither file exists.

        Args:
            job_id: The UUID of the job.

        Returns:
            List of ReviewItem objects or None if no result files exist for job_id.
        """
        # 1. Try classified records
        classified_records = self._classification_repo.get_classified_records(job_id)
        if classified_records is not None:
            return self._from_classified_records(job_id, classified_records)

        # 2. Fall back to scored records
        scored_path = self._results_dir / f"{job_id}_scored.json"
        if scored_path.exists():
            try:
                content = scored_path.read_text(encoding="utf-8")
                raw_data = json.loads(content)
                if isinstance(raw_data, list):
                    scored_records = [ScoredRecord.model_validate(item) for item in raw_data]
                    return self._from_scored_records(job_id, scored_records)
            except (json.JSONDecodeError, OSError, ValueError) as err:
                logger.error("Failed to load scored records for job %s: %s", job_id, err)
                return None

        return None

    def _from_classified_records(
        self,
        job_id: str,
        records: list[ClassifiedRecord],
    ) -> list[ReviewItem]:
        """Convert ClassifiedRecord objects into review items."""
        items: list[ReviewItem] = []
        for idx, cr in enumerate(records):
            sr = cr.record
            er = sr.record

            # Derive review status
            if sr.status == "extraction_error":
                status = ReviewStatus.extraction_error
            elif cr.taxonomy_status == TaxonomyStatus.pending_taxonomy_confirmation:
                status = ReviewStatus.pending_taxonomy_confirmation
            elif sr.confidence_band == ConfidenceBand.auto_accepted:
                status = ReviewStatus.auto_accepted
            elif sr.confidence_band == ConfidenceBand.needs_review:
                status = ReviewStatus.needs_review
            else:
                status = ReviewStatus.manual_required

            taxonomy_status_val: str | None = None
            if cr.taxonomy_status is not None:
                taxonomy_status_val = (
                    cr.taxonomy_status.value
                    if isinstance(cr.taxonomy_status, TaxonomyStatus)
                    else str(cr.taxonomy_status)
                )

            items.append(
                ReviewItem(
                    id=f"{job_id}_{idx}",
                    value=er.value,
                    label=er.label,
                    page=er.page,
                    bbox=er.bbox,
                    source_file=er.source_file,
                    confidence_band=sr.confidence_band,
                    confidence_score=sr.confidence_score,
                    normalized_label=cr.normalized_label,
                    taxonomy_status=taxonomy_status_val,
                    status=status,
                    flags=sr.flags,
                    error_detail=sr.error_detail,
                )
            )
        return items

    def _from_scored_records(
        self,
        job_id: str,
        records: list[ScoredRecord],
    ) -> list[ReviewItem]:
        """Convert ScoredRecord objects into review items when classification has not run."""
        items: list[ReviewItem] = []
        for idx, sr in enumerate(records):
            er = sr.record

            if sr.status == "extraction_error":
                status = ReviewStatus.extraction_error
            elif sr.confidence_band == ConfidenceBand.auto_accepted:
                status = ReviewStatus.auto_accepted
            elif sr.confidence_band == ConfidenceBand.needs_review:
                status = ReviewStatus.needs_review
            else:
                status = ReviewStatus.manual_required

            items.append(
                ReviewItem(
                    id=f"{job_id}_{idx}",
                    value=er.value,
                    label=er.label,
                    page=er.page,
                    bbox=er.bbox,
                    source_file=er.source_file,
                    confidence_band=sr.confidence_band,
                    confidence_score=sr.confidence_score,
                    normalized_label=None,
                    taxonomy_status=None,
                    status=status,
                    flags=sr.flags,
                    error_detail=sr.error_detail,
                )
            )
        return items
