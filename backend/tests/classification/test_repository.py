"""
Unit tests for ClassificationRepository persistence (Feature 3 Step 3).

Validates:
- Atomic file writes under data/results/<job_id>_classified.json (CONSTITUTION §1.9)
- Round-trip serialization and deserialization of ClassifiedRecords
- Missing job handling returning None
"""

from pathlib import Path

from app.classification.models import ClassifiedRecord, TaxonomyStatus
from app.classification.repository import ClassificationRepository
from app.extraction.models import (
    ConfidenceBand,
    ExtractedRecord,
    ScoredRecord,
)


def create_sample_classified_record(
    label: str,
    normalized_label: str | None = None,
    status: TaxonomyStatus = TaxonomyStatus.matched,
) -> ClassifiedRecord:
    record = ExtractedRecord(
        value="500",
        label=label,
        page=1,
        bbox={"x0": 10.0, "y0": 20.0, "x1": 80.0, "y1": 40.0},
        source_file="sample.pdf",
    )
    scored = ScoredRecord(
        record=record,
        confidence_score=0.97,
        confidence_band=ConfidenceBand.auto_accepted,
        flags=[],
        status="ok",
    )
    return ClassifiedRecord(
        record=scored,
        normalized_label=normalized_label,
        taxonomy_status=status,
        classifier_confidence=0.95 if normalized_label else None,
        is_confirmed=normalized_label is not None,
    )


def test_save_classified_records_atomic_write(tmp_path: Path) -> None:
    repo = ClassificationRepository(data_dir=tmp_path)
    job_id = "job-test-uuid-1"
    records = [
        create_sample_classified_record(
            "Stock compensation",
            "Stock-Based Compensation",
            TaxonomyStatus.matched,
        )
    ]

    saved_path = repo.save_classified_records(job_id, records)
    assert saved_path.exists()
    assert not (tmp_path / "results" / f"{job_id}_classified.json.tmp").exists()
    assert saved_path.name == f"{job_id}_classified.json"


def test_get_classified_records_roundtrip(tmp_path: Path) -> None:
    repo = ClassificationRepository(data_dir=tmp_path)
    job_id = "job-test-uuid-2"
    records = [
        create_sample_classified_record(
            "Stock comp",
            "Stock-Based Compensation",
            TaxonomyStatus.matched,
        ),
        create_sample_classified_record(
            "Pending item",
            None,
            TaxonomyStatus.pending_taxonomy_confirmation,
        ),
    ]

    repo.save_classified_records(job_id, records)
    loaded = repo.get_classified_records(job_id)

    assert loaded is not None
    assert len(loaded) == 2

    assert loaded[0].normalized_label == "Stock-Based Compensation"
    assert loaded[0].is_confirmed is True
    assert loaded[0].taxonomy_status == TaxonomyStatus.matched
    assert loaded[0].record.record.label == "Stock comp"
    assert loaded[0].record.record.value == "500"

    assert loaded[1].normalized_label is None
    assert loaded[1].is_confirmed is False
    assert loaded[1].taxonomy_status == TaxonomyStatus.pending_taxonomy_confirmation
    assert loaded[1].record.record.label == "Pending item"


def test_get_classified_records_missing_returns_none(tmp_path: Path) -> None:
    repo = ClassificationRepository(data_dir=tmp_path)
    result = repo.get_classified_records("non-existent-job-id")
    assert result is None
