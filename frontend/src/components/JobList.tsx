import type { StagedFile, TargetMetric, JobRecord, JobStatus } from '../types/job'
import { WORKFLOW_PACK_LABELS } from '../types/job'
import { buildAuditReportDownloadUrl, buildAuditReportFilename, canDownloadAuditReport } from '../lib/audit_report'
import { Download, FileCheck, History, Trash2, FileText, Info } from 'lucide-react'
import { formatFiscalPeriod } from '../lib/fiscal_period'

interface Props {
  stagedFiles: StagedFile[]
  persistedJobs: JobRecord[]
  apiBase?: string
  onMetricChange?: (id: string, metric: TargetMetric) => void
  onYearChange?: (id: string, year: number | null) => void
  onRemove: (id: string) => void
  onReview?: (jobId: string) => void
  onAuditTrail?: (jobId: string) => void
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const STATUS_LABELS: Record<JobStatus, string> = {
  queued: 'Queued',
  extracting: 'Extracting',
  done: 'Done',
  failed: 'Failed',
}

function StatusBadge({
  status,
  modelReady,
  modelSkipReason,
}: {
  status: JobStatus
  modelReady?: boolean
  modelSkipReason?: string | null
}) {
  if (status === 'done') {
    if (modelReady) {
      return (
        <span className="status-badge status-badge--done status-badge--model-ready" aria-label="Status: Model Ready">
          Model Ready
        </span>
      )
    }
    const tooltip = modelSkipReason || 'No auto-accepted records — review and confirm items to generate model.'
    return (
      <span
        className="status-badge status-badge--awaiting-review"
        aria-label="Status: Awaiting Review"
        title={tooltip}
        style={{ cursor: 'help', display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}
      >
        Awaiting Review
        <Info size={12} style={{ opacity: 0.8 }} aria-hidden="true" />
      </span>
    )
  }

  if (status === 'extracting') {
    return (
      <span
        className="status-badge status-badge--extracting"
        aria-label="Status: Extracting"
        title="Processing PDF — this may take 30–60 seconds for large documents"
        style={{ cursor: 'wait' }}
      >
        Extracting
      </span>
    )
  }

  return (
    <span className={`status-badge status-badge--${status}`} aria-label={`Status: ${STATUS_LABELS[status]}`}>
      {STATUS_LABELS[status]}
    </span>
  )
}

function PdfIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="job-table__pdf-icon"
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
    </svg>
  )
}

