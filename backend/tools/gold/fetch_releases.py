"""
P0-03: save the gold-set earnings releases, with integrity hashes.

Reads the approved shortlist (``eval/gold/issuers.yaml``), fetches each selected
EX-99.1 through the EDGAR client (its immutable cache is reused), and writes:

- ``eval/gold/raw/<accession>/<exhibit>.gz``: the exhibit bytes exactly as served
  by sec.gov, gzip-compressed;
- ``eval/gold/raw/manifest.yaml``: one entry per release with ticker, CIK,
  accession, filing date, exhibit, CIK-qualified sec.gov URL, byte size and the
  sha256 of the *original* (uncompressed) bytes.

``--verify`` re-hashes every saved file against the manifest and exits non-zero
on any mismatch or missing file, so CI can prove the gold inputs are unchanged.

Usage (from ``backend/``)::

    python -m tools.gold.fetch_releases            # needs SEC_USER_AGENT
    python -m tools.gold.fetch_releases --verify   # offline
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml
from app.ingestion.edgar.client import EdgarClient

GOLD_DIR = Path(__file__).resolve().parents[3] / "eval" / "gold"
RAW_DIR = GOLD_DIR / "raw"
MANIFEST = RAW_DIR / "manifest.yaml"
EXPECTED_RELEASES = 30


@dataclass(frozen=True)
class ReleaseEntry:
    ticker: str
    cik: str
    accession: str
    filed: str
    exhibit: str
    url: str
    bytes: int
    sha256: str
    path: str  # relative to eval/gold/raw/


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stored_path(accession: str, exhibit: str) -> str:
    return f"{accession}/{exhibit}.gz"


def selected_releases(issuers: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the approved shortlist into one dict per release, in file order."""
    if not issuers.get("approved_by"):
        raise ValueError("issuers.yaml is not approved (P0-02): approved_by is empty")
    out: list[dict[str, Any]] = []
    for issuer in issuers["selected"]:
        for rel in issuer["releases"]:
            out.append({"ticker": issuer["ticker"], "cik": issuer["cik"], **rel})
    return out


def save_release(raw_dir: Path, rel: dict[str, Any], content: bytes) -> ReleaseEntry:
    """Write one release gzip-compressed and return its manifest entry."""
    rel_path = stored_path(rel["accession"], rel["exhibit"])
    target = raw_dir / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 keeps the .gz bytes deterministic across runs.
    with target.open("wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", mtime=0) as gz:
        gz.write(content)
    return ReleaseEntry(
        ticker=rel["ticker"],
        cik=rel["cik"],
        accession=rel["accession"],
        filed=str(rel["filed"]),
        exhibit=rel["exhibit"],
        url=rel["url"],
        bytes=len(content),
        sha256=sha256_hex(content),
        path=rel_path,
    )


def verify(raw_dir: Path, manifest: dict[str, Any]) -> list[str]:
    """Problems found re-hashing saved files; an empty list means all good."""
    problems: list[str] = []
    for entry in manifest["releases"]:
        target = raw_dir / entry["path"]
        if not target.exists():
            problems.append(f"missing: {entry['path']}")
            continue
        data = gzip.decompress(target.read_bytes())
        if sha256_hex(data) != entry["sha256"]:
            problems.append(f"sha256 mismatch: {entry['path']}")
        if len(data) != entry["bytes"]:
            problems.append(f"size mismatch: {entry['path']}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="re-hash saved files")
    args = parser.parse_args()

    if args.verify:
        manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
        problems = verify(RAW_DIR, manifest)
        for p in problems:
            print(p)
        print(f"{len(manifest['releases'])} releases checked, {len(problems)} problems")
        return 1 if problems else 0

    issuers = yaml.safe_load((GOLD_DIR / "issuers.yaml").read_text(encoding="utf-8"))
    releases = selected_releases(issuers)
    if len(releases) != EXPECTED_RELEASES:
        print(f"expected {EXPECTED_RELEASES} releases, found {len(releases)}")
        return 1

    client = EdgarClient()
    entries: list[ReleaseEntry] = []
    for rel in releases:
        doc = client.get_document(rel["accession"], rel["exhibit"], cik=rel["cik"])
        if doc.url != rel["url"]:
            print(f"{rel['accession']}: URL changed: {doc.url} != {rel['url']}")
            return 1
        entries.append(save_release(RAW_DIR, rel, doc.content))
        print(f"{rel['ticker']:5} {rel['accession']} {len(doc.content):>9,} B")

    manifest_out = {
        "ticket": "P0-03",
        "source": "eval/gold/issuers.yaml (approved)",
        "storage": "gzip of the exact bytes served by sec.gov; sha256 is of the "
        "uncompressed bytes",
        "releases": [asdict(e) for e in entries],
    }
    MANIFEST.write_text(
        yaml.safe_dump(manifest_out, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    problems = verify(RAW_DIR, manifest_out)
    print(f"saved {len(entries)} releases; verify: {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
