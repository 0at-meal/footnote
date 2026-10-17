"""
Tests for promoting drafts to gold labels (P0-06). All releases here are
synthetic fixtures (CIK 1); none describe a real filing.
"""

import copy
from typing import Any

import pytest
from tools.gold.labels import VerifiedBy
from tools.gold.promote import PromotionError, promote

ACC = "0000000000-26-000001"
P1, P2 = "3M-2026-06-30", "3M-2025-06-30"


def _value(period: str, raw: str, value: str | None) -> dict[str, Any]:
    return {
        "period_id": period,
        "value_raw": raw,
        "value": value,
        "verified_by": "tieout",
        "labeler": "extractor (tools.gold.draft)",
        "labeled_on": "2026-10-14",
    }


def _line(order: int, label: str, role: str, v1: str, v2: str) -> dict[str, Any]:
    def num(raw: str) -> str | None:
        return None if raw == "—" else raw

    return {
        "row_order": order,
        "label_raw": label,
        "role": role,
        "sign": 1,
        "values": [_value(P1, v1, num(v1)), _value(P2, v2, num(v2))],
    }


DRAFT: dict[str, Any] = {
    "release": {
        "schema_version": 1,
        "ticker": "FIXT",
        "cik": "0000000001",
        "accession": ACC,
        "exhibit": "fixture.htm",
        "source_url": "https://www.sec.gov/Archives/edgar/data/1/000000000026000001/fixture.htm",
        "sha256": "0" * 64,
        "metric_label_raw": "Adjusted EBITDA",
        "scale": "millions",
        "scale_quote": "(in millions)",
        "table": {"table_index": 3, "caption_raw": None},
        "periods": [
            {
                "period_id": P1,
                "label_raw": "Three Months Ended June 30, 2026",
                "end_date": "2026-06-30",
                "months": 3,
            },
            {
                "period_id": P2,
                "label_raw": "Three Months Ended June 30, 2025",
                "end_date": "2025-06-30",
                "months": 3,
            },
        ],
        "lines": [
            _line(0, "Net income", "gaap_start", "50", "40"),
            _line(1, "Interest expense", "adjustment", "30", "30"),
            _line(
                2,
                "Net income attributable to noncontrolling interests",
                "adjustment",
                "—",
                "—",
            ),
            _line(3, "Adjusted EBITDA", "total", "80", "70"),
        ],
    },
    "exceptions": [],
    "notes": [],
}

READING: dict[str, Any] = {
    "scale": "millions",
    "metric_label_raw": "Adjusted EBITDA",
    "periods": [{"period_id": P1}, {"period_id": P2}],
    "lines": [
        {
            "label_raw": "Net income",
            "role": "gaap_start",
            "sign": 1,
            "values": ["50", "40"],
        },
        {
            "label_raw": "Interest expense",
            "role": "adjustment",
            "sign": 1,
            "values": ["30", "30"],
        },
        {
            "label_raw": "Net income attributable to noncontrolling interests",
            "role": "adjustment",
            "sign": 1,
            "values": ["—", "—"],
        },
        {
            "label_raw": "Adjusted EBITDA",
            "role": "total",
            "sign": 1,
            "values": ["80", "70"],
        },
    ],
}

DECISIONS: dict[str, Any] = {
    "reviewer": "Fixture Reviewer",
    "reviewed_on": "2026-10-17",
    "tables_confirmed": {ACC: 3},
    "resolutions": [],
}


def _by_label(gold: Any) -> dict[str, Any]:
    return {line.label_raw: line for line in gold.lines}


def test_clean_release_is_model_agreement_with_confirmed_table() -> None:
    gold = promote(DRAFT, READING, DECISIONS)
    assert {v.verified_by for v in gold.all_values()} == {VerifiedBy.model_agreement}
    assert gold.table.confirmed_by == "Fixture Reviewer"
    assert str(gold.table.confirmed_on) == "2026-10-17"


def test_anchor_resolution_makes_start_human_and_rest_model_agreement() -> None:
    draft = copy.deepcopy(DRAFT)
    item = "GAAP anchor unavailable for 3M-2026-06-30: 'Net income' = 50 vs XBRL n/a"
    draft["exceptions"] = [item]
    for line in draft["release"]["lines"]:
        line["values"][0]["verified_by"] = None  # held back by the failed anchor
    decisions = copy.deepcopy(DECISIONS)
    decisions["resolutions"] = [
        {
            "accession": ACC,
            "item": f"draft exception: {item}",
            "periods": [P1],
            "decision": "ok",
        }
    ]
    lines = _by_label(promote(draft, READING, decisions))
    start = lines["Net income"].values[0]
    assert start.verified_by is VerifiedBy.human and start.labeler == "Fixture Reviewer"
    assert lines["Interest expense"].values[0].verified_by is VerifiedBy.model_agreement


def test_line_resolution_sets_sign_and_human() -> None:
    reading = copy.deepcopy(READING)
    reading["lines"][2]["sign"] = -1
    label = "Net income attributable to noncontrolling interests"
    decisions = copy.deepcopy(DECISIONS)
    decisions["resolutions"] = [
        {
            "accession": ACC,
            "item": f"disagreement: sign of {label!r}: draft 1 vs reading -1",
            "line": label,
            "sign": -1,
            "decision": "deducted",
        }
    ]
    nci = _by_label(promote(DRAFT, reading, decisions))[label]
    assert nci.sign == -1
    assert {v.verified_by for v in nci.values} == {VerifiedBy.human}


def test_unresolved_item_blocks_promotion() -> None:
    reading = copy.deepcopy(READING)
    reading["lines"][2]["sign"] = -1
    with pytest.raises(PromotionError, match="exactly one resolution"):
        promote(DRAFT, reading, DECISIONS)


def test_resolution_without_item_blocks_promotion() -> None:
    decisions = copy.deepcopy(DECISIONS)
    decisions["resolutions"] = [
        {"accession": ACC, "item": "stale item", "decision": "x"}
    ]
    with pytest.raises(PromotionError, match="matches no queue item"):
        promote(DRAFT, READING, decisions)


def test_table_must_be_confirmed_at_drafted_index() -> None:
    decisions = copy.deepcopy(DECISIONS)
    decisions["tables_confirmed"] = {ACC: 4}
    with pytest.raises(PromotionError, match="not confirmed"):
        promote(DRAFT, READING, decisions)


def test_unverified_value_blocks_promotion() -> None:
    draft = copy.deepcopy(DRAFT)
    draft["release"]["lines"][1]["values"][0]["verified_by"] = None
    with pytest.raises(PromotionError, match="unverified value"):
        promote(draft, READING, DECISIONS)
