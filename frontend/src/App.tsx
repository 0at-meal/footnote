import { useState, useEffect, lazy, Suspense } from 'react'
import UploadZone from './components/UploadZone'
import JobList from './components/JobList'
import SubmitBar from './components/SubmitBar'
import ReviewPage from './components/review/ReviewPage'
import AuditTrailView from './components/audit/AuditTrailView'
import CompanySelector from './components/CompanySelector'
import CompanyMultiYearCard from './components/CompanyMultiYearCard'
import type {
  StagedFile,
  JobRecord,
  CompanyWithJobs,
  WorkflowPack,
  HealthStatus,
} from './types/job'
import { DEFAULT_METRIC } from './types/job'
import { X, Search } from 'lucide-react'
import { AppShell } from './components/shell/AppShell'
import { Wordmark } from './components/brand/Wordmark'
import { CommandPalette } from './components/search/CommandPalette'
import './App.css'

/**
 * Design-system showcase: dev builds only (FN-061, D7). In production builds
 * `import.meta.env.DEV` is the literal `false`, so this lazy import is removed from the bundle.
 */
const DesignPreviewPage = import.meta.env.DEV
  ? lazy(() =>
      import('./components/design/DesignPreviewPage').then((m) => ({ default: m.DesignPreviewPage })),
    )
  : null

function isDesignPath(): boolean {
  return (
    import.meta.env.DEV &&
    typeof window !== 'undefined' &&
    (window.location.pathname === '/design' || window.location.hash === '#/design')
  )
}

/** Base URL for the FastAPI backend. Change for production deployment. */
const API_BASE = 'http://localhost:8000'

