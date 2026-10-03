#!/usr/bin/env python
"""
Audit mutation experiments M1-M10, re-created as a committed tool (FIX checkpoint).

Each mutation breaks one critical behaviour with an exact string replacement, runs the tests
that should notice, then restores the file with `git checkout`. Requires a clean tracked tree
for the mutated files. Results: KILLED (tests failed) or SURVIVED (all passed).

Usage (venv interpreter):
    .venv/Scripts/python.exe tools/verify/mutations.py            # all, unit/component tests only
    .venv/Scripts/python.exe tools/verify/mutations.py M5 M6 --e2e   # also run the Playwright smoke
    .venv/Scripts/python.exe tools/verify/mutations.py --json
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = str(Path(sys.executable))
NPX = "npx.cmd" if os.name == "nt" else "npx"


def pytest(*paths: str) -> list[str]:
    return [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", *paths]


VITEST = [NPX, "vitest", "run"]
E2E_SMOKE = [NPX, "playwright", "test", "e2e/review-smoke.spec.ts"]

MUTATIONS: list[dict[str, object]] = [
    {
        "id": "M1",
        "desc": "Auto-accept threshold 0.95 -> 0.85",
        "file": "backend/app/extraction/confidence.py",
        "old": "    if score >= 0.95:\n        return ConfidenceBand.auto_accepted",
        "new": "    if score >= 0.85:\n        return ConfidenceBand.auto_accepted",
        "runs": [("backend", pytest("tests/extraction/test_confidence.py", "tests/extraction/test_flagger.py"))],
    },
    {
        "id": "M2",
        "desc": "needs_review band items silently LOCKED in review status derivation",
        "file": "backend/app/review/repository.py",
        "old": "            elif sr.confidence_band == ConfidenceBand.needs_review:\n                status = ReviewStatus.needs_review\n            else:\n                status = ReviewStatus.manual_required\n\n            taxonomy_status_val",
        "new": "            elif sr.confidence_band == ConfidenceBand.needs_review:\n                status = ReviewStatus.locked\n            else:\n                status = ReviewStatus.manual_required\n\n            taxonomy_status_val",
        "runs": [("backend", pytest("tests/review", "tests/test_job_runner.py", "tests/extraction/test_job_runner_integration.py"))],
    },
    {
        "id": "M3",
        # Redefined after AUD-002: the audit form (remove the inversion) was the fix itself, so the
        # mutation now re-introduces the defect: invert every Docling box regardless of origin.
        "desc": "Docling bbox Y: invert every Docling box regardless of coord_origin (AUD-002 defect)",
        "file": "backend/app/extraction/coordinate_normalizer.py",
        "old": '    if item.coord_origin == "BOTTOMLEFT":',
        "new": '    if item.parser_used == "docling" or item.coord_origin == "BOTTOMLEFT":',
        "runs": [("backend", pytest("tests/extraction/test_coordinate_normalizer.py", "tests/extraction/test_docling_golden_bbox.py"))],
    },
    {
        "id": "M4",
        "desc": "Workbook header always VERIFIED",
        "file": "backend/app/excel_export/generator.py",
        "old": "        if unverified_count > 0:\n            ws_recon.write(\n                0, 1, f\"DRAFT: {unverified_count} items unverified\", fmt_draft_status\n            )",
        "new": "        if False:\n            ws_recon.write(\n                0, 1, f\"DRAFT: {unverified_count} items unverified\", fmt_draft_status\n            )",
        "runs": [("backend", pytest("tests/excel_export"))],
    },
    {
        "id": "M5",
        "desc": "Review PDF page never drawn",
        "file": "frontend/src/components/review/ReviewPage.tsx",
        "old": "      .render(pdfDoc, targetPage, canvas, renderScale)",
        "new": "      .constructor && Promise.resolve('rendered' as const)",
        "runs": [("frontend", VITEST)],
        "e2e": True,
    },
    {
        "id": "M6",
        "desc": "Review highlight vertically mirrored",
        "file": "frontend/src/components/review/ReviewPage.tsx",
        "old": "                      const pixelBox = normalizeBboxToPixels(\n                        selectedItem.bbox,",
        "new": "                      const pixelBox = normalizeBboxToPixels(\n                        { ...selectedItem.bbox, y0: 1000 - selectedItem.bbox.y1, y1: 1000 - selectedItem.bbox.y0 },",
        "runs": [("frontend", VITEST)],
        "e2e": True,
    },
    {
        "id": "M7",
        "desc": "Auto workbook path receives no inputs",
        "file": "backend/app/job_runner.py",
        "old": "        formula_inputs = read_formula_inputs(classified_records)",
        "new": "        formula_inputs = read_formula_inputs([])",
        "runs": [("backend", pytest("tests/test_job_runner.py", "tests/extraction/test_job_runner_integration.py", "tests/excel_export"))],
    },
    {
        "id": "M8",
        "desc": "Checks sheet footing status hard-coded PASS",
        "file": "backend/app/excel_export/generator.py",
        "old": "ws_checks.write_formula(3, 5, '=IF(E4<=1.0, \"PASS\", \"FAIL\")', fmt_text)",
        "new": "ws_checks.write_formula(3, 5, '=IF(TRUE, \"PASS\", \"FAIL\")', fmt_text)",
        "runs": [("backend", pytest("tests/excel_export", "tests/formula_engine"))],
    },
    {
        "id": "M9",
        "desc": "EDGAR token bucket capacity 10 -> 1000",
        "file": "backend/app/ingestion/edgar/rate_limiter.py",
        "old": "    def __init__(self, rate: float = 10.0, capacity: float = 10.0) -> None:",
        "new": "    def __init__(self, rate: float = 10.0, capacity: float = 1000.0) -> None:",
        "runs": [("backend", pytest("tests/ingestion"))],
    },
    {
        "id": "M10",
        "desc": "QoE value parser returns 0.0 for every value",
        "file": "backend/app/drift/qoe_diff.py",
        "old": "            val = float(val_clean) if val_clean else 0.0",
        "new": "            val = 0.0",
        "runs": [("backend", pytest("tests/drift"))],
    },
]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def run_one(m: dict[str, object], with_e2e: bool) -> dict[str, object]:
    rel = str(m["file"])
    if git("status", "--porcelain", "--", rel).strip():
        return {"id": m["id"], "result": "SKIPPED", "reason": f"{rel} has uncommitted changes"}
    path = ROOT / rel
    src = path.read_text(encoding="utf-8")
    old, new = str(m["old"]), str(m["new"])
    if "\r\n" in src:
        old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    count = src.count(old)
    if count != 1:
        return {"id": m["id"], "result": "NOT-APPLICABLE", "reason": f"anchor found {count} times (code changed)"}
    path.write_text(src.replace(old, new, 1), encoding="utf-8", newline="")
    runs = list(m["runs"])  # type: ignore[call-overload]
    if with_e2e and m.get("e2e"):
        runs.append(("frontend", E2E_SMOKE))
    tails: list[str] = []
    killed_by = None
    try:
        for cwd, cmd in runs:
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
            proc = subprocess.run(cmd, cwd=ROOT / cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=2400, check=False)
            lines = [ln for ln in (proc.stdout + proc.stderr).splitlines() if ln.strip()]
            tails.append(f"{' '.join(cmd[-2:])}: " + " | ".join(lines[-2:]))
            if proc.returncode != 0:
                killed_by = " ".join(cmd[-2:])
                break
    finally:
        git("checkout", "--", rel)
    return {
        "id": m["id"],
        "desc": m["desc"],
        "file": rel,
        "result": "KILLED" if killed_by else "SURVIVED",
        "killed_by": killed_by,
        "tail": tails,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--e2e", action="store_true", help="also run the Playwright smoke for UI mutations")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    selected = [m for m in MUTATIONS if not args.ids or m["id"] in args.ids]
    results = [run_one(m, args.e2e) for m in selected]
    dirty = git("status", "--porcelain", "--untracked-files=no")
    if args.json:
        print(json.dumps({"results": results, "tracked_changes_after": dirty}, indent=2))
    else:
        for r in results:
            print(f"{r['id']:<4} {r['result']:<15} {r.get('desc', r.get('reason', ''))}")
            if r.get("killed_by"):
                print(f"      killed by: {r['killed_by']}")
        print("tracked changes after run:", dirty.strip() or "(none)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
