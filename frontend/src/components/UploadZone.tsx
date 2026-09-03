import { useState, useRef } from 'react'
import type { DragEvent, ChangeEvent } from 'react'
import type { RejectedFile, WorkflowPack } from '../types/job'
import { isPdf } from '../lib/validation'

export const WORKFLOW_PACK_DETAILS: {
  id: WorkflowPack
  title: string
  subtitle: string
  icon: string
}[] = [
  {
    id: 'non_gaap_bridge',
    title: 'Earnings Quality / Non-GAAP Bridge',
    subtitle: 'Adjusted EBITDA, Non-GAAP Net Income, Free Cash Flow bridges',
    icon: '📊',
  },
  {
    id: 'capital_structure',
    title: 'Capital Structure & Debt Sizing',
    subtitle: 'Note 8 debt tranches, interest rates, maturities, ASC 842 leases',
    icon: '🏛️',
  },
  {
    id: 'cash_conversion',
    title: 'Valuation & Cash Conversion',
    subtitle: 'Operating Cash Flow, CapEx, Working Capital normalization',
    icon: '📈',
  },
]

interface Props {
  onFilesAdded: (files: File[]) => void
  selectedWorkflowPack?: WorkflowPack
  onSelectWorkflowPack?: (pack: WorkflowPack) => void
}

function UploadZone({
  onFilesAdded,
  selectedWorkflowPack = 'non_gaap_bridge',
  onSelectWorkflowPack,
}: Props) {
  const [internalPack, setInternalPack] = useState<WorkflowPack>(selectedWorkflowPack)
  const [isDragOver, setIsDragOver] = useState(false)
  const [rejections, setRejections] = useState<RejectedFile[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  const activePack = onSelectWorkflowPack ? selectedWorkflowPack : internalPack

  function handlePackChange(pack: WorkflowPack) {
    if (onSelectWorkflowPack) {
      onSelectWorkflowPack(pack)
    } else {
      setInternalPack(pack)
    }
  }

  function processFiles(fileList: FileList | File[]) {
    const files = Array.from(fileList)
    const accepted: File[] = []
    const rejected: RejectedFile[] = []

    for (const file of files) {
      if (isPdf(file)) {
        accepted.push(file)
      } else {
        rejected.push({ filename: file.name, reason: 'unsupported file type' })
      }
    }

    setRejections(rejected)
    if (accepted.length > 0) {
      onFilesAdded(accepted)
    }
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setIsDragOver(false)
    processFiles(e.dataTransfer.files)
  }

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setIsDragOver(true)
  }

  function handleDragEnter(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setIsDragOver(true)
  }

  function handleDragLeave(e: DragEvent<HTMLDivElement>) {
    const leaving = e.relatedTarget
    if (leaving instanceof Node && e.currentTarget.contains(leaving)) return
    setIsDragOver(false)
  }

  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    if (e.target.files && e.target.files.length > 0) {
      processFiles(e.target.files)
      e.target.value = ''
    }
  }

  function handleBrowseClick() {
    inputRef.current?.click()
  }

  return (
    <div className="upload-section">
      <div className="workflow-packs-selector" style={{ marginBottom: '1.25rem' }}>
        <div style={{ marginBottom: '0.5rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <label style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text, #f8fafc)' }}>
            Select Targeted Workflow Pack
          </label>
          <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
            Routes ingestion parser and model generator
          </span>
        </div>
        <div
          role="radiogroup"
          aria-label="Workflow Pack Options"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: '0.75rem',
          }}
        >
          {WORKFLOW_PACK_DETAILS.map((pack) => {
            const isSelected = activePack === pack.id
            return (
              <div
                key={pack.id}
                role="radio"
                aria-checked={isSelected}
                tabIndex={0}
                onClick={() => handlePackChange(pack.id)}
                onKeyDown={(e) => {
                  if (e.key === ' ' || e.key === 'Enter') {
                    e.preventDefault()
                    handlePackChange(pack.id)
                  }
                }}
                style={{
                  padding: '0.75rem 1rem',
                  borderRadius: '6px',
                  border: isSelected ? '2px solid #2563eb' : '1px solid #334155',
                  backgroundColor: isSelected ? 'rgba(37, 99, 235, 0.12)' : 'var(--surface, #1e293b)',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.25rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span style={{ fontSize: '1.1rem' }}>{pack.icon}</span>
                  <span style={{ fontWeight: 600, fontSize: '0.85rem', color: isSelected ? '#38bdf8' : '#e2e8f0' }}>
                    {pack.title}
                  </span>
                </div>
                <span style={{ fontSize: '0.75rem', color: '#94a3b8', lineHeight: 1.3 }}>
                  {pack.subtitle}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      <div
        className={`upload-zone${isDragOver ? ' upload-zone--drag-over' : ''}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        aria-label="PDF upload area"
      >
        <svg
          className="upload-zone__icon"
          width="48"
          height="48"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M12 15V3m0 0L8.5 6.5M12 3l3.5 3.5" />
          <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3" />
        </svg>

        <p className="upload-zone__headline">
          {isDragOver ? 'Release to add files' : 'Drag & drop PDF files here'}
        </p>
        <p className="upload-zone__sub">or</p>

        <button
          type="button"
          className="upload-zone__browse-btn"
          onClick={handleBrowseClick}
        >
          Browse files
        </button>

        <input
          ref={inputRef}
          id="file-input"
          type="file"
          accept=".pdf,application/pdf"
          multiple
          onChange={handleChange}
          style={{ display: 'none' }}
          aria-label="Select PDF files"
        />

        <p className="upload-zone__hint">PDF only · Max 100 MB per file</p>

        {rejections.length > 0 && (
          <ul
            className="upload-zone__rejections"
            role="alert"
            aria-live="assertive"
          >
            {rejections.map((r, i) => (
              <li key={i} className="upload-zone__rejection-item">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 8v4m0 4h.01" />
                </svg>
                <span>
                  <strong>{r.filename}</strong> — {r.reason}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

export default UploadZone

