#!/usr/bin/env python
"""
Seed an isolated data dir for the Playwright e2e suite.

Creates a SYNTHETIC two-page filing (balance sheet on page 1, Adjusted EBITDA bridge on page 2;
invented data from backend/tests/fixtures/synthetic), runs the real pipeline (Docling) on it with
the offline classifier stub, and writes <data-dir>/e2e_manifest.json describing the job and the
PyMuPDF location of every review item's value text (used to check highlight placement).

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

FILENAME = "synthetic_two_page_filing.pdf"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, required=True)
    ap.add_argument("--force-pymupdf", action="store_true")
    args = ap.parse_args()
    data_dir = args.data_dir.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    pdf = write_synthetic_pdf(data_dir / "_seed" / FILENAME, [SYNTHETIC_BALANCE_SHEET, SYNTHETIC_EBITDA_BRIDGE])
    cmd = [sys.executable, str(ROOT / "tools" / "verify" / "run_pipeline.py"), str(pdf), "--data-dir", str(data_dir)]
    if args.force_pymupdf:
        cmd.append("--force-pymupdf")
    run = subprocess.run(cmd, capture_output=True, text=True, check=False)
    start = run.stdout.find("{")
    if run.returncode != 0 or start < 0:
        print(run.stdout, run.stderr, file=sys.stderr)
        return 1
    result = json.loads(run.stdout[start:])
    job_id = result["job_id"]
    # Materialise review items, then record expected value locations.
    probe = probe_job(data_dir, job_id)
    manifest = {
        "job_id": job_id,
        "filename": FILENAME,
        "status": result["status"],
        "parser_used": result["parser_used"],
        "review_items": result["review_items"],
        "bbox_probe": {k: probe[k] for k in ("hit", "miss", "value_not_found_on_page", "hit_rate")},
        "expected_value_rects": probe["expected_value_rects"],
    }
    (data_dir / "e2e_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k != "expected_value_rects"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
