"""
Review repository for loading and updating extraction records for human review (Feature 5).

Governed by CONSTITUTION §1.1 (mypy --strict), §1.9 (atomic persistence), §3.9 (review stage isolation).
"""

import json
import logging
import os
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
    Loads and updates review items for a job, persisting state under data/results/<job_id>_review.json.
    """

    def __init__(self, data_dir: Path = _DEFAULT_DATA_DIR) -> None:
        self._data_dir = data_dir
        self._classification_repo = ClassificationRepository(data_dir=data_dir)
        self._extraction_repo = ExtractionRepository(data_dir=data_dir)
        self._results_dir = data_dir / "results"

    def _ensure_dirs(self) -> None:
        """Create data/results/ if missing."""
        self._results_dir.mkdir(parents=True, exist_ok=True)

    def save_review_items(self, job_id: str, items: list[ReviewItem]) -> Path:
        """
        Persists ReviewItem objects for job_id to data/results/<job_id>_review.json atomically.
        """
        self._ensure_dirs()
        dest_path = self._results_dir / f"{job_id}_review.json"
        tmp_path = self._results_dir / f"{job_id}_review.json.tmp"

        payload = [item.model_dump() for item in items]
        tmp_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp_path, dest_path)
        return dest_path

    def get_review_items(self, job_id: str) -> list[ReviewItem] | None:
        """
        Retrieve review items for a job.

        1. Checks for persisted review state (<job_id>_review.json).
        2. Falls back to loading from classified or scored records and initializes review state.
        3. Returns None if no records exist for job_id.

        Args:
            job_id: The UUID of the job.

        Returns:
            List of ReviewItem objects or None if no result files exist for job_id.
        """
        self._ensure_dirs()
        review_path = self._results_dir / f"{job_id}_review.json"
        if review_path.exists():
            try:
                content = review_path.read_text(encoding="utf-8")
                raw_data = json.loads(content)
                if isinstance(raw_data, list):
                    return [ReviewItem.model_validate(item) for item in raw_data]
            except (json.JSONDecodeError, OSError, ValueError) as err:
                logger.error("Failed to load review state for job %s: %s", job_id, err)

        # Initialize from classified records if present
        classified_records = self._classification_repo.get_classified_records(job_id)
        if classified_records is not None:
            items = self._from_classified_records(job_id, classified_records)
            self.save_review_items(job_id, items)
            return items

        # Fall back to scored records
        scored_path = self._results_dir / f"{job_id}_scored.json"
        if scored_path.exists():
            try:
                content = scored_path.read_text(encoding="utf-8")
                raw_data = json.loads(content)
                if isinstance(raw_data, list):
                    scored_records = [ScoredRecord.model_validate(item) for item in raw_data]
                    items = self._from_scored_records(job_id, scored_records)
                    self.save_review_items(job_id, items)
                    return items
            except (json.JSONDecodeError, OSError, ValueError) as err:
                logger.error("Failed to load scored records for job %s: %s", job_id, err)
                return None

        return None

    def update_item(
        self,
        job_id: str,
        item_id: str,
        value: str | None = None,
        label: str | None = None,
    ) -> tuple[ReviewItem | None, str | None]:
        """
        Edit the value or label of a review item.

        Enforces:
        - Non-empty label (EC-4).
        - Preserves frozen fields (bbox, page, source_file per AC-9).
        - Does not auto-confirm (AC-8).
        - Recovers extraction_error status upon valid correction (EC-1).
        """
        items = self.get_review_items(job_id)
        if items is None:
            return None, "Job records not found"

        target_item: ReviewItem | None = None
        for item in items:
            if item.id == item_id:
                target_item = item
                break

        if target_item is None:
            return None, f"Item with id '{item_id}' not found"

        if target_item.status == ReviewStatus.locked:
            return None, "Cannot edit a locked item. Please unlock it first."

        if label is not None:
            if not label.strip():
                return None, "Label cannot be empty."
            target_item.label = label

        if value is not None:
            target_item.value = value

        # If it was an extraction error and now has content, transition to review status
        if target_item.status == ReviewStatus.extraction_error and target_item.value.strip() != "":
            if target_item.confidence_band == ConfidenceBand.needs_review:
                target_item.status = ReviewStatus.needs_review
            else:
                target_item.status = ReviewStatus.manual_required
            target_item.error_detail = None

        self.save_review_items(job_id, items)
        return target_item, None

    def confirm_item(
        self,
        job_id: str,
        item_id: str,
        add_to_taxonomy: bool = False,
    ) -> tuple[ReviewItem | None, str | None]:
        """
        Confirm an item, transitioning it to locked status (AC-4, AC-5).

        Enforces:
        - Cannot confirm extraction_error items (EC-1).
        - Prompts/requires taxonomy confirmation for unrecognized labels (EC-5).
        - Clears any existing flag state (AC-7).
        """
        items = self.get_review_items(job_id)
        if items is None:
            return None, "Job records not found"

        target_item: ReviewItem | None = None
        for item in items:
            if item.id == item_id:
                target_item = item
                break

        if target_item is None:
            return None, f"Item with id '{item_id}' not found"

        if target_item.status == ReviewStatus.extraction_error:
            return (
                None,
                "Cannot confirm an item with extraction error. Please edit with valid values first.",
            )

        if (
            target_item.status == ReviewStatus.pending_taxonomy_confirmation
            and not add_to_taxonomy
        ):
            return (
                None,
                "Taxonomy addition confirmation required for unrecognized label.",
            )

        if add_to_taxonomy:
            target_item.taxonomy_status = "matched"
            if target_item.normalized_label is None:
                target_item.normalized_label = target_item.label

        target_item.status = ReviewStatus.locked
        self.save_review_items(job_id, items)
        return target_item, None

    def flag_item(
        self,
        job_id: str,
        item_id: str,
    ) -> tuple[ReviewItem | None, str | None]:
        """
        Flag an item or toggle its flagged state (AC-4, AC-7, EC-8).

        Enforces:
        - Mutually exclusive with locked: cannot flag a locked item (AC-7).
        """
        items = self.get_review_items(job_id)
        if items is None:
            return None, "Job records not found"

        target_item: ReviewItem | None = None
        for item in items:
            if item.id == item_id:
                target_item = item
                break

        if target_item is None:
            return None, f"Item with id '{item_id}' not found"

        if target_item.status == ReviewStatus.locked:
            return None, "Cannot flag a locked item."

        if target_item.status == ReviewStatus.flagged:
            # Toggle flag off, returning to baseline status
            if target_item.taxonomy_status == "pending_taxonomy_confirmation":
                target_item.status = ReviewStatus.pending_taxonomy_confirmation
            elif target_item.confidence_band == ConfidenceBand.auto_accepted:
                target_item.status = ReviewStatus.auto_accepted
            elif target_item.confidence_band == ConfidenceBand.needs_review:
                target_item.status = ReviewStatus.needs_review
            else:
                target_item.status = ReviewStatus.manual_required
        else:
            target_item.status = ReviewStatus.flagged

        self.save_review_items(job_id, items)
        return target_item, None

    def unlock_item(
        self,
        job_id: str,
        item_id: str,
    ) -> tuple[ReviewItem | None, str | None]:
        """
        Explicitly unlock a locked item (spec AC-6).

        Transitions out of locked status back to baseline review status:
        - pending_taxonomy_confirmation if taxonomy_status is pending
        - auto_accepted / needs_review / manual_required based on confidence_band.
        """
        items = self.get_review_items(job_id)
        if items is None:
            return None, "Job records not found"

        target_item: ReviewItem | None = None
        for item in items:
            if item.id == item_id:
                target_item = item
                break

        if target_item is None:
            return None, f"Item with id '{item_id}' not found"

        if target_item.status != ReviewStatus.locked:
            return None, "Item is not currently locked."

        # Transition out of locked back to baseline review status
        if target_item.taxonomy_status == "pending_taxonomy_confirmation":
            target_item.status = ReviewStatus.pending_taxonomy_confirmation
        elif target_item.confidence_band == ConfidenceBand.auto_accepted:
            target_item.status = ReviewStatus.auto_accepted
        elif target_item.confidence_band == ConfidenceBand.needs_review:
            target_item.status = ReviewStatus.needs_review
        else:
            target_item.status = ReviewStatus.manual_required

        self.save_review_items(job_id, items)
        return target_item, None

    def protect_locked_items(
        self,
        job_id: str,
        new_items: list[ReviewItem],
    ) -> list[ReviewItem]:
        """
        Merge newly extracted/classified items while preserving locked items byte-identically (spec AC-5, EC-10).
        """
        existing = self.get_review_items(job_id)
        if not existing:
            self.save_review_items(job_id, new_items)
            return new_items

        locked_map = {item.id: item for item in existing if item.status == ReviewStatus.locked}
        merged: list[ReviewItem] = []
        for new_item in new_items:
            if new_item.id in locked_map:
                # Retain the locked item byte-identically
                merged.append(locked_map[new_item.id])
            else:
                merged.append(new_item)

        self.save_review_items(job_id, merged)
        return merged

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
