"""
Process-wide settings read from the environment.

- FOOTNOTE_DATA_DIR: where runtime data (e.g. taxonomy overrides) lives
  (default: backend/data). Tests point it at a throwaway directory.
- FOOTNOTE_DB: the observation store (default: var/footnote.db at the repo root).
"""

import os
from pathlib import Path

_REPO_DATA_DIR: Path = Path(__file__).parent.parent / "data"


def resolve_data_dir() -> Path:
    raw = os.environ.get("FOOTNOTE_DATA_DIR", "").strip()
    return Path(raw).expanduser().resolve() if raw else _REPO_DATA_DIR


DEFAULT_DATA_DIR: Path = resolve_data_dir()

REPO_ROOT: Path = Path(__file__).resolve().parents[2]


def default_db() -> Path:
    raw = os.environ.get("FOOTNOTE_DB", "").strip()
    return Path(raw) if raw else REPO_ROOT / "var" / "footnote.db"
