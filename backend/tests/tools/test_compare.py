"""
Tests for the P0-05b comparison of model readings with drafts. All releases here
are synthetic fixtures; none describe a real filing.
"""

import copy
from typing import Any

from tools.gold.compare import compare, norm_label


def _value(period: str, raw: str, verified: str | None = "tieout") -> dict[str, Any]:
    return {"period_id": period, "value_raw": raw, "verified_by": verified}


DRAFT: dict[str, Any] = {
    "release": {
        "accession": "0000000000-26-000001",
        "ticker": "FIXT",
        "scale": "millions",
        "metric_label_raw": "Adjusted EBITDA (a)",
        "periods": [{"period_id": "3M-2026-06-30"}, {"period_id": "3M-2025-06-30"}],
        "lines": [
            {
                "label_raw": "Net income",
                "role": "gaap_start",
                "sign": 1,
                "values": [
                    _value("3M-2026-06-30", "50"),
                    _value("3M-2025-06-30", "40"),
                ],
            },
            {
                "label_raw": "Interest expense (1)",
                "role": "adjustment",
                "sign": 1,
                "values": [
                    _value("3M-2026-06-30", "30"),
                    _value("3M-2025-06-30", "—", None),
                ],
            },
            {
                "label_raw": "Adjusted EBITDA (a)",
                "role": "total",
                "sign": 1,
                "values": [
                    _value("3M-2026-06-30", "80"),
                    _value("3M-2025-06-30", "40"),
                ],
            },
        ],
    },
    "exceptions": [],
}

READING: dict[str, Any] = {
    "scale": "millions",
    "metric_label_raw": "Adjusted EBITDA",
    "periods": [{"period_id": "3M-2026-06-30"}, {"period_id": "3M-2025-06-30"}],
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
            "values": ["30", "-"],
        },
        {
            "label_raw": "Adjusted EBITDA",
            "role": "total",
            "sign": 1,
            "values": ["80", "40"],
        },
    ],
}


def test_norm_label_ignores_footnotes_case_and_plus() -> None:
    assert norm_label("Plus: Net income (a), (b)") == "net income"
    assert norm_label("Other, net (3)") == "other, net"
    assert norm_label("Adjusted EBITDA (non-GAAP)") == "adjusted ebitda (non-gaap)"


def test_full_agreement_upgrades_only_tieout_values() -> None:
    result = compare(DRAFT, READING)
    assert result.disagreements == []
    proposed = [v["proposed_verified_by"] for v in result.values]
    # The dash value had no tie-out verification, so it is not upgraded.
    assert proposed.count("model_agreement") == 5
    assert proposed.count(None) == 1


def test_value_sign_role_and_line_disagreements() -> None:
    reading = copy.deepcopy(READING)
    reading["lines"][1]["values"][0] = "31"
    reading["lines"][1]["sign"] = -1
    reading["lines"].append(
        {
            "label_raw": "Restructuring",
            "role": "adjustment",
            "sign": 1,
            "values": ["1", "1"],
        }
    )
    reading["scale"] = "thousands"
    found = compare(DRAFT, reading).disagreements
    assert any(d.startswith("scale:") for d in found)
    assert any(d.startswith("sign of 'Interest expense (1)'") for d in found)
    assert any("line only in reading: 'Restructuring'" in d for d in found)
    # Sign disagreement blocks the upgrade for that line even where values agree.
    values = {
        (v["label_raw"], v["period_id"]): v for v in compare(DRAFT, reading).values
    }
    assert (
        values[("Interest expense (1)", "3M-2026-06-30")]["proposed_verified_by"]
        is None
    )


def test_period_disagreement() -> None:
    reading = copy.deepcopy(READING)
    reading["periods"] = [
        {"period_id": "3M-2026-06-30"},
        {"period_id": "6M-2026-06-30"},
    ]
    found = compare(DRAFT, reading).disagreements
    assert any(d.startswith("periods:") for d in found)


def test_table_pointer_gives_link_and_searchable_labels() -> None:
    from tools.gold.compare import table_pointer

    rel = {
        "source_url": "https://www.sec.gov/Archives/edgar/data/0/000000000026000001/fixture.htm",
        "metric_label_raw": "Adjusted EBITDA",
        "table": {"table_index": 3},
        "lines": [
            {"label_raw": "Net income", "values": [{"value_raw": "100"}]},
            {"label_raw": "Adjusted EBITDA", "values": [{"value_raw": "150"}]},
        ],
    }
    out = table_pointer(rel)
    assert out[0].endswith("fixture.htm")
    assert "**Net income** (first number: 100)" in out[1]
    assert "ending with **Adjusted EBITDA**" in out[1]
    assert out[2].startswith("- [ ] ") and "table 3" in out[2]
