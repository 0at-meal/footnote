"""
P0-04: gold-label schema and validator.

One JSON file per release lives in ``eval/gold/labels/<accession>.json``. A *label*
is one value in the bridge (one line x one period) and carries its own provenance:
``verified_by``, ``labeler`` and ``labeled_on``. The release carries the
CIK-qualified sec.gov URL and the sha256 of the saved exhibit (P0-03 manifest).

Value and sign conventions (used by tie-outs):

- ``value_raw`` is the text exactly as shown in the cell, e.g. ``"(1,234)"``.
- ``value`` is that number as presented, in the table's reported scale, with
  accounting parentheses or a leading minus making it negative. A dash
  placeholder (``"—"``, ``"-"``) is ``null``.
- ``sign`` is the line's direction in the bridge: ``+1`` if added toward the
  total, ``-1`` if subtracted (e.g. ``"Less: gain on sale"`` shown as ``50``).
- A line's contribution is ``sign * value``. Summing the contributions of the
  ``gaap_start`` line and all ``adjustment`` lines should give the ``total`` line.

Usage (from ``backend/``)::

    python -m tools.gold.labels --validate            # schema + manifest checks
    python -m tools.gold.labels --validate --strict   # + Phase 0 gate checks
    python -m tools.gold.labels --write-schema        # eval/gold/labels/schema.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import yaml
from app.extraction.bridge.models import LineRole
from app.extraction.locator import is_sec_archives_url
from app.extraction.scale_and_sign import parse_raw_numeric
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

GOLD_DIR = Path(__file__).resolve().parents[3] / "eval" / "gold"
LABELS_DIR = GOLD_DIR / "labels"
MANIFEST = GOLD_DIR / "raw" / "manifest.yaml"
SCHEMA_FILE = LABELS_DIR / "schema.json"

_ACCESSION = re.compile(r"^\d{10}-\d{2}-\d{6}$")
_CIK = re.compile(r"^\d{10}$")
_DASHES = {"—", "–", "-", "--"}


class VerifiedBy(str, Enum):
    """How a label's value was established (P0-05 / P0-05b / P0-06)."""

    tieout = "tieout"  # extractor value; both arithmetic checks pass
    model_agreement = "model_agreement"  # independent model reading agrees
    human = "human"  # checked or resolved by a person against sec.gov


class Scale(str, Enum):
    units = "units"
    thousands = "thousands"
    millions = "millions"
    billions = "billions"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Period(_Strict):
    period_id: str = Field(..., min_length=1, description="e.g. '3M-2026-06-30'")
    label_raw: str = Field(..., min_length=1, description="column header as shown")
    end_date: date
    months: Literal[3, 6, 9, 12]


class GoldValue(_Strict):
    period_id: str
    value_raw: str = Field(..., min_length=1)
    value: Decimal | None
    verified_by: VerifiedBy
    labeler: str = Field(..., min_length=1)
    labeled_on: date

    @model_validator(mode="after")
    def _raw_matches_value(self) -> GoldValue:
        raw = self.value_raw.strip()
        if raw in _DASHES:
            if self.value is not None:
                raise ValueError(f"dash placeholder {raw!r} must have value null")
            return self
        if self.value is None:
            raise ValueError(f"value is null but value_raw {raw!r} is not a dash")
        parsed = parse_raw_numeric(raw)
        if parsed is None or Decimal(str(parsed)) != self.value:
            raise ValueError(f"value {self.value} does not match value_raw {raw!r}")
        return self


class GoldLine(_Strict):
    row_order: int = Field(..., ge=0)
    label_raw: str = Field(..., min_length=1)
    role: LineRole
    sign: Literal[1, -1]
    values: list[GoldValue] = Field(..., min_length=1)


class TableSelection(_Strict):
    table_index: int = Field(..., ge=0)
    caption_raw: str | None = None
    confirmed_by: str | None = None  # P0-06: the owner confirms the table
    confirmed_on: date | None = None


