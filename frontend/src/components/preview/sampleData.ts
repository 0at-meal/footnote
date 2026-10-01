import type { WorkbookRow, CheckItem } from './WorkbookPreview'

export const DEFAULT_SAMPLE_ROWS: WorkbookRow[] = [
  { rowNumber: 1, label: 'Revenues', value: 12500, isHeader: false },
  { rowNumber: 2, label: 'Cost of Goods Sold', value: -7200, isHeader: false },
  { rowNumber: 3, label: 'Gross Profit', value: 5300, formula: '=B1+B2', isTotal: true },
  { rowNumber: 4, label: 'Operating Income (EBIT)', value: 2150, status: 'verified', isTotal: true },
  { rowNumber: 5, label: 'Depreciation & Amortization', value: 450, status: 'auto_accepted', sourcePage: 32 },
  {
    rowNumber: 6,
    label: 'Stock-Based Compensation',
    value: 180,
    status: 'needs_review',
    comment: 'Flagged for review: confidence 0.82',
    sourcePage: 38,
  },
  {
    rowNumber: 7,
    label: 'Acquisition & Integration Costs',
    value: 65,
    status: 'auto_accepted',
    sourcePage: 41,
  },
  {
    rowNumber: 8,
    label: 'Litigation Settlement',
    value: null,
    status: 'manual_required',
    comment: 'Manual input required: caption matched without definite value',
    sourcePage: 44,
  },
  {
    rowNumber: 9,
    label: 'Adjusted EBITDA',
    value: 2845,
    formula: '=SUM(B4:B8)',
    isTotal: true,
  },
]

export const DEFAULT_CHECKS: CheckItem[] = [
  { id: 'c1', name: 'Tranches sum to total debt', passed: true },
  { id: 'c2', name: 'Operating income ties to Income Statement', passed: true },
  { id: 'c3', name: 'Reconciliation math ties out', passed: true },
  { id: 'c4', name: 'Sign & scale consistency verified', passed: true },
  { id: 'c5', name: 'No duplicate period definitions', passed: true },
]
