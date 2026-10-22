"""
Coverage universe (P1-08): ``config/universe.yaml``.

Each entry is a ticker, its 10-digit CIK as resolved from EDGAR, and a sector
label. The file is written by ``tools.universe.build`` from EDGAR lookups, never
by hand-typed CIKs.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from app.pipeline.ingest import UniverseEntry

UNIVERSE_FILE = Path(__file__).resolve().parents[3] / "config" / "universe.yaml"
_CIK = re.compile(r"^\d{10}$")


class UniverseError(ValueError):
    """The universe file is malformed."""


def load_universe(path: Path = UNIVERSE_FILE) -> list[UniverseEntry]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    entries: list[UniverseEntry] = []
    seen: set[str] = set()
    for i, raw in enumerate(data.get("issuers") or []):
        ticker = str(raw.get("ticker", "")).strip().upper()
        cik = str(raw.get("cik", "")).strip()
        if not ticker:
            raise UniverseError(f"entry {i}: ticker missing")
        if not _CIK.match(cik):
            raise UniverseError(f"{ticker}: cik must be 10 digits, got {cik!r}")
        if cik in seen:
            raise UniverseError(f"{ticker}: duplicate cik {cik}")
        seen.add(cik)
        entries.append(
            UniverseEntry(ticker=ticker, cik=cik, sector=str(raw.get("sector", "")))
        )
    if not entries:
        raise UniverseError(f"{path}: no issuers")
    return entries
