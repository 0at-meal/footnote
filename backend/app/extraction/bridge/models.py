"""
Shared vocabulary for bridge lines (engine output and gold labels).
"""

from enum import Enum


class LineRole(str, Enum):
    gaap_start = "gaap_start"  # the GAAP measure the bridge starts from
    adjustment = "adjustment"  # an add-back or deduction
    subtotal = "subtotal"  # e.g. EBITDA before further adjustments
    total = "total"  # the headline non-GAAP metric
    memo = "memo"  # shown in the table but not part of the bridge
