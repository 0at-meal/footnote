import { useState, useEffect } from 'react'
import UploadZone from './components/UploadZone'
import JobList from './components/JobList'
import SubmitBar from './components/SubmitBar'
import ReviewPage from './components/review/ReviewPage'
import AuditTrailView from './components/audit/AuditTrailView'
import type { StagedFile, TargetMetric, JobRecord } from './types/job'
import { DEFAULT_METRIC } from './types/job'
import './App.css'

/** Base URL for the FastAPI backend. Change for production deployment. */
const API_BASE = 'http://localhost:8000'

function App() {
  const [stagedFiles, setStagedFiles] = useState<StagedFile[]>([])
  const [persistedJobs, setPersistedJobs] = useState<JobRecord[]>([])
  const [submissionErrors, setSubmissionErrors] = useState<string[]>([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [activeReviewJobId, setActiveReviewJobId] = useState<string | null>(null)
  const [activeAuditJobId, setActiveAuditJobId] = useState<string | null>(null)

  // ── On mount: restore persisted jobs from backend (spec AC-7) ───────────
  useEffect(() => {
    fetch(`${API_BASE}/upload/jobs`)
      .then((res) => res.json())
      .then((data: { jobs: JobRecord[] }) => {
        setPersistedJobs(data.jobs)
      })
      .catch(() => {
        // Backend unreachable on load — non-fatal; user can still stage files.
        // Errors during submit are surfaced separately.
      })
  }, [])

  // ── Auto-polling for active jobs status (spec AC-7, AC-8) ───────────────
  useEffect(() => {
    const hasActiveJobs = persistedJobs.some(
      (j) => j.status === 'queued' || j.status === 'extracting',
    )
    if (!hasActiveJobs) return

    const intervalId = setInterval(() => {
      fetch(`${API_BASE}/upload/jobs`)
        .then((res) => res.json())
        .then((data: { jobs: JobRecord[] }) => {
          setPersistedJobs(data.jobs)
        })
        .catch(() => {
          // Non-fatal background refresh error
        })
    }, 3000)

    return () => clearInterval(intervalId)
  }, [persistedJobs])

  // ── Staged file handlers ─────────────────────────────────────────────────

  function handleFilesAdded(files: File[]) {
    const newFiles: StagedFile[] = files.map((file) => ({
      id: crypto.randomUUID(),
      file,
      filename: file.name,
      file_size_bytes: file.size,
      target_metric: DEFAULT_METRIC,
    }))
    setStagedFiles((prev) => [...prev, ...newFiles])
  }

  function handleMetricChange(id: string, metric: TargetMetric) {
    setStagedFiles((prev) =>
      prev.map((sf) =>
        sf.id === id ? { ...sf, target_metric: metric } : sf,
      ),
    )
  }

  function handleRemove(id: string) {
    setStagedFiles((prev) => prev.filter((sf) => sf.id !== id))
  }

  // ── Submit handler ───────────────────────────────────────────────────────

  async function handleSubmit() {
    if (stagedFiles.length === 0) return

    setIsSubmitting(true)
    setSubmissionErrors([])

    try {
      const form = new FormData()
      for (const sf of stagedFiles) {
        form.append('files', sf.file, sf.filename)
        form.append('target_metrics', sf.target_metric)
      }

      const res = await fetch(`${API_BASE}/upload/jobs`, {
        method: 'POST',
        body: form,
      })

      if (!res.ok) {
        const detail = await res.text()
        setSubmissionErrors([`Server error ${res.status}: ${detail}`])
        return
      }

      const data: { created_jobs: JobRecord[]; rejections: { filename: string; error_message: string | null }[] } =
        await res.json()

      // Append successfully created jobs to the persisted list.
      if (data.created_jobs.length > 0) {
        setPersistedJobs((prev) => [...prev, ...data.created_jobs])
      }

      // Remove each accepted job's staged file one-for-one.
      // Must iterate the full array (not a Set) so that duplicate filenames
      // (EC-1: same name submitted twice) each consume exactly one staged entry.
      const acceptedFilenames = data.created_jobs.map((j) => j.filename)
      setStagedFiles((prev) => {
        const remaining = [...prev]
        for (const filename of acceptedFilenames) {
          const idx = remaining.findIndex((sf) => sf.filename === filename)
          if (idx !== -1) remaining.splice(idx, 1)
        }
        return remaining
      })

      // Collect per-file rejection messages for the dismissible banner.
      if (data.rejections.length > 0) {
        const errors = data.rejections.map(
          (r) => `${r.filename}: ${r.error_message ?? 'rejected'}`,
        )
        setSubmissionErrors(errors)
      }
    } catch {
      setSubmissionErrors(['Network error — could not reach the server. Is the backend running?'])
    } finally {
      setIsSubmitting(false)
    }
  }

  // ── Render ───────────────────────────────────────────────────────────────

  if (activeReviewJobId) {
    return (
      <ReviewPage
        jobId={activeReviewJobId}
        apiBase={API_BASE}
        onBack={() => setActiveReviewJobId(null)}
      />
    )
  }

  if (activeAuditJobId) {
    return (
      <AuditTrailView
        jobId={activeAuditJobId}
        apiBase={API_BASE}
        onBack={() => setActiveAuditJobId(null)}
      />
    )
  }

  return (
    <div className="app-layout">
      <header className="app-header">
        <div className="app-header__logo">
          <svg
            width="28"
            height="28"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" />
          </svg>
          <span className="app-header__wordmark">footnote</span>
        </div>
        <p className="app-header__tagline">
          Financial statement extraction &amp; model generation
        </p>
      </header>

      <main className="app-main">
        <section className="app-section" aria-labelledby="upload-heading">
          <h2 id="upload-heading" className="section-title">
            Upload Filings
          </h2>
          <p className="section-desc">
            Select one or more PDF 10-K filings to begin extraction.
          </p>
          <UploadZone onFilesAdded={handleFilesAdded} />
        </section>

        <section className="app-section" aria-labelledby="queue-heading">
          <h2 id="queue-heading" className="section-title">
            Upload Queue
            {(stagedFiles.length + persistedJobs.length) > 0 && (
              <span className="section-title__badge">
                {stagedFiles.length + persistedJobs.length}
              </span>
            )}
          </h2>

          {/* Dismissible rejection banner (spec option b) */}
          {submissionErrors.length > 0 && (
            <div
              className="submission-errors"
              role="alert"
              aria-live="assertive"
            >
              <div className="submission-errors__header">
                <strong>
                  {submissionErrors.length === 1
                    ? '1 file was rejected'
                    : `${submissionErrors.length} files were rejected`}
                </strong>
                <button
                  type="button"
                  className="submission-errors__dismiss"
                  onClick={() => setSubmissionErrors([])}
                  aria-label="Dismiss rejection errors"
                >
                  ✕
                </button>
              </div>
              <ul className="submission-errors__list">
                {submissionErrors.map((msg, i) => (
                  <li key={i}>{msg}</li>
                ))}
              </ul>
            </div>
          )}

          <JobList
            stagedFiles={stagedFiles}
            persistedJobs={persistedJobs}
            onMetricChange={handleMetricChange}
            onRemove={handleRemove}
            onReview={(jobId) => setActiveReviewJobId(jobId)}
            onAuditTrail={(jobId) => setActiveAuditJobId(jobId)}
          />
          <SubmitBar
            stagedFiles={stagedFiles}
            onSubmit={() => void handleSubmit()}
            isSubmitting={isSubmitting}
          />
        </section>
      </main>

      <footer className="app-footer">
        <p>Footnote — MVP · Single-user · Local extraction</p>
      </footer>
    </div>
  )
}

export default App
