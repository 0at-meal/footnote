"""
Test-session isolation: the app's default data directory points at a throwaway directory, never
at backend/data (the user's real jobs). Must run before any `app.*` import, which pytest guarantees
for the root conftest.

Known gap (logged in docs/audit/FIX_PROGRESS.md): the seed taxonomy is read from
<data dir>/taxonomy.json, which is gitignored. Until the seed is versioned with the code, a
read-only copy of the local file is placed in the temp dir so taxonomy tests keep running.
"""

import os
import shutil
import tempfile
from pathlib import Path

# Tests never use a real Groq key. Set it empty before app import: the classifier calls
# load_dotenv(), which does not override variables that already exist, so the developer's .env
# key stays out of the test session and local runs behave like CI.
os.environ["GROQ_API_KEY"] = ""

if not os.environ.get("FOOTNOTE_DATA_DIR"):
    _tmp = Path(tempfile.mkdtemp(prefix="footnote-test-data-"))
    _seed = Path(__file__).resolve().parent.parent / "data" / "taxonomy.json"
    if _seed.exists():
        shutil.copyfile(_seed, _tmp / "taxonomy.json")
    os.environ["FOOTNOTE_DATA_DIR"] = str(_tmp)
