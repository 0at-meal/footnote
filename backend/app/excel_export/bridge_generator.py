"""
Non-GAAP Reconciliation Bridge Excel Generator (Workflow Pack 1 / Step 7).

Serializes a FormulaTree into a deterministic 2-tab workbook:
- Source_Inputs: Raw line items extracted from filing
- Reconciliation: Dynamic non-GAAP bridge with zero numeric hardcodes
"""

from app.excel_export.generator import (
    generate_workbook,
)
from app.excel_export.generator import (
    generate_workbook as generate_bridge_workbook,
)

__all__ = ["generate_bridge_workbook", "generate_workbook"]
