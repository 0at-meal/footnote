// Frozen field names per CONSTITUTION §2.3 — do not rename.

export type BoundingBox = {
  x0: number
  y0: number
  x1: number
  y1: number
}

export type SourceComponent = {
  component_id: string
  source_file: string
  page: number
  bbox: BoundingBox
  value: string
  label: string
  normalized_label: string | null
  review_status: string
  is_missing: boolean
  provenance_id: string | null
}

export type SourceChainResponse = {
  job_id: string
  sheet_name: string | null
  cell_coord: string | null
  provenance_id: string | null
  node_id: string | null
  is_formula: boolean
  formula_expression: string | null
  is_found: boolean
  components: SourceComponent[]
  error_detail: string | null
}

export type ProvenanceSummaryRecord = {
  id: string
  job_id: string
  sheet_name: string
  cell_coord: string
  node_id: string
  is_formula: boolean
}

export type ProvenanceQueryResponse = {
  job_id: string
  total_records: number
  records: ProvenanceSummaryRecord[]
}
