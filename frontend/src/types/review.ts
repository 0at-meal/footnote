// Frozen field names per CONSTITUTION ? 2.3 ? do not rename.

export type ConfidenceBand = 'auto_accepted' | 'needs_review' | 'manual_required'

export type StatementType =
  | 'income_statement'
  | 'balance_sheet'
  | 'cash_flow'
  | 'non_gaap_bridge'
  | 'kpi'

export type ReviewStatus =
  | 'auto_accepted'
  | 'needs_review'
  | 'manual_required'
  | 'extraction_error'
  | 'pending_taxonomy_confirmation'
  | 'flagged'
  | 'locked'

export type BoundingBox = {
  x0: number
  y0: number
  x1: number
  y1: number
}

export type PdfLocator = {
  type: 'pdf'
  page: number
  bbox: BoundingBox
  source_file: string
}

export type HtmlLocator = {
  type: 'html'
  /** SEC CIK of the filer; needed for a valid sec.gov Archives URL (D9). */
  cik?: string | null
  accession: string
  document: string
  element_path: string
  char_range?: [number, number] | null
  url?: string | null
  source_file?: string | null
}

export type Locator = PdfLocator | HtmlLocator

export type ReviewItem = {
  id: string
  value: string
  label: string
  page: number
  bbox: BoundingBox
  source_file: string
  locator?: Locator
  confidence_band: ConfidenceBand
  confidence_score: number
  normalized_label: string | null
  taxonomy_status: string | null
  status: ReviewStatus
  flags: string[]
  is_target_metric_candidate?: boolean
  table_name?: string | null
  error_detail: string | null
  statement_type?: StatementType | null
}

export type ReviewItemsResponse = {
  job_id: string
  items: ReviewItem[]
  total_items: number
  parser_used?: 'docling' | 'pymupdf' | 'mixed' | 'ixbrl_html' | null
  target_metric_found?: boolean
}