function JobList({
  stagedFiles,
  persistedJobs,
  apiBase = 'http://localhost:8000',
  onYearChange,
  onRemove,
  onReview,
  onAuditTrail,
}: Props) {
  const isEmpty = stagedFiles.length === 0 && persistedJobs.length === 0

  if (isEmpty) {
    return (
      <div className="job-list job-list--empty">
        <svg
          width="32"
          height="32"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <path d="M14 2v6h6M12 18v-6M9 15h6" />
        </svg>
        <p>No files staged. Add PDFs above to get started.</p>
      </div>
    )
  }

  return (
    <div className="job-list">
      <table className="job-table" aria-label="Upload queue">
        <thead>
          <tr>
            <th scope="col">File</th>
            <th scope="col">Size</th>
            <th scope="col">Workflow Pack</th>
            <th scope="col">Fiscal Year</th>
            <th scope="col">Status</th>
            <th scope="col">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {/* ── Staged (pending, not yet submitted) ── */}
          {stagedFiles.map((sf) => (
            <tr key={sf.id} className="job-table__row job-table__row--staged">
              <td className="job-table__filename">
                <PdfIcon />
                <span title={sf.filename}>{sf.filename}</span>
              </td>
              <td className="job-table__size fn-tabular tabular-nums">{formatBytes(sf.file_size_bytes)}</td>
              <td className="job-table__metric">
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    padding: '0.2rem 0.55rem',
                    borderRadius: '4px',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    background: 'var(--fn-accent-bg)',
                    color: 'var(--fn-accent-text)',
                    border: '1px solid var(--fn-accent-border)',
                  }}
                >
                  {WORKFLOW_PACK_LABELS[sf.workflow_pack ?? 'non_gaap_bridge']}
                </span>
              </td>
              <td className="job-table__year">
                <input
                  type="number"
                  min="1900"
                  max="2100"
                  placeholder="e.g. 2023"
                  value={sf.filing_year ?? ''}
                  onChange={(e) =>
                    onYearChange?.(
                      sf.id,
                      e.target.value.trim() ? parseInt(e.target.value, 10) : null,
                    )
                  }
                  aria-label={`Fiscal year for ${sf.filename}`}
                  className="job-table__year-input fn-tabular tabular-nums"
                  style={{
                    width: '85px',
                    padding: '0.3rem 0.5rem',
                    fontSize: '0.8125rem',
                    borderRadius: '0.25rem',
                    border: '1px solid var(--fn-border-subtle)',
                    background: 'var(--fn-bg-elevated)',
                    color: 'var(--fn-text-primary)',
                  }}
                />
              </td>
              <td className="job-table__status">
                <span className="status-badge status-badge--pending">Pending</span>
              </td>
              <td className="job-table__remove">
                <button
                  type="button"
                  className="fn-btn fn-btn--destructive fn-btn--sm job-table__remove-btn"
                  onClick={() => onRemove(sf.id)}
                  aria-label={`Remove ${sf.filename}`}
                >
                  <Trash2 size={14} aria-hidden="true" />
                </button>
              </td>
            </tr>
          ))}

          {/* ── Persisted (backend-confirmed, locked) ── */}
          {persistedJobs.map((job) => (
            <tr key={job.job_id} className="job-table__row job-table__row--persisted">
              <td className="job-table__filename">
                <PdfIcon />
                <span title={job.filename}>{job.filename}</span>
              </td>
              <td className="job-table__size fn-tabular tabular-nums">{formatBytes(job.file_size_bytes)}</td>
              <td className="job-table__metric">
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    padding: '0.2rem 0.55rem',
                    borderRadius: '4px',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    background: 'var(--fn-bg-elevated)',
                    color: 'var(--fn-text-muted)',
                    border: '1px solid var(--fn-border-subtle)',
                  }}
                >
                  {WORKFLOW_PACK_LABELS[job.workflow_pack ?? 'non_gaap_bridge']}
                </span>
              </td>
              <td className="job-table__year">
                <span className="job-table__year-locked fn-tabular tabular-nums">
                  {formatFiscalPeriod(job.filename, job.filing_year)}
                </span>
              </td>
              <td className="job-table__status">
                <StatusBadge
                  status={job.status}
                  modelReady={job.model_ready}
                  modelSkipReason={job.model_skip_reason}
                />
              </td>
              <td className="job-table__remove" style={{ whiteSpace: 'nowrap' }}>
                <div style={{ display: 'flex', gap: '0.375rem', justifyContent: 'flex-end', alignItems: 'center' }}>
                  {job.status === 'done' && job.model_ready && (
                    <a
                      href={`${apiBase}/models/${job.job_id}/download`}
                      download={`${job.job_id}_model.xlsx`}
                      className="fn-btn fn-btn--secondary fn-btn--sm job-table__review-btn"
                      aria-label={`Download Excel model for ${job.filename}`}
                    >
                      <Download size={12} aria-hidden="true" />
                      <span>Excel (.xlsx)</span>
                    </a>
                  )}
                  {job.status === 'done' && onReview && (
                    <button
                      type="button"
                      className="fn-btn fn-btn--primary fn-btn--sm job-table__review-btn"
                      onClick={() => onReview(job.job_id)}
                      aria-label={`Review ${job.filename}`}
                    >
                      <FileCheck size={12} aria-hidden="true" />
                      <span>Review</span>
                    </button>
                  )}
                  {job.status === 'done' && onAuditTrail && (
                    <button
                      type="button"
                      className="fn-btn fn-btn--secondary fn-btn--sm job-table__review-btn"
                      onClick={() => onAuditTrail(job.job_id)}
                      aria-label={`Audit Trail for ${job.filename}`}
                    >
                      <History size={12} aria-hidden="true" />
                      <span>Audit Trail</span>
                    </button>
                  )}
                  {canDownloadAuditReport(job.status) && (
                    <a
                      href={buildAuditReportDownloadUrl(apiBase, job.job_id)}
                      download={buildAuditReportFilename(job.job_id)}
                      className="fn-btn fn-btn--secondary fn-btn--sm job-table__review-btn"
                      aria-label={`Export Audit Report PDF for ${job.filename}`}
                    >
                      <FileText size={12} aria-hidden="true" />
                      <span>Audit PDF</span>
                    </a>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default JobList
