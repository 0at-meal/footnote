"""
Tests for the P0-04 gold-label schema and validator. Every identifier and number
here is a synthetic fixture (zero CIK, example values); none describe a filing.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from tools.gold.labels import GoldRelease, validate_dir

SHA = "a" * 64
ACC = "0000000000-26-000001"
URL = "https://www.sec.gov/Archives/edgar/data/1/000000000026000001/ex991.htm"


def _value(period: str, raw: str, value: str | None) -> dict[str, Any]:
    return {
        "period_id": period,
        "value_raw": raw,
        "value": value,
        "verified_by": "tieout",
        "labeler": "extractor",
        "labeled_on": "2026-10-14",
    }


def release_dict() -> dict[str, Any]:
    # Synthetic bridge that ties out: 50 + 40 + 60 + 50 = 200.
    return {
        "schema_version": 1,
        "ticker": "FIXT",
        "cik": "0000000001",
        "accession": ACC,
        "exhibit": "ex991.htm",
        "source_url": URL,
        "sha256": SHA,
        "metric_label_raw": "Adjusted EBITDA",
        "scale": "millions",
        "scale_quote": "(in millions)",
        "table": {"table_index": 3, "caption_raw": None},
        "periods": [
            {
                "period_id": "3M-2026-06-30",
                "label_raw": "Three Months Ended June 30, 2026",
                "end_date": "2026-06-30",
                "months": 3,
            }
        ],
        "lines": [
            {
                "row_order": 0,
                "label_raw": "Net income (loss)",
                "role": "gaap_start",
                "sign": 1,
                "values": [_value("3M-2026-06-30", "50", "50")],
            },
            {
                "row_order": 1,
                "label_raw": "Interest expense, net",
                "role": "adjustment",
                "sign": 1,
                "values": [_value("3M-2026-06-30", "40", "40")],
            },
            {
                "row_order": 2,
                "label_raw": "Depreciation and amortization",
                "role": "adjustment",
                "sign": 1,
                "values": [_value("3M-2026-06-30", "60", "60")],
            },
            {
                "row_order": 3,
                "label_raw": "Restructuring",
                "role": "adjustment",
                "sign": 1,
                "values": [_value("3M-2026-06-30", "50", "50")],
            },
            {
                "row_order": 4,
                "label_raw": "Adjusted EBITDA",
                "role": "total",
                "sign": 1,
                "values": [_value("3M-2026-06-30", "$ 200", "200")],
            },
        ],
    }


def test_valid_release_parses() -> None:
    rel = GoldRelease.model_validate(release_dict())
    assert len(rel.all_values()) == 5


def test_parentheses_value_must_be_negative() -> None:
    d = release_dict()
    d["lines"][3]["values"][0] = _value("3M-2026-06-30", "(45)", "45")
    with pytest.raises(ValidationError, match="does not match value_raw"):
        GoldRelease.model_validate(d)
    d["lines"][3]["values"][0] = _value("3M-2026-06-30", "(45)", "-45")
    GoldRelease.model_validate(d)


def test_dash_must_be_null_and_null_must_be_dash() -> None:
    d = release_dict()
    d["lines"][3]["values"][0] = _value("3M-2026-06-30", "—", "0")
    with pytest.raises(ValidationError, match="must have value null"):
        GoldRelease.model_validate(d)
    d["lines"][3]["values"][0] = _value("3M-2026-06-30", "12", None)
    with pytest.raises(ValidationError, match="is not a dash"):
        GoldRelease.model_validate(d)


def test_requires_one_start_and_one_total() -> None:
    d = release_dict()
    d["lines"][4]["role"] = "adjustment"
    with pytest.raises(ValidationError, match="exactly one gaap_start"):
        GoldRelease.model_validate(d)


def test_every_line_has_every_period() -> None:
    d = release_dict()
    d["periods"].append(
        {
            "period_id": "6M-2026-06-30",
            "label_raw": "Six Months Ended June 30, 2026",
            "end_date": "2026-06-30",
            "months": 6,
        }
    )
    with pytest.raises(ValidationError, match="one value per period"):
        GoldRelease.model_validate(d)


def test_source_url_must_be_this_filing() -> None:
    d = release_dict()
    d["source_url"] = URL.replace("/data/1/", "/data/2/")
    with pytest.raises(ValidationError, match="source_url"):
        GoldRelease.model_validate(d)


def test_unknown_fields_and_bad_verified_by_rejected() -> None:
    d = release_dict()
    d["extra"] = 1
    with pytest.raises(ValidationError):
        GoldRelease.model_validate(d)
    d = release_dict()
    d["lines"][0]["values"][0]["verified_by"] = "llm"
    with pytest.raises(ValidationError):
        GoldRelease.model_validate(d)


def _manifest() -> dict[str, Any]:
    return {
        "releases": [
            {
                "ticker": "FIXT",
                "cik": "0000000001",
                "accession": ACC,
                "exhibit": "ex991.htm",
                "url": URL,
                "sha256": SHA,
            },
            {
                "ticker": "FIXT",
                "cik": "0000000001",
                "accession": "0000000000-26-000002",
                "exhibit": "ex991.htm",
                "url": URL,
                "sha256": SHA,
            },
        ]
    }


def test_validate_dir_against_manifest(tmp_path: Path) -> None:
    (tmp_path / f"{ACC}.json").write_text(json.dumps(release_dict()), encoding="utf-8")
    assert validate_dir(tmp_path, _manifest()) == []

    strict = validate_dir(tmp_path, _manifest(), strict=True)
    assert any("not confirmed" in p for p in strict)
    assert any("0000000000-26-000002: no label file" in p for p in strict)


def test_validate_dir_catches_hash_drift(tmp_path: Path) -> None:
    d = copy.deepcopy(release_dict())
    d["sha256"] = "b" * 64
    (tmp_path / f"{ACC}.json").write_text(json.dumps(d), encoding="utf-8")
    assert validate_dir(tmp_path, _manifest()) == [
        "0000000000-26-000001.json: sha256 differs from manifest"
    ]
