"""
Test-session isolation: the app's default data directory points at a throwaway
directory, never at backend/data. Runs before any ``app.*`` import, which pytest
guarantees for the root conftest.
"""

import os
import tempfile

if not os.environ.get("FOOTNOTE_DATA_DIR"):
    os.environ["FOOTNOTE_DATA_DIR"] = tempfile.mkdtemp(prefix="footnote-test-data-")