class GoldRelease(_Strict):
    schema_version: Literal[1] = 1
    ticker: str = Field(..., min_length=1)
    cik: str
    accession: str
    exhibit: str = Field(..., min_length=1)
    source_url: str
    sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    metric_label_raw: str = Field(..., min_length=1)
    scale: Scale
    scale_quote: str = Field(..., min_length=1, description="caption text giving scale")
    table: TableSelection
    periods: list[Period] = Field(..., min_length=1)
    lines: list[GoldLine] = Field(..., min_length=2)

    @model_validator(mode="after")
    def _consistent(self) -> GoldRelease:
        if not _CIK.match(self.cik):
            raise ValueError(f"cik must be 10 digits: {self.cik!r}")
        if not _ACCESSION.match(self.accession):
            raise ValueError(f"bad accession: {self.accession!r}")
        acc = self.accession.replace("-", "")
        if not (
            is_sec_archives_url(self.source_url)
            and f"/data/{int(self.cik)}/{acc}/" in self.source_url
            and self.source_url.endswith("/" + self.exhibit)
        ):
            raise ValueError(
                f"source_url is not this filing's sec.gov URL: {self.source_url}"
            )

        period_ids = [p.period_id for p in self.periods]
        if len(set(period_ids)) != len(period_ids):
            raise ValueError("duplicate period_id")
        rows = [ln.row_order for ln in self.lines]
        if len(set(rows)) != len(rows):
            raise ValueError("duplicate row_order")

        for line in self.lines:
            got = sorted(v.period_id for v in line.values)
            if got != sorted(period_ids):
                raise ValueError(
                    f"line {line.label_raw!r} must have exactly one value per period"
                )

        starts = [ln for ln in self.lines if ln.role is LineRole.gaap_start]
        totals = [ln for ln in self.lines if ln.role is LineRole.total]
        if len(starts) != 1 or len(totals) != 1:
            raise ValueError("need exactly one gaap_start line and one total line")
        if starts[0].row_order >= totals[0].row_order:
            raise ValueError("gaap_start must come before total")
        return self

    def all_values(self) -> list[GoldValue]:
        return [v for line in self.lines for v in line.values]


def load_release(path: Path) -> GoldRelease:
    return GoldRelease.model_validate_json(path.read_text(encoding="utf-8"))


def validate_dir(
    labels_dir: Path, manifest: dict[str, Any], strict: bool = False
) -> list[str]:
    """
    Problems across all label files; an empty list means valid.

    Always: schema rules, one file per manifest release at most, sha256 / URL /
    exhibit agree with the manifest. With ``strict`` (Phase 0 exit gate): every
    manifest release has a label file and every table selection is confirmed.
    """
    by_acc = {e["accession"]: e for e in manifest["releases"]}
    problems: list[str] = []
    seen: set[str] = set()
    for path in sorted(labels_dir.glob("*.json")):
        if path.name == SCHEMA_FILE.name:
            continue
        try:
            rel = load_release(path)
        except ValidationError as exc:
            problems.append(f"{path.name}: {exc.error_count()} schema error(s): {exc}")
            continue
        if path.stem != rel.accession:
            problems.append(f"{path.name}: file name must be the accession")
        entry = by_acc.get(rel.accession)
        if entry is None:
            problems.append(f"{path.name}: accession not in the P0-03 manifest")
            continue
        seen.add(rel.accession)
        for field_name, label_value in (
            ("sha256", rel.sha256),
            ("exhibit", rel.exhibit),
            ("cik", rel.cik),
            ("ticker", rel.ticker),
        ):
            if label_value != entry[field_name]:
                problems.append(f"{path.name}: {field_name} differs from manifest")
        if rel.source_url != entry["url"]:
            problems.append(f"{path.name}: source_url differs from manifest url")
        if strict and not (rel.table.confirmed_by and rel.table.confirmed_on):
            problems.append(f"{path.name}: table selection not confirmed (P0-06)")
    if strict:
        for acc in sorted(set(by_acc) - seen):
            problems.append(f"{acc}: no label file")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--validate", action="store_true")
    group.add_argument("--write-schema", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Phase 0 gate checks")
    args = parser.parse_args()

    if args.write_schema:
        LABELS_DIR.mkdir(parents=True, exist_ok=True)
        SCHEMA_FILE.write_text(
            json.dumps(GoldRelease.model_json_schema(), indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {SCHEMA_FILE}")
        return 0

    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    problems = validate_dir(LABELS_DIR, manifest, strict=args.strict)
    for p in problems:
        print(p)
    n = len([p for p in LABELS_DIR.glob("*.json") if p.name != SCHEMA_FILE.name])
    print(f"{n} label files checked, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
