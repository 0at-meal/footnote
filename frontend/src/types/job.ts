// Frozen field names per CONSTITUTION §2.3 — do not rename.

export const TARGET_METRICS = [
  'Adjusted EBITDA',
  'EBITDA',
  'Net Income',
  'Free Cash Flow',
] as const

export type TargetMetric = (typeof TARGET_METRICS)[number]

export const DEFAULT_METRIC: TargetMetric = 'Adjusted EBITDA'

/**
 * A file that has been accepted client-side and is awaiting submission.
 * This is local state only — no backend job_id exists yet (that is Feature 1, Step 3).
 */
export type StagedFile = {
  /** Locally generated UUID — not the backend job_id. */
  id: string
  /** The raw File object held in memory. */
  file: File
  /** Original filename as uploaded — stored as-is (UTF-8). */
  filename: string
  /** Exact byte count from File.size. */
  file_size_bytes: number
  /** User-selected target metric; defaults to DEFAULT_METRIC. */
  target_metric: TargetMetric
}

/**
 * A file rejected during client-side type checking.
 * Shown inline in the upload zone; never added to StagedFile[].
 */
export type RejectedFile = {
  filename: string
  reason: string
}

/**
 * Lifecycle states for a persisted job (mirrors backend JobStatus enum).
 * Values are frozen per CONSTITUTION §2.3 — do not rename.
 */
export type JobStatus = 'queued' | 'extracting' | 'done' | 'failed'

/**
 * A backend-persisted job record returned by POST /upload/jobs and GET /upload/jobs.
 * Field names are frozen per CONSTITUTION §2.3.
 */
export type JobRecord = {
  /** UUIDv4 assigned by the server — the authoritative job identifier. */
  job_id: string
  /** Original filename as uploaded (UTF-8, stored as-is — EC-8). */
  filename: string
  /** Exact byte count of the accepted file. */
  file_size_bytes: number
  /** Current job lifecycle state. */
  status: JobStatus
  /** Target metric selected before submission (locked after queuing — spec AC-6). */
  target_metric: string
  /** ISO 8601 UTC timestamp of job creation. */
  submitted_at: string
  /** Whether an Excel model workbook is ready for download (Ticket 0.4.3). */
  model_ready?: boolean
}

