// Frozen field names per CONSTITUTION §2.3 — do not rename.

export type ConfidenceBand = 'auto_accepted' | 'needs_review' | 'manual_required'

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

export type ReviewItem = {
  id: string
  value: string
  label: string
  page: number
  bbox: BoundingBox
  source_file: string
  confidence_band: ConfidenceBand
  confidence_score: number
  normalized_label: string | null
  taxonomy_status: string | null
  status: ReviewStatus
  flags: string[]
  is_target_metric_candidate?: boolean
  table_name?: string | null
  error_detail: string | null
}

export type ReviewItemsResponse = {
  job_id: string
  items: ReviewItem[]
  total_items: number
}