function App() {
  const [stagedFiles, setStagedFiles] = useState<StagedFile[]>([])
  const [persistedJobs, setPersistedJobs] = useState<JobRecord[]>([])
  const [submissionErrors, setSubmissionErrors] = useState<string[]>([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [selectedWorkflowPack, setSelectedWorkflowPack] = useState<WorkflowPack>('non_gaap_bridge')
  const [activeReviewJobId, setActiveReviewJobId] = useState<string | null>(null)
  const [activeAuditJobId, setActiveAuditJobId] = useState<string | null>(null)
  const [selectedCompany, setSelectedCompany] = useState<string>('')
  const [companies, setCompanies] = useState<CompanyWithJobs[]>([])
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false)
  const [serviceWarning, setServiceWarning] = useState<string | null>(null)
  const [currentRoute, setCurrentRoute] = useState<'app' | 'design'>(() =>
    isDesignPath() ? 'design' : 'app',
  )

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setIsCommandPaletteOpen((prev) => !prev)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  useEffect(() => {
    const onPopState = () => {
      setCurrentRoute(isDesignPath() ? 'design' : 'app')
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  function handleNavigate(route: 'app' | 'design') {
    if (route === 'design' && !import.meta.env.DEV) return
    setCurrentRoute(route)
    if (route === 'design') {
      window.history.pushState(null, '', '/design')
    } else {
      window.history.pushState(null, '', '/')
    }
  }

  function refreshCompanies() {
    fetch(`${API_BASE}/companies`)
      .then((res) => res.json())
      .then((data: CompanyWithJobs[]) => {
        if (Array.isArray(data)) {
          setCompanies(data)
        }
      })
      .catch(() => {
        // Non-fatal if backend is offline
      })
  }

  // ── On mount: degraded-parser check (D1) ─────────────────────────────────
  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((res) => res.json())
      .then((data: HealthStatus) => {
        if (data.status === 'degraded') {
          setServiceWarning(data.degraded_reason || 'The backend reports a degraded state.')
        }
      })
      .catch(() => {
        // Backend offline is reported by the queue fetch below.
      })
  }, [])

  // ── On mount: restore persisted jobs and companies from backend ─────────
  useEffect(() => {
    fetch(`${API_BASE}/upload/jobs`)
      .then((res) => res.json())
      .then((data: { jobs: JobRecord[] }) => {
        setPersistedJobs(data.jobs)
      })
      .catch(() => {
        // Backend unreachable on load — non-fatal; user can still stage files.
      })

    refreshCompanies()
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
      refreshCompanies()
    }, 3000)

    return () => clearInterval(intervalId)
  }, [persistedJobs])

  // ── Staged file handlers ─────────────────────────────────────────────────

  function handleFilesAdded(files: File[]) {
    const existingStaged = new Set(stagedFiles.map((sf) => `${sf.filename}_${sf.file_size_bytes}`))
    const existingPersisted = new Set(persistedJobs.map((j) => `${j.filename}_${j.file_size_bytes}`))

    const newFiles: StagedFile[] = []
    const duplicateNames: string[] = []

    for (const file of files) {
      const fileKey = `${file.name}_${file.size}`
      if (existingStaged.has(fileKey) || existingPersisted.has(fileKey)) {
        duplicateNames.push(file.name)
        continue
      }
      existingStaged.add(fileKey)
      newFiles.push({
        id: crypto.randomUUID(),
        file,
        filename: file.name,
        file_size_bytes: file.size,
        target_metric: selectedWorkflowPack === 'capital_structure' ? 'Capital Structure' : DEFAULT_METRIC,
        filing_year: null,
        workflow_pack: selectedWorkflowPack,
      })
    }

    if (duplicateNames.length > 0) {
      setSubmissionErrors((prev) => [
        ...prev,
        duplicateNames.length === 1
          ? `Duplicate file skipped: "${duplicateNames[0]}" is already in the queue or processed.`
          : `Duplicate files skipped: ${duplicateNames.map((n) => `"${n}"`).join(', ')} already in queue or processed.`,
      ])
    }

    if (newFiles.length > 0) {
      setStagedFiles((prev) => [...prev, ...newFiles])
    }
  }



  function handleYearChange(id: string, year: number | null) {
    setStagedFiles((prev) =>
      prev.map((sf) =>
        sf.id === id ? { ...sf, filing_year: year } : sf,
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
      if (selectedCompany.trim().length > 0) {
        form.append('company_name', selectedCompany.trim())
      }

      for (const sf of stagedFiles) {
        form.append('files', sf.file, sf.filename)
        form.append('target_metrics', sf.target_metric)
        form.append('filing_years', sf.filing_year ? String(sf.filing_year) : '')
        form.append('workflow_packs', sf.workflow_pack ?? selectedWorkflowPack)
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

  if (currentRoute === 'design' && DesignPreviewPage) {
    return (
      <AppShell
        serviceWarning={serviceWarning}
        currentRoute="design"
        onNavigate={handleNavigate}
        showDesignLink={import.meta.env.DEV}
        breadcrumbs={[
          { label: 'Home', onClick: () => handleNavigate('app') },
          { label: 'Design System (/design)', active: true },
        ]}
      >
        <Suspense fallback={null}>
          <DesignPreviewPage />
        </Suspense>
      </AppShell>
    )
  }

  if (activeReviewJobId) {
    const activeJob = persistedJobs.find((j) => j.job_id === activeReviewJobId)
    return (
      <AppShell
        serviceWarning={serviceWarning}
        currentRoute="app"
        onNavigate={handleNavigate}
        showDesignLink={import.meta.env.DEV}
        breadcrumbs={[
          { label: 'Home', onClick: () => setActiveReviewJobId(null) },
          { label: `Review: ${activeJob?.filename || activeReviewJobId}`, active: true },
        ]}
      >
        <ReviewPage
          jobId={activeReviewJobId}
          apiBase={API_BASE}
          onBack={() => setActiveReviewJobId(null)}
          onAuditTrail={(jobId) => {
            setActiveReviewJobId(null)
            setActiveAuditJobId(jobId)
          }}
        />
      </AppShell>
    )
  }

  if (activeAuditJobId) {
    const activeAuditJob = persistedJobs.find((j) => j.job_id === activeAuditJobId)
    return (
      <AppShell
        serviceWarning={serviceWarning}
        currentRoute="app"
        onNavigate={handleNavigate}
        showDesignLink={import.meta.env.DEV}
        breadcrumbs={[
          { label: 'Home', onClick: () => setActiveAuditJobId(null) },
          { label: `Audit Trail: ${activeAuditJob?.filename || activeAuditJobId}`, active: true },
        ]}
      >
        <AuditTrailView
          jobId={activeAuditJobId}
          apiBase={API_BASE}
          onBack={() => setActiveAuditJobId(null)}
          onReview={(jobId) => {
            setActiveAuditJobId(null)
            setActiveReviewJobId(jobId)
          }}
          jobRecord={activeAuditJob}
          modelReady={activeAuditJob?.model_ready}
        />
      </AppShell>
    )
  }

  // ── Active selected company resolution for Multi-Year Model ─────────────
  const activeCompany = companies.find(
    (c) =>
      c.name.toLowerCase() === selectedCompany.trim().toLowerCase() ||
      c.company_id === selectedCompany.trim(),
  )
  const activeCompanyWithLatestJobs: CompanyWithJobs | null = activeCompany
    ? {
        ...activeCompany,
        jobs: persistedJobs.filter(
          (j) => j.company_id === activeCompany.company_id,
        ),
      }
    : null

  return (
    <AppShell
        serviceWarning={serviceWarning}
      currentRoute="app"
      onNavigate={handleNavigate}
        showDesignLink={import.meta.env.DEV}
      breadcrumbs={[{ label: 'Upload & Queue', active: true }]}
    >
      <div className="app-layout">
        <header className="app-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div className="app-header__logo">
              <Wordmark size="md" />
            </div>
            <p className="app-header__tagline">
              Financial statement extraction &amp; model generation
            </p>
          </div>

          {/* ⌘K Command Palette / Ticker Search Trigger */}
          <button
            type="button"
            onClick={() => setIsCommandPaletteOpen(true)}
            aria-label="Open command palette (⌘K)"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '6px 14px',
              borderRadius: 'var(--fn-radius-md)',
              border: '1px solid var(--border)',
              background: 'var(--surface)',
              color: 'var(--ink-muted)',
              fontSize: '0.8125rem',
              cursor: 'pointer',
              boxShadow: 'var(--fn-shadow-sm)',
            }}
          >
            <Search size={14} aria-hidden="true" style={{ color: 'var(--accent)' }} />
            <span>Search filings or companies...</span>
            <kbd
              style={{
                fontSize: '10px',
                padding: '2px 5px',
                borderRadius: '3px',
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                fontWeight: 600,
                color: 'var(--ink-secondary)',
              }}
            >
              ⌘K
            </kbd>
          </button>
        </header>

        <CommandPalette
          isOpen={isCommandPaletteOpen}
          onClose={() => setIsCommandPaletteOpen(false)}
          companies={companies}
          onSelectCompany={(companyName) => setSelectedCompany(companyName)}
          onUploadClick={() => {
            const input = document.getElementById('file-input')
            input?.click()
          }}
        />

      <main className="app-main">
        <section className="app-section" aria-labelledby="upload-heading">
          <UploadZone
            onFilesAdded={handleFilesAdded}
            selectedWorkflowPack={selectedWorkflowPack}
            onSelectWorkflowPack={setSelectedWorkflowPack}
          />
        </section>

        <section className="app-section" aria-labelledby="queue-heading">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2 id="queue-heading" className="section-title" style={{ margin: 0 }}>
              Filing Queue
              {(stagedFiles.length + persistedJobs.length) > 0 && (
                <span className="section-title__badge">
                  {stagedFiles.length + persistedJobs.length}
                </span>
              )}
            </h2>
          </div>

          {/* Assign to Company selector */}
          <CompanySelector
            selectedCompany={selectedCompany}
            onCompanyChange={setSelectedCompany}
            apiBase={API_BASE}
          />

          {/* Multi-Year Model Generation Card */}
          {activeCompanyWithLatestJobs && (
            <CompanyMultiYearCard
              company={activeCompanyWithLatestJobs}
              apiBase={API_BASE}
            />
          )}

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
                  className="submission-errors__dismiss fn-btn fn-btn--ghost fn-btn--sm"
                  onClick={() => setSubmissionErrors([])}
                  aria-label="Dismiss rejection errors"
                >
                  <X size={14} aria-hidden="true" />
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
            apiBase={API_BASE}
            onYearChange={handleYearChange}
            onRemove={handleRemove}
            onReview={(jobId) => setActiveReviewJobId(jobId)}
            onAuditTrail={(jobId) => setActiveAuditJobId(jobId)}
          />

          {/* Submit button only rendered when staged files are present */}
          {stagedFiles.length > 0 && (
            <SubmitBar
              stagedFiles={stagedFiles}
              onSubmit={() => void handleSubmit()}
              isSubmitting={isSubmitting}
            />
          )}
        </section>
      </main>

      <footer className="app-footer">
        <p>Footnote © 2026</p>
      </footer>
    </div>
  </AppShell>
  )
}

export default App
