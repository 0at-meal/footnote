#!/usr/bin/env python
"""
Run the real extraction pipeline on one PDF in a throwaway data dir and print a JSON summary.

Never touches backend/data: FOOTNOTE_DATA_DIR is pointed at a temp (or given) directory before
the app is imported. The LLM classifier is replaced by an offline stub unless --live-llm is given,
so labels are never sent anywhere by default.

Usage (always with the venv interpreter):
    .venv/Scripts/python.exe tools/verify/run_pipeline.py path/to/filing.pdf
    .venv/Scripts/python.exe tools/verify/run_pipeline.py filing.pdf --pack non_gaap_bridge --data-dir C:/tmp/fn
    .venv/Scripts/python.exe tools/verify/run_pipeline.py filing.pdf --force-pymupdf   # degraded parser
"""

import argparse
import collections
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--pack", default="non_gaap_bridge")
    parser.add_argument("--target-metric", default="Adjusted EBITDA")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--live-llm", action="store_true", help="use the configured Groq classifier")
    parser.add_argument("--force-pymupdf", action="store_true", help="simulate missing Docling (degraded mode)")
    args = parser.parse_args()

    data_dir = (args.data_dir or Path(tempfile.mkdtemp(prefix="footnote-verify-"))).resolve()
    if data_dir == (ROOT / "backend" / "data").resolve():
        print("Refusing to run against backend/data (user data).", file=sys.stderr)
        return 2
    os.environ["FOOTNOTE_DATA_DIR"] = str(data_dir)
    sys.path.insert(0, str(ROOT / "backend"))

    from unittest.mock import MagicMock

    from app.classification.models import ClassifierRawResponse
    from app.extraction import docling_parser
    from app.extraction.repository import ExtractionRepository
    from app.ingestion.repository import JobRepository
    from app.job_runner import process_queued_job
    from app.review.repository import ReviewRepository

    if args.force_pymupdf:
        os.environ["ALLOW_PYMUPDF_FALLBACK"] = "1"
        docling_parser.DOCLING_IMPORT_ERROR = "simulated: --force-pymupdf"

    client = None
    if not args.live_llm:
        client = MagicMock()
        client.classify.return_value = ClassifierRawResponse(label="Other", confidence=0.5)

    repo = JobRepository(data_dir=data_dir)
    job = repo.save_job(
        filename=args.pdf.name,
        content=args.pdf.read_bytes(),
        target_metric=args.target_metric,
        workflow_pack=args.pack,
    )
    error = None
    try:
        process_queued_job(job.job_id, repo, classifier_client=client)
    except Exception as exc:  # noqa: BLE001 - reported in the JSON summary
        error = f"{type(exc).__name__}: {exc}"

    final = repo.get_job(job.job_id)
    summary = ExtractionRepository(data_dir=data_dir).get_extraction_summary(job.job_id)
    items = ReviewRepository(data_dir=data_dir).get_review_items(job.job_id) or []
    statuses = collections.Counter(str(getattr(i.status, "value", i.status)) for i in items)
    flagged = sum(v for k, v in statuses.items() if k not in ("locked", "auto_accepted"))
    out = {
        "data_dir": str(data_dir),
        "job_id": job.job_id,
        "status": final.status.value if final else None,
        "model_ready": final.model_ready if final else None,
        "model_skip_reason": final.model_skip_reason if final else None,
        "failure_reason": final.failure_reason if final else None,
        "parser_used": final.parser_used if final else None,
        "parser_fallback_reason": final.parser_fallback_reason if final else None,
        "workbook_exists": (data_dir / "models" / f"{job.job_id}_model.xlsx").exists(),
        "summary": summary.model_dump() if summary else None,
        "review_items": len(items),
        "review_status_counts": dict(statuses),
        "flagged": flagged,
        "flagged_pct": round(100 * flagged / len(items), 1) if items else 0.0,
        "error": error,
    }
    print(json.dumps(out, indent=2, default=str))
    return 0 if error is None else 1


if __name__ == "__main__":
    sys.exit(main())
