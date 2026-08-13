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

import pytest
from app.extraction.models import DoclingBbox, DoclingItem
from app.extraction.repository import ExtractionRepository


def _make_item(value: str = "100", label: str = "Net Sales") -> DoclingItem:
    return DoclingItem(
        value=value,
        label=label,
        page=1,
        bbox=DoclingBbox(x0=1.0, y0=2.0, x1=3.0, y1=4.0),
        source_file="test.pdf",
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
