"""
P0-06: promote drafts to gold labels using the owner's recorded review.

Inputs: ``eval/gold/drafts`` (P0-05), ``eval/gold/model_reading`` (P0-05b, via
``tools.gold.compare``) and ``eval/gold/review_decisions.yaml`` (P0-06). Output:
``eval/gold/labels/<accession>.json``, validated against the P0-04 schema.

``verified_by`` per value:

- ``human``: a resolution covers it. A ``line`` resolution covers that line's
  values (and may set its ``sign``); a ``periods`` resolution settles the GAAP
  anchor for those periods, so it covers the ``gaap_start`` value there.
- ``model_agreement``: the independent reading agrees and both P0-05 checks pass,
  or they pass once a ``periods`` resolution settles the anchor.

Nothing is promoted unless every table is confirmed at the drafted index, every
review-queue item has exactly one resolution, and every value is verified by
one of the rules above.

Usage (from ``backend/``)::

    python -m tools.gold.promote
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from tools.gold.compare import GOLD_DIR, compare, load_decisions, queue_items
from tools.gold.labels import LABELS_DIR, GoldRelease


class PromotionError(Exception):
    """A draft cannot become a gold label without further review."""


def promote(
    draft: dict[str, Any], reading: dict[str, Any], decisions: dict[str, Any]
) -> GoldRelease:
    rel = deepcopy(draft["release"])
    acc = rel["accession"]
    reviewer, reviewed_on = decisions["reviewer"], str(decisions["reviewed_on"])

    confirmed = {str(k): int(v) for k, v in decisions["tables_confirmed"].items()}
    if confirmed.get(acc) != rel["table"]["table_index"]:
        raise PromotionError(
            f"{acc}: table {rel['table']['table_index']} not confirmed"
        )

    result = compare(draft, reading)
    items = queue_items(draft, result)
    resolutions = [r for r in decisions["resolutions"] if str(r["accession"]) == acc]
    for item in items:
        if sum(r["item"] == item for r in resolutions) != 1:
            raise PromotionError(f"{acc}: item needs exactly one resolution: {item}")
    for r in resolutions:
        if r["item"] not in items:
            raise PromotionError(
                f"{acc}: resolution matches no queue item: {r['item']}"
            )

    anchor_periods = {p for r in resolutions for p in r.get("periods", [])}
    resolved_lines = {r["line"]: r for r in resolutions if "line" in r}
    agrees = {(v["label_raw"], v["period_id"]): v for v in result.values}

    for line in rel["lines"]:
        override = resolved_lines.pop(line["label_raw"], None)
        if override is not None and "sign" in override:
            line["sign"] = int(override["sign"])
        for value in line["values"]:
            key = (line["label_raw"], value["period_id"])
            cmp = agrees[key]
            if override is not None or (
                line["role"] == "gaap_start" and value["period_id"] in anchor_periods
            ):
                value.update(
                    verified_by="human", labeler=reviewer, labeled_on=reviewed_on
                )
            elif cmp["proposed_verified_by"] == "model_agreement" or (
                value["period_id"] in anchor_periods and cmp["reader_agrees"]
            ):
                value["verified_by"] = "model_agreement"
            else:
                raise PromotionError(f"{acc}: unverified value {key}")
    if resolved_lines:
        raise PromotionError(
            f"{acc}: resolution lines not in table: {list(resolved_lines)}"
        )

    rel["table"].update(confirmed_by=reviewer, confirmed_on=reviewed_on)
    return GoldRelease.model_validate(rel)


def main() -> int:
    decisions = load_decisions()
    if decisions is None:
        print("no eval/gold/review_decisions.yaml: record the P0-06 review first")
        return 1
    released: list[tuple[Path, GoldRelease]] = []
    problems: list[str] = []
    for draft_path in sorted((GOLD_DIR / "drafts").glob("*.json")):
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        reading = json.loads(
            (GOLD_DIR / "model_reading" / draft_path.name).read_text(encoding="utf-8")
        )
        try:
            released.append(
                (LABELS_DIR / draft_path.name, promote(draft, reading, decisions))
            )
        except PromotionError as exc:
            problems.append(str(exc))
    if problems:
        print("\n".join(problems))
        print(f"{len(problems)} problem(s); no labels written")
        return 1
    counts: dict[str, int] = {}
    for path, gold in released:
        path.write_text(gold.model_dump_json(indent=2) + "\n", encoding="utf-8")
        for v in gold.all_values():
            counts[v.verified_by.value] = counts.get(v.verified_by.value, 0) + 1
    print(f"wrote {len(released)} label files; verified_by: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
