"""
``footnote`` command line (P1-09).

    python -m app.pipeline.cli ingest [--quarters 8] [--db PATH] [--only TICKER ...]
    python -m app.pipeline.cli export [--out web-dist]

Requires ``SEC_USER_AGENT``. The database defaults to ``$FOOTNOTE_DB`` or
``var/footnote.db`` at the repository root.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path

from app.analytics.snapshot import build_snapshot
from app.config import REPO_ROOT, default_db
from app.ingestion.edgar.client import EdgarClient
from app.pipeline.ingest import run_ingest
from app.pipeline.universe import load_universe
from app.store.db import Store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="footnote")
    parser.add_argument("--db", type=Path, default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest", help="ingest earnings releases from EDGAR")
    ing.add_argument("--quarters", type=int, default=8)
    ing.add_argument("--only", nargs="*", help="tickers to ingest (default: all)")
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
        cache = os.environ.get("EDGAR_CACHE_DIR") or str(
            REPO_ROOT / "backend" / "data" / "edgar_cache"
        )
        stats = run_ingest(
            EdgarClient(cache_dir=cache),
            store,
            universe,
            quarters=args.quarters,
            command=" ".join(["ingest", *(argv or sys.argv[1:])]),
        )
        print(json.dumps(stats.as_dict(), indent=2))
    elif args.cmd == "export":
        snap = build_snapshot(store)
        snap["static"] = True
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "snapshot.json").write_text(
            json.dumps(snap, separators=(",", ":")), encoding="utf-8"
        )
        shutil.copy(REPO_ROOT / "web" / "index.html", args.out / "index.html")
        print(f"wrote {args.out} ({len(snap['issuers'])} issuers)")
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
