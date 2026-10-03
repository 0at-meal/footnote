#!/usr/bin/env python
"""
Bounding-box probe (AUD-002 verification, re-created from the audit's scratchpad probe).

For every review item of a job: does the item's stored bbox (0-1000 page space) contain the
PyMuPDF location of the item's own value text on that page? Prints hit/miss counts and examples.

Usage:
    .venv/Scripts/python.exe tools/verify/bbox_probe.py --data-dir <dir> [--job <job_id>] [--json]
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pymupdf


def value_locations(page: Any, value: str) -> list[tuple[float, float, float, float]]:
    """All 0-1000 rects where the value text appears on the page."""
    needle = value.strip().lstrip("$").strip()
    if not needle:
        return []
    # Filings print nil cells as an em/en dash; the parser stores them as "-".
    needles = [needle, "—", "–"] if needle == "-" else [needle]
    width, height = page.rect.width, page.rect.height
    return [
        (r.x0 / width * 1000, r.y0 / height * 1000, r.x1 / width * 1000, r.y1 / height * 1000)
        for n in needles
        for r in page.search_for(n)
    ]


def contains_center(bbox: dict[str, float], rect: tuple[float, float, float, float], tol: float = 8.0) -> bool:
    cx = (rect[0] + rect[2]) / 2
    cy = (rect[1] + rect[3]) / 2
    return (
        bbox["x0"] - tol <= cx <= bbox["x1"] + tol and bbox["y0"] - tol <= cy <= bbox["y1"] + tol
    )


def probe_job(data_dir: Path, job_id: str, source: str = "review") -> dict[str, Any]:
    """source='review' probes review items; 'normalized' probes every extracted cell (works for
    not_found jobs, which have no review items)."""
    raw = json.loads((data_dir / "results" / f"{job_id}_{source}.json").read_text(encoding="utf-8"))
    items = [
        {**it, "id": it.get("id", f"cell-{n}")} for n, it in enumerate(raw if isinstance(raw, list) else raw.get("items", []))
    ]
    doc = pymupdf.open(str(data_dir / "uploads" / f"{job_id}.pdf"))
    hits = misses = not_found = 0
    examples: list[dict[str, Any]] = []
    expected: dict[str, list[float]] = {}
    for item in items:
        page = doc[item["page"] - 1]
        locs = value_locations(page, item["value"])
        if not locs:
            not_found += 1
            continue
        bbox = item["bbox"]
        match = next((r for r in locs if contains_center(bbox, r)), None)
        if match is not None:
            hits += 1
            expected[item["id"]] = [round(v, 2) for v in match]
        else:
            misses += 1
            expected[item["id"]] = [round(v, 2) for v in locs[0]]
            if len(examples) < 5:
                examples.append(
                    {
                        "label": item["label"][:50],
                        "value": item["value"],
                        "bbox": [round(bbox[k]) for k in ("x0", "y0", "x1", "y1")],
                        "text_at": [round(v) for v in locs[0]],
                    }
                )
    doc.close()
    return {
        "job_id": job_id,
        "hit": hits,
        "miss": misses,
        "value_not_found_on_page": not_found,
        "hit_rate": round(hits / (hits + misses), 4) if hits + misses else None,
        "miss_examples": examples,
        "expected_value_rects": expected,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, required=True)
    ap.add_argument("--job", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--source", choices=["review", "normalized"], default="review")
    args = ap.parse_args()
    results_dir = args.data_dir / "results"
    jobs = [args.job] if args.job else sorted(
        p.name.removesuffix(f"_{args.source}.json") for p in results_dir.glob(f"*_{args.source}.json")
    )
    out = [probe_job(args.data_dir, j, args.source) for j in jobs]
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        for r in out:
            print(f"{r['job_id'][:8]} hit={r['hit']} miss={r['miss']} not_found={r['value_not_found_on_page']} rate={r['hit_rate']}")
            for ex in r["miss_examples"]:
                print("   MISS", ex)
    return 0 if all(r["miss"] == 0 for r in out) else 1


if __name__ == "__main__":
    sys.exit(main())
