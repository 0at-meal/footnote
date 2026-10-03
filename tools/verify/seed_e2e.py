#!/usr/bin/env python
"""
Seed an isolated data dir for the Playwright e2e suite.

Creates a SYNTHETIC two-page filing (balance sheet on page 1, Adjusted EBITDA bridge on page 2;
invented data from backend/tests/fixtures/synthetic) twice and runs the real pipeline on it: once
with Docling and once in degraded PyMuPDF mode, with the offline classifier stub. Writes
<data-dir>/e2e_manifest.json with each job and the PyMuPDF location of every review item's value
text (used to check highlight placement).

Usage:
    .venv/Scripts/python.exe tools/verify/seed_e2e.py --data-dir <dir>
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bbox_probe import probe_job
from tests.fixtures.synthetic.pdfs import (
    SYNTHETIC_BALANCE_SHEET,
    SYNTHETIC_EBITDA_BRIDGE,
    write_synthetic_pdf,
)

JOBS = {
    "docling": ("synthetic_two_page_filing.pdf", False),
    "pymupdf": ("synthetic_two_page_filing_pymupdf.pdf", True),
}


def seed_job(data_dir: Path, filename: str, force_pymupdf: bool) -> dict[str, object]:
    pdf = write_synthetic_pdf(
        data_dir / "_seed" / filename, [SYNTHETIC_BALANCE_SHEET, SYNTHETIC_EBITDA_BRIDGE]
    )
    cmd = [sys.executable, str(ROOT / "tools" / "verify" / "run_pipeline.py"), str(pdf), "--data-dir", str(data_dir)]
    if force_pymupdf:
        cmd.append("--force-pymupdf")
    run = subprocess.run(cmd, capture_output=True, text=True, check=False)
    start = run.stdout.find("{")
    if run.returncode != 0 or start < 0:
        raise RuntimeError(f"pipeline failed for {filename}: {run.stdout} {run.stderr}")
    result = json.loads(run.stdout[start:])
    job_id = str(result["job_id"])
    probe = probe_job(data_dir, job_id)
    return {
        "job_id": job_id,
        "filename": filename,
        "status": result["status"],
        "parser_used": result["parser_used"],
        "review_items": result["review_items"],
        "bbox_probe": {k: probe[k] for k in ("hit", "miss", "value_not_found_on_page", "hit_rate")},
        "expected_value_rects": probe["expected_value_rects"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, required=True)
    args = ap.parse_args()
    data_dir = args.data_dir.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    manifest = {name: seed_job(data_dir, filename, force) for name, (filename, force) in JOBS.items()}
    (data_dir / "e2e_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    summary = {
        name: {k: v for k, v in job.items() if k != "expected_value_rects"} for name, job in manifest.items()
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
