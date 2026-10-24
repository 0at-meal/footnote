"""
P1-08: build ``config/universe.yaml`` from EDGAR lookups.

Every candidate ticker is resolved to its CIK through SEC ``company_tickers.json``
and checked against its submissions feed: it must be a domestic filer with at
least ``MIN_RELEASES`` Item 2.02 8-Ks in the last two years. The first
``TARGET`` passing candidates, in list order (the 15 gold-set issuers first),
are written with EDGAR's name and CIK. Rejections are written with reasons.

Sector labels are Footnote's own grouping for peer comparison, not EDGAR SIC.

Usage (from ``backend/``, with ``SEC_USER_AGENT`` set)::

    python -m tools.universe.build
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, timedelta

import yaml
from app.ingestion.edgar.client import EdgarClient
from app.ingestion.edgar.models import EdgarClientError
from app.pipeline.universe import UNIVERSE_FILE

TARGET = 50
MIN_RELEASES = 4

# (ticker, sector). Gold-set issuers first. Unverified until this tool runs.
CANDIDATES: list[tuple[str, str]] = [
    ("TDG", "Aerospace & defense"),
    ("CZR", "Gaming & leisure"),
    ("WYNN", "Gaming & leisure"),
    ("HTZ", "Vehicle rental"),
    ("CAR", "Vehicle rental"),
    ("THC", "Healthcare services"),
    ("CYH", "Healthcare services"),
    ("IHRT", "Media"),
    ("LUMN", "Telecom & cable"),
    ("CHTR", "Telecom & cable"),
    ("CVNA", "Auto retail"),
    ("BHC", "Pharma"),
    ("CC", "Chemicals"),
    ("RXT", "IT services"),
    ("FUN", "Gaming & leisure"),
    ("MGM", "Gaming & leisure"),
    ("PENN", "Gaming & leisure"),
    ("BYD", "Gaming & leisure"),
    ("RRR", "Gaming & leisure"),
    ("CHDN", "Gaming & leisure"),
    ("CCL", "Cruise"),
    ("NCLH", "Cruise"),
    ("RCL", "Cruise"),
    ("CNK", "Gaming & leisure"),
    ("AMC", "Gaming & leisure"),
    ("SIRI", "Media"),
    ("SBGI", "Media"),
    ("GTN", "Media"),
    ("NXST", "Media"),
    ("TGNA", "Media"),
    ("AMCX", "Media"),
    ("WBD", "Media"),
    ("CCO", "Media"),
    ("SATS", "Telecom & cable"),
    ("UNIT", "Telecom & cable"),
    ("LAMR", "Media"),
    ("OUT", "Media"),
    ("SEM", "Healthcare services"),
    ("ACHC", "Healthcare services"),
    ("OMI", "Healthcare services"),
    ("AVTR", "Life sciences tools"),
    ("COTY", "Consumer products"),
    ("NWL", "Consumer products"),
    ("MAT", "Consumer products"),
    ("HBI", "Consumer products"),
    ("WOOF", "Retail"),
    ("USFD", "Food distribution"),
    ("PFGC", "Food distribution"),
    ("ARMK", "Business services"),
    ("SPB", "Consumer products"),
    ("POST", "Food & beverage"),
    ("CLVT", "Information services"),
    ("CLF", "Metals & mining"),
    ("OLN", "Chemicals"),
    ("TROX", "Chemicals"),
    ("BLDR", "Building products"),
    ("HRI", "Equipment rental"),
    ("URI", "Equipment rental"),
    ("WSC", "Equipment rental"),
    ("SABR", "IT services"),
    ("XRX", "IT services"),
    ("PBI", "Business services"),
    ("VST", "Power"),
    ("NRG", "Power"),
]


def main() -> int:
    client = EdgarClient()
    since = datetime.now(UTC).date() - timedelta(days=730)
    selected: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    for ticker, sector in CANDIDATES:
        if len(selected) >= TARGET:
            break
        try:
            cik = client.resolve_cik(ticker)
            subs = client.get_submissions(cik)
            filings = client.get_filings(
                cik, forms=["8-K"], items=["2.02"], limit=200, submissions=subs
            )
        except EdgarClientError as exc:
            rejected.append({"ticker": ticker, "reason": str(exc)})
            print(f"{ticker:5} rejected: {exc}")
            continue
        recent = [f for f in filings if date.fromisoformat(f.filed_at) >= since]
        if len(recent) < MIN_RELEASES:
            reason = f"{len(recent)} Item 2.02 8-Ks since {since} (< {MIN_RELEASES})"
            rejected.append({"ticker": ticker, "cik": cik, "reason": reason})
            print(f"{ticker:5} rejected: {reason}")
            continue
        selected.append(
            {
                "ticker": ticker,
                "cik": cik,
                "name": str(subs.get("name", "")),
                "sector": sector,
            }
        )
        print(f"{ticker:5} {cik} {subs.get('name')} ({len(recent)} releases)")
    UNIVERSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    UNIVERSE_FILE.write_text(
        yaml.safe_dump(
            {
                "ticket": "P1-08",
                "generated": datetime.now(UTC).date().isoformat(),
                "generated_by": "tools.universe.build",
                "rule": f"domestic filer, >= {MIN_RELEASES} Item 2.02 8-Ks in 2 years",
                "issuers": selected,
                "rejected": rejected,
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    print(f"{len(selected)} issuers written to {UNIVERSE_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
