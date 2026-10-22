"""
Row-label patterns for non-GAAP bridges (bridge engine, P0-01 shortlist, P0-05 drafts).
"""

import re

# The GAAP measure a non-GAAP bridge starts from.
GAAP_START = re.compile(
    r"\bnet (?:\(loss\) income|income \(loss\)|income|loss)\b"
    r"|\boperating (?:income|loss)\b|\bincome (?:\(loss\) )?before\b"
    r"|\b(?:income|loss|income \(loss\)) from continuing operations\b",
    re.IGNORECASE,
)

# EBITDA-labelled rows that are not the bridge total.
NOT_A_TOTAL = re.compile(
    r"margin|%|per share|percent|\bltm\b|last twelve|trailing twelve", re.IGNORECASE
)

# A bridge from a GAAP measure to EBITDA adds back at least two of these.
BRIDGE_TERMS = ("interest", "tax", "depreciation", "amortization")

# The table states outright that it reconciles to EBITDA.
RECON_TITLE = re.compile(r"reconciliation.*ebitda", re.IGNORECASE)

# Label directives that make a line subtract from the total.
SUBTRACT_DIRECTIVE = re.compile(r"^\s*(?:less|deduct)\b", re.IGNORECASE)
