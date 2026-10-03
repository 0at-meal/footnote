"""
Process-wide settings read from the environment.

- FOOTNOTE_DATA_DIR: where jobs, uploads and results live (default: backend/data).
  Used to run experiments and end-to-end tests against a copy, never the user's data.
- ALLOW_PYMUPDF_FALLBACK: "1" enables the degraded PDF mode when Docling is missing (D1).
- PUBLIC_BASE_URL: base URL written into workbook deep links (D9).
"""

import os
from pathlib import Path

_REPO_DATA_DIR: Path = Path(__file__).parent.parent / "data"


def resolve_data_dir() -> Path:
    raw = os.environ.get("FOOTNOTE_DATA_DIR", "").strip()
    return Path(raw).expanduser().resolve() if raw else _REPO_DATA_DIR


DEFAULT_DATA_DIR: Path = resolve_data_dir()


def pymupdf_fallback_allowed() -> bool:
    return os.environ.get("ALLOW_PYMUPDF_FALLBACK", "").strip() == "1"
