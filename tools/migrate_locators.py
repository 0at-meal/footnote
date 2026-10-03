#!/usr/bin/env python
"""
One-shot FN-023 locator migration (AUD-037).

Jobs created before FN-023 store records with only the legacy fields page / bbox / source_file.
They load (the models derive a PdfLocator), but the stored files never carry the locator. This
adds `"locator": {"type": "pdf", ...}` to every such record in a data directory.

- Dry run by default: reports what would change and writes nothing.
- `--apply` writes a backup of each changed file next to it (`*.pre-locator-migration.json`),
  rewrites the file, then reloads every job through the app models and checks that review item
  IDs and locators are unchanged (IDs are never edited).
- Records with incomplete legacy fields are reported and left untouched.

Usage (venv interpreter):
    .venv/Scripts/python.exe tools/migrate_locators.py --data-dir <dir>            # dry run
    .venv/Scripts/python.exe tools/migrate_locators.py --data-dir <dir> --apply
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RECORD_FILES = ("_records.json", "_scored.json", "_classified.json", "_review.json")
BACKUP_SUFFIX = ".pre-locator-migration.json"


def _is_legacy_record(obj: dict[str, Any]) -> bool:
    return "value" in obj and "label" in obj and "page" in obj and obj.get("locator") is None


def _migrate(obj: Any, stats: dict[str, int]) -> Any:
    if isinstance(obj, list):
        return [_migrate(v, stats) for v in obj]
    if not isinstance(obj, dict):
        return obj
    if _is_legacy_record(obj):
        from app.extraction.locator import PdfLocator

        if obj.get("bbox") is None or not obj.get("source_file") or not isinstance(obj.get("page"), int) or obj["page"] < 1:
            stats["incomplete"] += 1
            return obj
        locator = PdfLocator(page=obj["page"], bbox=obj["bbox"], source_file=obj["source_file"])
        stats["migrated"] += 1
        return {**obj, "locator": locator.model_dump()}
    return {k: _migrate(v, stats) for k, v in obj.items()}


def _snapshot(data_dir: Path) -> dict[str, list[tuple[str, str]]]:
    """Review item IDs and canonical locator keys per job, loaded through the app models."""
    from app.extraction.locator import canonical_locator_key
    from app.ingestion.repository import JobRepository
    from app.review.repository import ReviewRepository

    snap: dict[str, list[tuple[str, str]]] = {}
    for job in JobRepository(data_dir=data_dir).list_jobs():
        items = ReviewRepository(data_dir=data_dir).get_review_items(job.job_id) or []
        snap[job.job_id] = [(i.id, canonical_locator_key(i.locator)) for i in items]
    return snap


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, required=True)
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = ap.parse_args()

    data_dir = args.data_dir.resolve()
    os.environ["FOOTNOTE_DATA_DIR"] = str(data_dir)
    sys.path.insert(0, str(ROOT / "backend"))

    results = data_dir / "results"
    files = sorted(f for f in results.glob("*.json") if f.name.endswith(RECORD_FILES))
    before = _snapshot(data_dir) if args.apply else None
    total = {"migrated": 0, "incomplete": 0, "files_changed": 0}
    for f in files:
        stats = {"migrated": 0, "incomplete": 0}
        migrated = _migrate(json.loads(f.read_text(encoding="utf-8")), stats)
        total["migrated"] += stats["migrated"]
        total["incomplete"] += stats["incomplete"]
        if stats["migrated"] or stats["incomplete"]:
            print(f"{f.name}: add locator to {stats['migrated']} record(s), {stats['incomplete']} incomplete (left unchanged)")
        if stats["migrated"] and args.apply:
            shutil.copy2(f, f.with_name(f.name.removesuffix(".json") + BACKUP_SUFFIX))
            tmp = f.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(migrated, indent=2), encoding="utf-8")
            tmp.replace(f)
            total["files_changed"] += 1

    mode = "APPLIED" if args.apply else "DRY RUN (nothing written)"
    print(f"{mode}: {total['migrated']} record(s) in {len(files)} file(s); {total['incomplete']} incomplete; {total['files_changed']} file(s) rewritten")
    if args.apply:
        after = _snapshot(data_dir)
        if after != before:
            print("VERIFY FAILED: review IDs or locators changed after migration; restore the backups.")
            return 1
        print(f"VERIFY OK: {sum(len(v) for v in after.values())} review item(s) in {len(after)} job(s) have the same IDs and locators")
    return 0


if __name__ == "__main__":
    sys.exit(main())
