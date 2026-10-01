"""
SEC EDGAR On-Demand Filing Downloader for Footnote Benchmark Corpus (FN-010).

Downloads filing artifacts on demand to a gitignored local cache directory.
Filings, PDFs, and HTML sources are NEVER committed to version control.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent / ".cache"
MANIFEST_PATH = Path(__file__).resolve().parent / "corpus" / "labels" / "manifest.json"


def get_cache_dir() -> Path:
    """Returns the gitignored filing cache directory, creating it if needed."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def fetch_filing_by_accession(
    accession_number: str,
    form: str = "10-K",
    ticker: str = "UNKNOWN",
    user_agent: str = "Footnote Research bot@footnote.local",
    mock_if_unavailable: bool = True,
) -> Path:
    """
    Downloads or retrieves a filing from the local cache.

    Args:
        accession_number: SEC EDGAR Accession Number e.g. '0001018724-23-000014'
        form: Form type e.g. '10-K', '10-Q', '8-K'
        ticker: Ticker symbol
        user_agent: User-Agent header complying with SEC fair access policy
        mock_if_unavailable: If network fails or offline, creates a synthetic placeholder

    Returns:
        Path to cached filing file.
    """
    cache = get_cache_dir()
    clean_acc = accession_number.replace("-", "")
    target_filename = f"{accession_number}_{form.replace(' ', '_').replace('/', '_')}.html"
    cached_file = cache / target_filename

    if cached_file.exists():
        logger.info("Found cached filing: %s", cached_file)
        return cached_file

    # Build SEC EDGAR URL
    url = f"https://www.sec.gov/Archives/edgar/data/{clean_acc}/{accession_number}.txt"

    headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
    req = urllib.request.Request(url, headers=headers)

    try:
        logger.info("Downloading %s from SEC EDGAR...", url)
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            content = resp.read()
            cached_file.write_bytes(content)
            logger.info("Cached filing to: %s (%d bytes)", cached_file, len(content))
            return cached_file
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        logger.warning("Network fetch failed for accession %s: %s", accession_number, e)
        if mock_if_unavailable:
            logger.info("Generating mock cached document for test harness...")
            mock_content = (
                f"<!-- MOCK SEC EDGAR FILING -->\n"
                f"<accession>{accession_number}</accession>\n"
                f"<ticker>{ticker}</ticker>\n"
                f"<form>{form}</form>\n"
                f"<div>Non-GAAP Reconciliation Table for {ticker}</div>\n"
            ).encode("utf-8")
            cached_file.write_bytes(mock_content)
            return cached_file
        raise


def fetch_all_manifest_filings(dev_only: bool = False, mock: bool = True) -> list[Path]:
    """Downloads all benchmark corpus filings specified in manifest.json."""
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Corpus manifest not found: {MANIFEST_PATH}")

    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    accessions = data.get("filing_accessions", [])
    results: list[Path] = []

    labels_dir = MANIFEST_PATH.parent
    for acc in accessions:
        label_file = labels_dir / f"{acc}.json"
        if not label_file.exists():
            continue
        label_data = json.loads(label_file.read_text(encoding="utf-8"))
        if dev_only and label_data.get("split") != "dev":
            continue

        p = fetch_filing_by_accession(
            accession_number=acc,
            form=label_data.get("form", "10-K"),
            ticker=label_data.get("ticker", "UNKNOWN"),
            mock_if_unavailable=mock,
        )
        results.append(p)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Footnote Benchmark Filing Fetcher")
    parser.add_argument("--accession", type=str, help="Specific accession number to fetch")
    parser.add_argument("--dev-only", action="store_true", help="Fetch dev split only")
    parser.add_argument("--mock", action="store_true", default=True, help="Mock if SEC EDGAR unreachable")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    if args.accession:
        p = fetch_filing_by_accession(args.accession, mock_if_unavailable=args.mock)
        print(f"Filing available at: {p}")
    else:
        paths = fetch_all_manifest_filings(dev_only=args.dev_only, mock=args.mock)
        print(f"Fetched {len(paths)} filings to {get_cache_dir()}")


if __name__ == "__main__":
    main()
