"""
Tests for the A-19 brief. The snapshot is a small synthetic fixture (FIX*
tickers, example URLs on the fixture CIK); no filing is described.
"""

from typing import Any

from app.analytics.brief import NARRATIVE_PENDING, build_brief, to_markdown

URL = "https://www.sec.gov/Archives/edgar/data/1/000000000026000002/ex991.htm"


def snapshot() -> dict[str, Any]:
    quarter = {
        "period_id": "3M-2026-06-30",
        "end_date": "2026-06-30",
        "accession": "0000000000-26-000002",
        "exhibit_url": URL,
        "scale": "millions",
        "metric_label": "Adjusted EBITDA",
        "addback_intensity": 0.25,
        "normalization": {
            "reported_total": "200",
            "normalized": "180",
            "excluded": "20",
            "status": "computed",
            "reason": None,
            "policy_version": "footnote-default v0.1",
            "preview": True,
            "pending_review": 3,
        },
    }
    old = {**quarter, "period_id": "3M-2025-06-30", "end_date": "2025-06-30"}
    releases = [
        {
            "accession": "0000000000-26-000002",
            "filed": "2026-08-05",
            "url": URL,
            "status": "ok",
            "exceptions": [],
        },
        {
            "accession": "0000000000-26-000001",
            "filed": "2026-05-05",
            "url": URL,
            "status": "exceptions",
            "exceptions": ["sum tie-out failed for 3M-2026-03-31"],
        },
    ]
    return {
        "issuers": [
            {
                "ticker": "FIXT",
                "name": "Fixture Co",
                "sector": "Fixtures",
                "quarters": [old, quarter],
                "releases": releases,
                "recasts": [
                    {
                        "label": "Headline total",
                        "period_id": "3M-2025-06-30",
                        "first_usd": 1.9e8,
                        "latest_usd": 1.95e8,
                        "latest_accession": "0000000000-26-000002",
                        "latest_url": URL,
                    }
                ],
            },
        ],
        "feed": [
            {
                "type": "added",
                "ticker": "FIXT",
                "label": "Litigation",
                "prior_label": None,
                "accession": "0000000000-26-000002",
                "url": URL,
            },
            {
                "type": "recurring_addback",
                "ticker": "FIXT",
                "label": "Restructuring",
                "accession": "0000000000-26-000002",
                "url": URL,
                "value_raw": "5",
                "code": "RESTR",
                "treatment": "exclude",
            },
            {
                "type": "added",
                "ticker": "FIXT",
                "label": "Older change",
                "accession": "0000000000-26-000001",
                "url": URL,
            },
        ],
        "peers": {
            "Fixtures": {
                "issuers": [
                    {
                        "ticker": "FIXT",
                        "period_id": "3M-2026-06-30",
                        "addback_intensity": 0.25,
                    },
                    {
                        "ticker": "FIXB",
                        "period_id": "3M-2026-06-30",
                        "addback_intensity": 0.4,
                    },
                ],
                "median_addback_intensity": 0.325,
            }
        },
    }


def test_latest_release_brief() -> None:
    b = build_brief(snapshot(), "fixt")
    assert b["release"]["filed"] == "2026-08-05"  # latest by date, not list order
    h = b["headline"]
    assert (h["period_id"], h["reported"], h["normalized"]) == (
        "3M-2026-06-30",
        "200",
        "180",
    )
    assert [c["label"] for c in b["changes"]] == ["Litigation"]
    assert [r["period_id"] for r in b["recasts"]] == ["3M-2025-06-30"]
    assert b["recurring_addbacks"][0]["label"] == "Restructuring"
    assert b["peers"] == {
        "status": "ok",
        "sector": "Fixtures",
        "period_id": "3M-2026-06-30",
        "addback_intensity": 0.25,
        "sector_median": 0.325,
        "rank": 2,
        "of": 2,
    }
    assert b["narrative"] is None and b["narrative_status"] == NARRATIVE_PENDING
    md = to_markdown(b)
    assert "reported 200, normalized 180" in md and f"]({URL})" in md


def test_older_release_and_missing_cases() -> None:
    b = build_brief(snapshot(), "FIXT", "0000000000-26-000001")
    assert b["headline"]["status"] == "unavailable"
    assert b["tieout_exceptions"] == ["sum tie-out failed for 3M-2026-03-31"]
    assert [c["label"] for c in b["changes"]] == ["Older change"]
    assert build_brief(snapshot(), "NOPE")["reason"] == "not_covered"
    assert (
        build_brief(snapshot(), "FIXT", "0000000000-26-000009")["status"] == "not_found"
    )
