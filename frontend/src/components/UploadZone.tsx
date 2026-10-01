import { useState, useRef, type DragEvent, type ChangeEvent, type ReactNode } from 'react'
import { TrendingUp, CreditCard, PieChart, UploadCloud, AlertCircle, Check, Sparkles } from 'lucide-react'
import type { RejectedFile, WorkflowPack } from '../types/job'
import { isPdf } from '../lib/validation'

interface WorkflowPackConfig {
  id: WorkflowPack
  title: string
  subtitle: string
  icon: ReactNode
  disabled?: boolean
  isComingSoon?: boolean
  thumbnailLines: string[]
}

const WORKFLOW_PACK_CONFIGS: WorkflowPackConfig[] = [
  {
    id: 'non_gaap_bridge',
    title: 'Earnings Quality / Non-GAAP Bridge',
    subtitle: 'Adjusted EBITDA, Non-GAAP Net Income, Free Cash Flow bridges',
    icon: <TrendingUp size={16} aria-hidden="true" />,
    thumbnailLines: ['Operating Income (EBIT)', '+ Depr & Amortization', '+ Stock-Based Comp', '= Adjusted EBITDA'],
  },
  {
    id: 'capital_structure',
    title: 'Capital Structure & Debt Sizing',
    subtitle: 'Note 8 debt tranches, interest rates, maturities, ASC 842 leases',
    icon: <CreditCard size={16} aria-hidden="true" />,
    thumbnailLines: ['5.25% Senior Notes 2028', 'Term Loan B (SOFR+3%)', 'Revolving Credit Facility', '= Total Debt $2.5B'],
  },
  {
    id: 'cash_conversion',
    title: 'Valuation & Cash Conversion',
    subtitle: 'Operating Cash Flow, CapEx, Working Capital normalization',
    icon: <PieChart size={16} aria-hidden="true" />,
    isComingSoon: true,
    thumbnailLines: ['Operating Cash Flow', '- Capex / Maintenance', 'Δ Working Capital', '= Normalized FCF'],
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
  const [requestedPacks, setRequestedPacks] = useState<Set<string>>(new Set())
  const inputRef = useRef<HTMLInputElement>(null)

  const activePack = onSelectWorkflowPack ? selectedWorkflowPack : internalPack

  function handlePackChange(pack: WorkflowPack) {
    if (onSelectWorkflowPack) {
      onSelectWorkflowPack(pack)
    } else {
      setInternalPack(pack)
    }
  }

  function handleRequestPack(packId: string, e: React.MouseEvent) {
    e.stopPropagation()
    setRequestedPacks((prev) => new Set(prev).add(packId))
  }

  function processFiles(fileList: FileList | File[]) {
    const files = Array.from(fileList)
    const accepted: File[] = []
    const rejected: RejectedFile[] = []

    for (const file of files) {
      if (isPdf(file)) {
        accepted.push(file)
      } else {
        rejected.push({ filename: file.name, reason: 'unsupported file type (must be PDF)' })
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
    <div className="upload-section" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* ── Hero: "What do you want to build?" ── */}
      <div className="fn-hero-section">
        <h2
          style={{
            fontFamily: 'var(--fn-font-serif)',
            fontSize: '1.5rem',
            fontWeight: 700,
            color: 'var(--ink)',
            marginBottom: '0.25rem',
          }}
        >
          What do you want to build?
        </h2>
        <p style={{ fontSize: '0.85rem', color: 'var(--ink-muted)', margin: 0 }}>
          Select a financial model pack to configure automatic extraction rules and tie-outs.
        </p>

        {/* ── Workflow Pack Cards with Real Output Thumbnails ── */}
        <div
          role="radiogroup"
          aria-label="Workflow Pack Options"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
            gap: '1rem',
            marginTop: '1rem',
          }}
        >
          {WORKFLOW_PACK_CONFIGS.map((pack) => {
            const isSelected = activePack === pack.id
            const isRequested = requestedPacks.has(pack.id)

            return (
              <div
                key={pack.id}
                role="radio"
                aria-checked={isSelected}
                tabIndex={pack.isComingSoon ? -1 : 0}
                onClick={() => {
                  if (!pack.isComingSoon) {
                    handlePackChange(pack.id)
                  }
                }}
                onKeyDown={(e) => {
                  if (!pack.isComingSoon && (e.key === ' ' || e.key === 'Enter')) {
                    e.preventDefault()
                    handlePackChange(pack.id)
                  }
                }}
                style={{
                  position: 'relative',
                  padding: '1.1rem',
                  borderRadius: 'var(--fn-radius-lg)',
                  border: isSelected ? '2px solid var(--accent)' : '1px solid var(--border)',
                  backgroundColor: isSelected ? 'rgba(43, 75, 238, 0.04)' : 'var(--surface)',
                  boxShadow: isSelected
                    ? '0 0 0 2px var(--accent), var(--fn-shadow-md)'
                    : 'var(--fn-shadow-sm)',
                  cursor: pack.isComingSoon ? 'default' : 'pointer',
                  transition: 'all var(--fn-motion-state)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.75rem',
                  overflow: 'hidden',
                }}
              >
                {/* Header with Title and Selected Ring / Check */}
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div
                      style={{
                        padding: '6px',
                        borderRadius: 'var(--fn-radius-sm)',
                        backgroundColor: isSelected ? 'rgba(43, 75, 238, 0.12)' : 'var(--surface-2)',
                        color: isSelected ? 'var(--accent)' : 'var(--ink-secondary)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      {pack.icon}
                    </div>
                    <div>
                      <h3
                        style={{
                          margin: 0,
                          fontSize: '0.9rem',
                          fontWeight: 600,
                          color: 'var(--ink)',
                        }}
                      >
                        {pack.title}
                      </h3>
                      <p style={{ margin: '2px 0 0 0', fontSize: '0.75rem', color: 'var(--ink-muted)' }}>
                        {pack.subtitle}
                      </p>
                    </div>
                  </div>

                  {/* Selected Indicator: Filled Ring + Check */}
                  {isSelected && (
                    <div
                      style={{
                        flexShrink: 0,
                        width: '22px',
                        height: '22px',
                        borderRadius: '50%',
                        backgroundColor: 'var(--accent)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#fff',
                        boxShadow: '0 2px 4px rgba(43, 75, 238, 0.3)',
                      }}
                      aria-label="Selected"
                    >
                      <Check size={13} strokeWidth={3} aria-hidden="true" />
                    </div>
                  )}

                  {/* "Request this" Button for Coming Soon */}
                  {pack.isComingSoon && (
                    <button
                      type="button"
                      onClick={(e) => handleRequestPack(pack.id, e)}
                      disabled={isRequested}
                      style={{
                        flexShrink: 0,
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        padding: '3px 8px',
                        borderRadius: 'var(--fn-radius-sm)',
                        background: isRequested ? 'var(--surface-2)' : 'rgba(43, 75, 238, 0.08)',
                        color: isRequested ? 'var(--ok)' : 'var(--accent)',
                        border: '1px solid var(--border)',
                        cursor: isRequested ? 'default' : 'pointer',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                      }}
                    >
                      {isRequested ? (
                        <>
                          <Check size={11} aria-hidden="true" />
                          <span>Requested</span>
                        </>
                      ) : (
                        <>
                          <Sparkles size={11} aria-hidden="true" />
                          <span>Request this</span>
                        </>
                      )}
                    </button>
                  )}
                </div>

                {/* Real Output Thumbnail Preview */}
                <div
                  style={{
                    backgroundColor: 'var(--surface-2)',
                    borderRadius: 'var(--fn-radius-sm)',
                    border: '1px solid var(--border)',
                    padding: '8px 10px',
                    fontSize: '11px',
                    fontFamily: 'var(--fn-font-mono)',
                    color: 'var(--ink-secondary)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '4px',
                  }}
                >
                  <div
                    style={{
                      fontSize: '10px',
                      color: 'var(--ink-muted)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em',
                      marginBottom: '2px',
                    }}
                  >
                    Output Preview
                  </div>
                  {pack.thumbnailLines.map((line, idx) => (
                    <div
                      key={idx}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        borderBottom: idx < pack.thumbnailLines.length - 1 ? '1px dashed var(--border)' : 'none',
                        paddingBottom: '2px',
                        fontWeight: line.startsWith('=') ? 600 : 400,
                        color: line.startsWith('=') ? 'var(--ink)' : 'inherit',
                      }}
                    >
                      <span>{line}</span>
                      <span>──</span>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* ── Slim Drop Bar that Expands with Spotlight on Drag-Over ── */}
      <div
        className={`upload-zone upload-zone--slim${isDragOver ? ' upload-zone--drag-over' : ''}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        aria-label="Filing upload bar"
        style={{
          border: isDragOver ? '2px dashed var(--accent)' : '1px dashed var(--border)',
          borderRadius: 'var(--fn-radius-md)',
          backgroundColor: isDragOver ? 'rgba(43, 75, 238, 0.05)' : 'var(--surface)',
          boxShadow: isDragOver ? '0 0 0 3px rgba(43, 75, 238, 0.15)' : 'var(--fn-shadow-sm)',
          padding: isDragOver ? '1.5rem 1rem' : '0.85rem 1.25rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '1rem',
          transition: 'all var(--fn-motion-state)',
          cursor: 'pointer',
        }}
        onClick={handleBrowseClick}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              padding: '8px',
              borderRadius: '50%',
              backgroundColor: isDragOver ? 'rgba(43, 75, 238, 0.15)' : 'var(--surface-2)',
              color: isDragOver ? 'var(--accent)' : 'var(--ink-muted)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <UploadCloud size={20} aria-hidden="true" />
          </div>
          <div>
            <div style={{ fontWeight: 600, fontSize: '0.85rem', color: 'var(--ink)' }}>
              {isDragOver ? 'Release to stage filing for extraction' : 'Drop 10-K or 10-Q filing here or browse files'}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--ink-muted)' }}>
              Auto-detects company and fiscal period
            </div>
          </div>
        </div>

        <button
          type="button"
          className="fn-btn fn-btn--secondary fn-btn--sm"
          onClick={(e) => {
            e.stopPropagation()
            handleBrowseClick()
          }}
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
      </div>

      {/* ── Rejection Alerts ── */}
      {rejections.length > 0 && (
        <ul
          className="upload-zone__rejections"
          role="alert"
          aria-live="assertive"
          style={{
            margin: 0,
            padding: '8px 12px',
            backgroundColor: 'rgba(194, 65, 12, 0.1)',
            border: '1px solid var(--danger)',
            borderRadius: 'var(--fn-radius-md)',
            listStyle: 'none',
            display: 'flex',
            flexDirection: 'column',
            gap: '4px',
          }}
        >
          {rejections.map((r, i) => (
            <li
              key={i}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                fontSize: '0.8rem',
                color: 'var(--danger)',
              }}
            >
              <AlertCircle size={14} aria-hidden="true" />
              <span>
                <strong>{r.filename}</strong> — {r.reason}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default UploadZone
