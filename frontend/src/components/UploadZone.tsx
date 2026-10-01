import { useState, useRef, type DragEvent, type ChangeEvent, type ReactNode } from 'react'
import { TrendingUp, PieChart, UploadCloud, AlertCircle } from 'lucide-react'
import type { RejectedFile, WorkflowPack } from '../types/job'
import { isPdf } from '../lib/validation'

const WORKFLOW_PACK_DETAILS: {
  id: WorkflowPack
  title: string
  subtitle: string
  icon: ReactNode
  disabled?: boolean
  badge?: string
}[] = [
  {
    id: 'non_gaap_bridge',
    title: 'Earnings Quality / Non-GAAP Bridge',
    subtitle: 'Adjusted EBITDA, Non-GAAP Net Income, Free Cash Flow bridges',
    icon: <TrendingUp size={16} aria-hidden="true" />,
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
    icon: <PieChart size={16} aria-hidden="true" />,
    disabled: true,
    badge: 'Coming Soon',
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
            const isDisabled = Boolean(pack.disabled)
            return (
              <div
                key={pack.id}
                role="radio"
                aria-checked={isSelected}
                aria-disabled={isDisabled}
                tabIndex={isDisabled ? -1 : 0}
                onClick={() => !isDisabled && handlePackChange(pack.id)}
                onKeyDown={(e) => {
                  if (!isDisabled && (e.key === ' ' || e.key === 'Enter')) {
                    e.preventDefault()
                    handlePackChange(pack.id)
                  }
                }}
                style={{
                  padding: '0.75rem 1rem',
                  borderRadius: 'var(--fn-radius-md)',
                  border: isSelected ? '1px solid var(--fn-border-accent)' : '1px solid var(--fn-border-subtle)',
                  backgroundColor: isSelected ? 'var(--fn-accent-bg)' : 'var(--fn-bg-surface)',
                  cursor: isDisabled ? 'not-allowed' : 'pointer',
                  opacity: isDisabled ? 0.55 : 1,
                  transition: 'all 0.15s ease',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.25rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{ fontSize: '1.1rem' }}>{pack.icon}</span>
                    <span style={{ fontWeight: 600, fontSize: '0.85rem', color: isSelected ? 'var(--fn-accent-text)' : 'var(--fn-text-primary)' }}>
                      {pack.title}
                    </span>
                  </div>
                  {pack.badge && (
                    <span
                      style={{
                        fontSize: '0.65rem',
                        fontWeight: 600,
                        padding: '2px 6px',
                        borderRadius: '4px',
                        background: 'var(--fn-bg-elevated)',
                        color: 'var(--fn-text-muted)',
                        textTransform: 'uppercase',
                        letterSpacing: '0.5px',
                      }}
                    >
                      {pack.badge}
                    </span>
                  )}
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
        <UploadCloud className="upload-zone__icon" size={40} aria-hidden="true" />

        <p className="upload-zone__headline">
          {isDragOver ? 'Release to add files' : 'Drag & drop PDF files here'}
        </p>
        <p className="upload-zone__sub">or</p>

        <button
          type="button"
          className="fn-btn fn-btn--secondary fn-btn--md upload-zone__browse-btn"
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
                <AlertCircle size={14} aria-hidden="true" />
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

