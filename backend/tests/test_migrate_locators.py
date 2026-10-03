"""
AUD-037: tools/migrate_locators.py adds the FN-023 locator to legacy records without changing
review IDs. Runs the real tool (subprocess, venv interpreter) on a SYNTHETIC data dir.
"""

import json
import subprocess
import sys
from pathlib import Path

from app.ingestion.repository import JobRepository
from app.review.repository import ReviewRepository

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "migrate_locators.py"
BOX = {"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 220.0}


def _legacy_job(data_dir: Path) -> tuple[str, Path]:
    job = JobRepository(data_dir=data_dir).save_job(
        filename="synthetic.pdf", content=b"%PDF-1.4 synthetic", target_metric="Adjusted EBITDA", workflow_pack="non_gaap_bridge"
    )
    review = data_dir / "results" / f"{job.job_id}_review.json"
    review.parent.mkdir(parents=True, exist_ok=True)
    legacy = [
        {"id": "legacy-1", "value": "1,000", "label": "Synthetic row", "page": 2, "bbox": BOX, "source_file": "synthetic.pdf",
         "confidence_band": "needs_review", "confidence_score": 0.9, "status": "needs_review", "flags": []},
    ]
    review.write_text(json.dumps(legacy), encoding="utf-8")
    return job.job_id, review


def _run(data_dir: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(TOOL), "--data-dir", str(data_dir), *extra], capture_output=True, text=True, check=False)


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    _job, review = _legacy_job(tmp_path)
    before = review.read_bytes()
    proc = _run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "DRY RUN" in proc.stdout and "1 record(s)" in proc.stdout
    assert review.read_bytes() == before
    assert not list(review.parent.glob("*.pre-locator-migration.json"))


def test_apply_adds_locator_keeps_ids_and_backs_up(tmp_path: Path) -> None:
    job_id, review = _legacy_job(tmp_path)
    proc = _run(tmp_path, "--apply")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "VERIFY OK" in proc.stdout

    stored = json.loads(review.read_text(encoding="utf-8"))
    assert stored[0]["id"] == "legacy-1"
    assert stored[0]["locator"] == {"type": "pdf", "page": 2, "bbox": BOX, "source_file": "synthetic.pdf"}
    assert (review.parent / f"{job_id}_review.pre-locator-migration.json").exists()

    [item] = ReviewRepository(data_dir=tmp_path).get_review_items(job_id) or []
    assert item.id == "legacy-1" and item.page == 2 and item.source_file == "synthetic.pdf"

    again = _run(tmp_path, "--apply")
    assert "0 record(s)" in again.stdout  # idempotent
