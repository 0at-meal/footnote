"""
``footnote`` command line (P1-09).

    python -m app.pipeline.cli ingest [--quarters 8] [--db PATH] [--only TICKER ...]
    python -m app.pipeline.cli export [--out web-dist]
    python -m app.pipeline.cli review export queue.csv
    python -m app.pipeline.cli review apply queue.csv --reviewer "Your Name"

Requires ``SEC_USER_AGENT``. The database defaults to ``$FOOTNOTE_DB`` or
``var/footnote.db`` at the repository root.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.analytics.digest import build_digest
from app.analytics.snapshot import build_snapshot
from app.analytics.source import source_table
from app.config import REPO_ROOT, default_cache_dir, default_db
from app.export.web import web_page
from app.ingestion.edgar.client import EdgarClient
from app.pipeline.ingest import run_ingest
from app.pipeline.review import apply_queue, export_queue
from app.pipeline.universe import load_universe
from app.store.db import Store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="footnote")
    parser.add_argument("--db", type=Path, default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest", help="ingest earnings releases from EDGAR")
    ing.add_argument("--quarters", type=int, default=8)
    ing.add_argument("--only", nargs="*", help="tickers to ingest (default: all)")
    rev = sub.add_parser("review", help="category review queue (P3-02)")
    rev.add_argument("action", choices=["export", "apply"])
    rev.add_argument("path", type=Path, help="CSV file to write or read")
    rev.add_argument("--reviewer", default="", help="your name (required for apply)")
    dig = sub.add_parser("digest", help="watchlist change digest as HTML (P4-06)")
    dig.add_argument("--tickers", nargs="+", required=True)
    dig.add_argument("--since", type=date.fromisoformat, required=True)
    dig.add_argument("--until", type=date.fromisoformat, default=None)
    dig.add_argument("--out", type=Path, required=True)
    exp = sub.add_parser("export", help="write the static web app + snapshot.json")
    exp.add_argument("--out", type=Path, default=REPO_ROOT / "web-dist")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    store = Store(args.db or default_db())
    if args.cmd == "ingest":
        universe = load_universe()
        if args.only:
            wanted = {t.upper() for t in args.only}
            universe = [u for u in universe if u.ticker in wanted]
        stats = run_ingest(
            EdgarClient(cache_dir=default_cache_dir()),
            store,
            universe,
            quarters=args.quarters,
            command=" ".join(argv or sys.argv[1:]),
        )
        print(json.dumps(stats.as_dict(), indent=2))
    elif args.cmd == "review":
        if args.action == "export":
            n = export_queue(store, args.path)
            print(f"{n} labels to review written to {args.path}")
        else:
            res = apply_queue(store, args.path, args.reviewer)
            print(f"applied {res.applied}, skipped {res.skipped} blank rows")
            for e in res.errors:
                print(f"ERROR {e}")
            if res.errors:
                return 1
    elif args.cmd == "digest":
        until = args.until or datetime.now(UTC).date()
        html, n = build_digest(build_snapshot(store), args.tickers, args.since, until)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(html, encoding="utf-8")
        print(f"{n} change(s) written to {args.out}")
    elif args.cmd == "export":
        snap = build_snapshot(store)
        snap["static"] = True
        # The static app has no API: embed each issuer's latest-quarter table.
        sources: dict[str, Any] = {}
        for doc in snap["issuers"]:
            if doc["quarters"]:
                acc = doc["quarters"][-1]["accession"]
                src = source_table(store, acc, default_cache_dir())
                if src is not None:
                    sources[acc] = src
        snap["sources"] = sources
        bad = [a for a, s in sources.items() if s["status"] != "ok"]
        if bad:
            print(f"{len(bad)} source table(s) not embedded: {', '.join(bad)}")
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "snapshot.json").write_text(
            json.dumps(snap, separators=(",", ":")), encoding="utf-8"
        )
        (args.out / "index.html").write_text(web_page(), encoding="utf-8")
        print(f"wrote {args.out} ({len(snap['issuers'])} issuers)")
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
