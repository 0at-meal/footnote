import { useState } from 'react'
import type { StagedFile, TargetMetric, JobRecord, JobStatus } from '../types/job'
import { WORKFLOW_PACK_LABELS } from '../types/job'
import { buildAuditReportDownloadUrl, buildAuditReportFilename, canDownloadAuditReport } from '../lib/audit_report'
import { Download, FileCheck, History, Trash2, FileText, Info, MoreHorizontal, CheckCircle2 } from 'lucide-react'
import { formatFiscalPeriod } from '../lib/fiscal_period'
import { EmptyState } from './brand/EmptyState'

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

function StatusStepper({
  status,
  modelReady,
  modelSkipReason,
}: {
  status: JobStatus
  modelReady?: boolean
  modelSkipReason?: string | null
}) {
  const steps = ['Parsing', 'Classifying', 'Checks', 'Ready']

  let currentStepIdx = 0
  if (status === 'queued') currentStepIdx = 0
  else if (status === 'extracting') currentStepIdx = 1
  else if (status === 'done') {
    currentStepIdx = modelReady ? 4 : 3
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      {/* ── Status Text / Badge ── */}
      <div>
        {status === 'done' ? (
          modelReady ? (
            <span
              className="status-badge status-badge--done status-badge--model-ready"
              aria-label="Status: Model Ready"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                fontWeight: 600,
                fontSize: '11px',
                padding: '2px 8px',
                borderRadius: '4px',
                background: 'rgba(31, 138, 91, 0.12)',
                color: 'var(--ok)',
                border: '1px solid var(--ok)',
              }}
            >
              <CheckCircle2 size={12} aria-hidden="true" />
              Model Ready
            </span>
          ) : (
            <span
              className="status-badge status-badge--awaiting-review"
              aria-label="Status: Awaiting Review"
              title={modelSkipReason || 'No auto-accepted records — review and confirm items to generate model.'}
              style={{
                cursor: 'help',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                fontSize: '11px',
                padding: '2px 8px',
                borderRadius: '4px',
                background: 'rgba(183, 121, 31, 0.12)',
                color: 'var(--warn)',
                border: '1px solid var(--warn)',
              }}
            >
              Awaiting Review
              <Info size={12} style={{ opacity: 0.8 }} aria-hidden="true" />
            </span>
          )
        ) : status === 'extracting' ? (
          <span
            className="status-badge status-badge--extracting"
            aria-label="Status: Extracting"
            title="Processing PDF — this may take 30–60 seconds for large documents"
            style={{
              cursor: 'wait',
              fontSize: '11px',
              padding: '2px 8px',
              borderRadius: '4px',
              background: 'rgba(43, 75, 238, 0.12)',
              color: 'var(--accent)',
            }}
          >
            Extracting
          </span>
        ) : (
          <span
            className={`status-badge status-badge--${status}`}
            aria-label={`Status: ${status}`}
            style={{
              fontSize: '11px',
              padding: '2px 8px',
              borderRadius: '4px',
              background: 'var(--surface-2)',
              color: 'var(--ink-secondary)',
            }}
          >
            {status === 'queued' ? 'Queued' : status}
          </span>
        )}
      </div>

      {/* ── Stepper Indicator: Parsing -> Classifying -> Checks -> Ready ── */}
      <div
        className="fn-stepper"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
          marginTop: '2px',
        }}
        aria-label="Pipeline progress stepper"
      >
        {steps.map((st, i) => {
          const isDone = i < currentStepIdx
          const isCurrent = i === currentStepIdx && status !== 'done' && status !== 'failed'
          return (
            <div
              key={st}
              title={`Stage ${i + 1}: ${st}`}
              style={{
                height: '4px',
                width: '18px',
                borderRadius: '2px',
                backgroundColor: isDone
                  ? 'var(--ok)'
                  : isCurrent
                    ? 'var(--accent)'
                    : 'var(--border)',
                transition: 'background-color var(--fn-motion-state)',
              }}
            />
          )
        })}
      </div>
    </div>
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
      style={{ color: 'var(--accent)', flexShrink: 0 }}
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
  const [openOverflowJobId, setOpenOverflowJobId] = useState<string | null>(null)

  const hasStaged = stagedFiles.length > 0
  const hasPersisted = persistedJobs.length > 0
  const isEmpty = !hasStaged && !hasPersisted

  if (isEmpty) {
    return (
      <div className="job-list job-list--empty" style={{ margin: '1.5rem 0' }}>
        <EmptyState
          variant="no-filings"
          title="No filings in processing queue"
          description="Drag and drop or select SEC 10-K or 10-Q filing PDFs above to begin extraction."
        />
      </div>
    )
  }

  return (
    <div className="job-list" style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      {/* ── 1. Staging Queue: Files About to Submit ── */}
      {hasStaged && (
        <div className="job-queue-staging">
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '0.75rem',
            }}
          >
            <h3
              style={{
                margin: 0,
                fontSize: '0.95rem',
                fontWeight: 600,
                color: 'var(--ink)',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <span>Staged Filings</span>
              <span
                style={{
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  padding: '2px 7px',
                  borderRadius: '10px',
                  backgroundColor: 'rgba(43, 75, 238, 0.1)',
                  color: 'var(--accent)',
                }}
              >
                {stagedFiles.length}
              </span>
            </h3>
            <span style={{ fontSize: '0.75rem', color: 'var(--ink-muted)' }}>
              Configure period before submission
            </span>
          </div>

          <div
            style={{
              border: '1px solid var(--border)',
              borderRadius: 'var(--fn-radius-md)',
              overflowX: 'auto',
              backgroundColor: 'var(--surface)',
              boxShadow: 'var(--fn-shadow-sm)',
            }}
          >
            <table className="job-table" aria-label="Upload queue" style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ backgroundColor: 'var(--surface-2)', borderBottom: '1px solid var(--border)', fontSize: '11px', color: 'var(--ink-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  <th scope="col" style={{ padding: '8px 12px', textAlign: 'left' }}>File</th>
                  <th scope="col" style={{ padding: '8px 12px', textAlign: 'left' }}>Workflow Pack</th>
                  <th scope="col" style={{ padding: '8px 12px', textAlign: 'left' }}>Fiscal Year</th>
                  <th scope="col" style={{ padding: '8px 12px', textAlign: 'left' }}>Status</th>
                  <th scope="col" style={{ padding: '8px 12px', textAlign: 'right' }}>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {stagedFiles.map((sf) => (
                  <tr key={sf.id} className="job-table__row job-table__row--staged" style={{ borderBottom: '1px solid var(--border)' }}>
                    <td className="job-table__filename" style={{ padding: '10px 12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <PdfIcon />
                        <span title={sf.filename} style={{ fontWeight: 500, color: 'var(--ink)' }}>
                          {sf.filename}
                        </span>
                      </div>
                    </td>
                    <td className="job-table__metric" style={{ padding: '10px 12px' }}>
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          padding: '0.2rem 0.55rem',
                          borderRadius: '4px',
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          background: 'rgba(43, 75, 238, 0.08)',
                          color: 'var(--accent)',
                          border: '1px solid var(--border)',
                        }}
                      >
                        {WORKFLOW_PACK_LABELS[sf.workflow_pack ?? 'non_gaap_bridge']}
                      </span>
                    </td>
                    <td className="job-table__year" style={{ padding: '10px 12px' }}>
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
                          width: '90px',
                          padding: '0.3rem 0.5rem',
                          fontSize: '0.8125rem',
                          borderRadius: 'var(--fn-radius-sm)',
                          border: '1px solid var(--border)',
                          background: 'var(--surface-2)',
                          color: 'var(--ink)',
                        }}
                      />
                    </td>
                    <td className="job-table__status" style={{ padding: '10px 12px' }}>
                      <span
                        className="status-badge status-badge--pending"
                        style={{
                          fontSize: '11px',
                          padding: '2px 8px',
                          borderRadius: '4px',
                          background: 'var(--surface-2)',
                          color: 'var(--ink-secondary)',
                        }}
                      >
                        Pending
                      </span>
                    </td>
                    <td className="job-table__remove" style={{ padding: '10px 12px', textAlign: 'right' }}>
                      <button
                        type="button"
                        className="fn-btn fn-btn--destructive fn-btn--sm job-table__remove-btn"
                        onClick={() => onRemove(sf.id)}
                        aria-label={`Remove ${sf.filename}`}
                        style={{
                          padding: '4px 8px',
                          borderRadius: 'var(--fn-radius-sm)',
                          border: '1px solid var(--border)',
                          background: 'transparent',
                          color: 'var(--danger)',
                          cursor: 'pointer',
                        }}
                      >
                        <Trash2 size={14} aria-hidden="true" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── 2. Results & History Queue: Completed/Running Filings ── */}
      {hasPersisted && (
        <div className="job-queue-persisted">
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '0.75rem',
            }}
          >
            <h3
              style={{
                margin: 0,
                fontSize: '0.95rem',
                fontWeight: 600,
                color: 'var(--ink)',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <span>Results & History</span>
              <span
                style={{
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  padding: '2px 7px',
                  borderRadius: '10px',
                  backgroundColor: 'var(--surface-2)',
                  color: 'var(--ink-secondary)',
                }}
              >
                {persistedJobs.length}
              </span>
            </h3>
          </div>

          <div
            style={{
              border: '1px solid var(--border)',
              borderRadius: 'var(--fn-radius-md)',
              overflowX: 'auto',
              backgroundColor: 'var(--surface)',
              boxShadow: 'var(--fn-shadow-sm)',
            }}
          >
            <table className="job-table" aria-label="Upload queue" style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ backgroundColor: 'var(--surface-2)', borderBottom: '1px solid var(--border)', fontSize: '11px', color: 'var(--ink-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  <th scope="col" style={{ padding: '8px 12px', textAlign: 'left' }}>File</th>
                  <th scope="col" style={{ padding: '8px 12px', textAlign: 'left' }}>Workflow Pack</th>
                  <th scope="col" style={{ padding: '8px 12px', textAlign: 'left' }}>Fiscal Year</th>
                  <th scope="col" style={{ padding: '8px 12px', textAlign: 'left' }}>Status</th>
                  <th scope="col" style={{ padding: '8px 12px', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {persistedJobs.map((job) => {
                  const isDone = job.status === 'done'
                  const isOverflowOpen = openOverflowJobId === job.job_id

                  return (
                    <tr key={job.job_id} className="job-table__row job-table__row--persisted" style={{ borderBottom: '1px solid var(--border)' }}>
                      <td className="job-table__filename" style={{ padding: '10px 12px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <PdfIcon />
                          <span title={job.filename} style={{ fontWeight: 500, color: 'var(--ink)' }}>
                            {job.filename}
                          </span>
                        </div>
                      </td>
                      <td className="job-table__metric" style={{ padding: '10px 12px' }}>
                        <span
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            padding: '0.2rem 0.55rem',
                            borderRadius: '4px',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            background: 'var(--surface-2)',
                            color: 'var(--ink-secondary)',
                            border: '1px solid var(--border)',
                          }}
                        >
                          {WORKFLOW_PACK_LABELS[job.workflow_pack ?? 'non_gaap_bridge']}
                        </span>
                      </td>
                      <td className="job-table__year" style={{ padding: '10px 12px' }}>
                        <span className="job-table__year-locked fn-tabular tabular-nums" style={{ color: 'var(--ink)' }}>
                          {formatFiscalPeriod(job.filename, job.filing_year)}
                        </span>
                      </td>
                      <td className="job-table__status" style={{ padding: '10px 12px' }}>
                        <StatusStepper
                          status={job.status}
                          modelReady={job.model_ready}
                          modelSkipReason={job.model_skip_reason}
                        />
                      </td>
                      <td className="job-table__remove" style={{ padding: '10px 12px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                        <div style={{ display: 'inline-flex', gap: '6px', alignItems: 'center', position: 'relative' }}>
                          {/* Primary Action: Open workbook / Excel Download */}
                          {isDone && job.model_ready && (
                            <a
                              href={`${apiBase}/models/${job.job_id}/download`}
                              download={`${job.job_id}_model.xlsx`}
                              className="fn-btn fn-btn--primary fn-btn--sm job-table__review-btn"
                              aria-label={`Download Excel model for ${job.filename}`}
                              style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                            >
                              <Download size={13} aria-hidden="true" />
                              <span>Excel (.xlsx)</span>
                            </a>
                          )}

                          {/* Secondary / Review Action */}
                          {isDone && onReview && (
                            <button
                              type="button"
                              className="fn-btn fn-btn--secondary fn-btn--sm job-table__review-btn"
                              onClick={() => onReview(job.job_id)}
                              aria-label={`Review ${job.filename}`}
                              style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                            >
                              <FileCheck size={13} aria-hidden="true" />
                              <span>Review</span>
                            </button>
                          )}

                          {/* Overflow Menu Button */}
                          {isDone && (
                            <div style={{ position: 'relative' }}>
                              <button
                                type="button"
                                className="fn-btn fn-btn--ghost fn-btn--sm"
                                onClick={() => setOpenOverflowJobId(isOverflowOpen ? null : job.job_id)}
                                aria-label="More actions"
                                style={{ padding: '4px' }}
                              >
                                <MoreHorizontal size={15} aria-hidden="true" />
                              </button>

                              {/* Overflow dropdown */}
                              {isOverflowOpen && (
                                <div
                                  style={{
                                    position: 'absolute',
                                    right: 0,
                                    top: '100%',
                                    marginTop: '4px',
                                    backgroundColor: 'var(--surface)',
                                    border: '1px solid var(--border)',
                                    borderRadius: 'var(--fn-radius-md)',
                                    boxShadow: 'var(--fn-shadow-md)',
                                    zIndex: 10,
                                    minWidth: '150px',
                                    padding: '4px',
                                    display: 'flex',
                                    flexDirection: 'column',
                                    gap: '2px',
                                  }}
                                >
                                  {onAuditTrail && (
                                    <button
                                      type="button"
                                      className="fn-btn fn-btn--ghost fn-btn--sm job-table__review-btn"
                                      onClick={() => {
                                        setOpenOverflowJobId(null)
                                        onAuditTrail(job.job_id)
                                      }}
                                      aria-label={`Audit Trail for ${job.filename}`}
                                      style={{ justifyContent: 'flex-start', width: '100%', gap: '6px' }}
                                    >
                                      <History size={13} aria-hidden="true" />
                                      <span>Audit Trail</span>
                                    </button>
                                  )}
                                  {canDownloadAuditReport(job.status) && (
                                    <a
                                      href={buildAuditReportDownloadUrl(apiBase, job.job_id)}
                                      download={buildAuditReportFilename(job.job_id)}
                                      className="fn-btn fn-btn--ghost fn-btn--sm job-table__review-btn"
                                      aria-label={`Export Audit Report PDF for ${job.filename}`}
                                      style={{ justifyContent: 'flex-start', width: '100%', gap: '6px', textDecoration: 'none' }}
                                      onClick={() => setOpenOverflowJobId(null)}
                                    >
                                      <FileText size={13} aria-hidden="true" />
                                      <span>Audit PDF</span>
                                    </a>
                                  )}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

export default JobList
