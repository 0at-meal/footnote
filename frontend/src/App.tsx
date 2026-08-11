import { useState } from 'react'
import UploadZone from './components/UploadZone'
import JobList from './components/JobList'
import SubmitBar from './components/SubmitBar'
import type { StagedFile, TargetMetric } from './types/job'
import { DEFAULT_METRIC } from './types/job'
import './App.css'

function App() {
  const [stagedFiles, setStagedFiles] = useState<StagedFile[]>([])

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

  function handleSubmit() {
    // API wiring is Feature 1, Step 3.
    // At Step 1 this is intentionally a no-op stub.
    console.log(
      '[Feature 1 Step 1] Submit triggered — API wiring pending (Step 3)',
      stagedFiles.map((sf) => ({
        filename: sf.filename,
        file_size_bytes: sf.file_size_bytes,
        target_metric: sf.target_metric,
      })),
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
            {stagedFiles.length > 0 && (
              <span className="section-title__badge">{stagedFiles.length}</span>
            )}
          </h2>
          <JobList
            stagedFiles={stagedFiles}
            onMetricChange={handleMetricChange}
            onRemove={handleRemove}
          />
          <SubmitBar stagedFiles={stagedFiles} onSubmit={handleSubmit} />
        </section>
      </main>

      <footer className="app-footer">
        <p>Footnote — MVP · Single-user · Local extraction</p>
      </footer>
    </div>
  )
}

export default App
