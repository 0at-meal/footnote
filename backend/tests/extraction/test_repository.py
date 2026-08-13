"""
Unit tests for app.extraction.repository.ExtractionRepository.

Tests use pytest's tmp_path fixture so no real data/ directory is
ever created or touched.

Tests verify:
- Docling items are persisted atomically to data/results/<job_id>_docling.json.
- Written JSON content is readable and contains the expected fields.
- data/results/ is created on first write if it does not exist.
"""

from pathlib import Path

from app.extraction.models import (
    ConfidenceBand,
    DoclingBbox,
    DoclingItem,
    ExtractedRecord,
    NormalizedBbox,
    NormalizedItem,
    ScoredRecord,
)
from app.extraction.repository import ExtractionRepository


def _make_item(value: str = "100", label: str = "Net Sales") -> DoclingItem:
    return DoclingItem(
        value=value,
        label=label,
        page=1,
        bbox=DoclingBbox(x0=1.0, y0=2.0, x1=3.0, y1=4.0),
        source_file="test.pdf",
    )


def _make_normalized_item(
    value: str = "100", label: str = "Net Sales"
) -> NormalizedItem:
    return NormalizedItem(
        value=value,
        label=label,
        page=1,
        bbox=NormalizedBbox(x0=100.0, y0=200.0, x1=300.0, y1=400.0),
        source_file="test.pdf",
    )


def _make_extracted_record(
    value: str = "100", label: str = "Net Sales"
) -> ExtractedRecord:
    return ExtractedRecord(
        value=value,
        label=label,
        page=1,
        bbox={"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 400.0},
        source_file="test.pdf",
    )


def _make_scored_record(value: str = "100", label: str = "Net Sales") -> ScoredRecord:
    return ScoredRecord(
        record=_make_extracted_record(value=value, label=label),
        confidence_score=0.98,
        confidence_band=ConfidenceBand.auto_accepted,
        flags=[],
    )


# ── save_docling_items ────────────────────────────────────────────────────────


def test_save_docling_items_creates_results_dir(tmp_path: Path) -> None:
    repo = ExtractionRepository(data_dir=tmp_path)
    assert not (tmp_path / "results").exists()
    repo.save_docling_items("job-abc", [_make_item()])
    assert (tmp_path / "results").is_dir()


def test_save_docling_items_returns_correct_path(tmp_path: Path) -> None:
    repo = ExtractionRepository(data_dir=tmp_path)
    job_id = "job-docling-test"
    dest_path = repo.save_docling_items(job_id, [_make_item()])
    assert dest_path == tmp_path / "results" / f"{job_id}_docling.json"


def test_save_docling_items_file_exists_after_write(tmp_path: Path) -> None:
    repo = ExtractionRepository(data_dir=tmp_path)
    dest_path = repo.save_docling_items("job-exists", [_make_item()])
    assert dest_path.exists()


def test_save_docling_items_json_content_is_correct(tmp_path: Path) -> None:
    repo = ExtractionRepository(data_dir=tmp_path)
    item = _make_item(value="500", label="Net Sales")
    dest_path = repo.save_docling_items("job-content", [item])

    text = dest_path.read_text(encoding="utf-8")
    assert "Net Sales" in text
    assert "500" in text


def test_save_docling_items_empty_list_produces_empty_array(tmp_path: Path) -> None:
    repo = ExtractionRepository(data_dir=tmp_path)
    dest_path = repo.save_docling_items("job-empty", [])
    text = dest_path.read_text(encoding="utf-8")
    assert text.strip() == "[]"


def test_save_docling_items_no_tmp_file_left_on_disk(tmp_path: Path) -> None:
    repo = ExtractionRepository(data_dir=tmp_path)
    repo.save_docling_items("job-tmp", [_make_item()])
    tmp_files = list((tmp_path / "results").glob("*.tmp"))
    assert tmp_files == [], f"Unexpected .tmp files left on disk: {tmp_files}"


# ── save_normalized_items ─────────────────────────────────────────────────────


def test_save_normalized_items_returns_correct_path(tmp_path: Path) -> None:
    repo = ExtractionRepository(data_dir=tmp_path)
    job_id = "job-norm-test"
    dest_path = repo.save_normalized_items(job_id, [_make_normalized_item()])
    assert dest_path == tmp_path / "results" / f"{job_id}_normalized.json"
    assert dest_path.exists()


def test_save_normalized_items_json_content_is_correct(tmp_path: Path) -> None:
    repo = ExtractionRepository(data_dir=tmp_path)
    item = _make_normalized_item(value="800", label="Operating Margin")
    dest_path = repo.save_normalized_items("job-norm-content", [item])

    text = dest_path.read_text(encoding="utf-8")
    assert "Operating Margin" in text
    assert "800" in text
    assert "100.0" in text
    assert "400.0" in text


# ── save_extracted_records ───────────────────────────────────────────────────


def test_save_extracted_records_returns_correct_path(tmp_path: Path) -> None:
    repo = ExtractionRepository(data_dir=tmp_path)
    job_id = "job-rec-test"
    dest_path = repo.save_extracted_records(job_id, [_make_extracted_record()])
    assert dest_path == tmp_path / "results" / f"{job_id}_records.json"
    assert dest_path.exists()


def test_save_extracted_records_json_content_is_correct(tmp_path: Path) -> None:
    repo = ExtractionRepository(data_dir=tmp_path)
    record = _make_extracted_record(value="999", label="EBITDA")
    dest_path = repo.save_extracted_records("job-rec-content", [record])

    text = dest_path.read_text(encoding="utf-8")
    assert "EBITDA" in text
    assert "999" in text
    assert '"x0": 100.0' in text


# ── save_scored_records ───────────────────────────────────────────────────────


def test_save_scored_records_returns_correct_path(tmp_path: Path) -> None:
    repo = ExtractionRepository(data_dir=tmp_path)
    job_id = "job-scored-test"
    dest_path = repo.save_scored_records(job_id, [_make_scored_record()])
    assert dest_path == tmp_path / "results" / f"{job_id}_scored.json"
    assert dest_path.exists()


def test_save_scored_records_json_content_is_correct(tmp_path: Path) -> None:
    repo = ExtractionRepository(data_dir=tmp_path)
    scored = _make_scored_record(value="777", label="Gross Profit")
    dest_path = repo.save_scored_records("job-scored-content", [scored])

    text = dest_path.read_text(encoding="utf-8")
    assert "Gross Profit" in text
    assert "777" in text
    assert '"confidence_band": "auto_accepted"' in text
    assert '"confidence_score": 0.98' in text
