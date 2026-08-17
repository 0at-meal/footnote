import type { JobStatus } from '../types/job'

/**
 * Builds the canonical audit report download endpoint URL.
 */
export function buildAuditReportDownloadUrl(apiBase: string, jobId: string): string {
  const base = apiBase.replace(/\/+$/, '')
  return `${base}/api/jobs/${encodeURIComponent(jobId)}/audit-report`
}

/**
 * Builds the suggested filename for client-side audit report PDF downloads.
 */
export function buildAuditReportFilename(jobId: string): string {
  return `audit_report_${jobId}.pdf`
}

/**
 * Determines whether a job is eligible for audit report export.
 * Audit reports require a completed pipeline run ('done').
 */
export function canDownloadAuditReport(status: JobStatus): boolean {
  return status === 'done'
}
