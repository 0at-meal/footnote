import { useState, useEffect, useRef } from 'react'
import type {
  SourceComponent,
  SourceChainResponse,
  ProvenanceQueryResponse,
  ProvenanceSummaryRecord,
} from '../../types/audit'
import { loadPdf, renderPage, type PDFDocumentProxy } from '../../lib/pdf/renderer'
import { normalizeBboxToPixels, type PixelBoundingBox } from '../../lib/pdf/coordinates'
import { computeChainRollup } from '../../lib/pdf/audit_status'
import { buildAuditReportDownloadUrl, buildAuditReportFilename } from '../../lib/audit_report'
import './AuditTrailView.css'

interface Props {
  jobId: string
  apiBase: string
  onBack: () => void
}

const STATUS_TOOLTIPS: Record<string, string> = {
  locked: 'Confirmed by analyst & locked against further modification',
  flagged: 'Flagged during review for discrepancy or manual inspection',
  auto_accepted: 'High confidence extraction (≥ 0.95), auto-accepted',
  needs_review: 'Medium confidence extraction (0.65–0.95), requires review',
  manual_required: 'Low confidence extraction (< 0.65), requires manual verification',
  pending_taxonomy_confirmation: 'Unrecognized label awaiting taxonomy confirmation',
  source_record_missing: 'Underlying source record is missing from store',
}

function StatusBadge({ status, isMissing }: { status: string; isMissing: boolean }) {
  if (isMissing) {
    return (
      <span
        className="status-badge status-badge--failed"
        title="Underlying source record is missing from data store"
      >
        Missing Record
      </span>
    )
  }
  const badgeClass = `status-badge status-badge--${status}`
  const label = status.replace(/_/g, ' ')
  const tooltip = STATUS_TOOLTIPS[status] || label
  return (
    <span className={badgeClass} title={tooltip} aria-label={`Status: ${label}`}>
      {label}
    </span>
  )
}

export default function AuditTrailView({ jobId, apiBase, onBack }: Props) {
  const [provenanceRecords, setProvenanceRecords] = useState<ProvenanceSummaryRecord[]>([])
  const [selectedSheet, setSelectedSheet] = useState<string>('Reconciliation')
  const [cellCoordInput, setCellCoordInput] = useState<string>('C4')
  const [provIdInput, setProvIdInput] = useState<string>('')

  const [chain, setChain] = useState<SourceChainResponse | null>(null)
  const [isLoadingChain, setIsLoadingChain] = useState<boolean>(false)
  const [chainError, setChainError] = useState<string | null>(null)

  const [selectedComponent, setSelectedComponent] = useState<SourceComponent | null>(null)

  // PDF viewer states
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null)
  const [activePage, setActivePage] = useState<number>(1)
  const [canvasDims, setCanvasDims] = useState<{ width: number; height: number }>({
    width: 0,
    height: 0,
  })
  const [pdfError, setPdfError] = useState<string | null>(null)
  const [isLoadingPdf, setIsLoadingPdf] = useState<boolean>(true)

  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  // ── Helper: Resolve Source Chain by Cell ────────────────────────────────
  async function resolveByCell(sheet: string, coord: string) {
    const trimmedCoord = coord.trim().toUpperCase()
    if (!trimmedCoord) return

    setIsLoadingChain(true)
    setChainError(null)

    try {
      const res = await fetch(`${apiBase}/audit-trail/${jobId}/cell/${sheet}/${trimmedCoord}`)
      if (!res.ok) {
        throw new Error(`Server error (${res.status})`)
      }
      const data = (await res.json()) as SourceChainResponse
      setChain(data)
      if (data.components.length > 0) {
        // Keep currently selected component if it still exists in the refreshed chain
        setSelectedComponent((prev) => {
          if (prev) {
            const match = data.components.find((c) => c.component_id === prev.component_id)
            if (match) return match
          }
          return data.components[0]
        })
        setActivePage((prev) => {
          if (prev) return prev
          return data.components[0].page
        })
      } else {
        setSelectedComponent(null)
      }
    } catch (err) {
      setChainError(err instanceof Error ? err.message : 'Failed to resolve source chain')
    } finally {
      setIsLoadingChain(false)
    }
  }

  // ── Helper: Resolve Source Chain by Provenance ID ───────────────────────
  async function resolveById(id: string) {
    const trimmedId = id.trim()
    if (!trimmedId) return

    setIsLoadingChain(true)
    setChainError(null)

    try {
      const res = await fetch(
        `${apiBase}/audit-trail/${jobId}/record?provenance_id=${encodeURIComponent(trimmedId)}`,
      )
      if (!res.ok) {
        throw new Error(`Server error (${res.status})`)
      }
      const data = (await res.json()) as SourceChainResponse
      setChain(data)
      if (data.components.length > 0) {
        setSelectedComponent(data.components[0])
        setActivePage(data.components[0].page)
      } else {
        setSelectedComponent(null)
      }
    } catch (err) {
      setChainError(err instanceof Error ? err.message : 'Failed to resolve source chain')
    } finally {
      setIsLoadingChain(false)
    }
  }

  // ── 1. Load available provenance records on mount ────────────────────────
  useEffect(() => {
    let cancelled = false

    async function fetchMetadataAndInitialChain() {
      try {
        const res = await fetch(`${apiBase}/models/${jobId}/provenance`)
        if (!res.ok) return
        const data = (await res.json()) as ProvenanceQueryResponse
        if (cancelled) return
        setProvenanceRecords(data.records || [])

        const firstRecon = data.records?.find((r) => r.sheet_name === 'Reconciliation')
        if (firstRecon) {
          setSelectedSheet(firstRecon.sheet_name)
          setCellCoordInput(firstRecon.cell_coord)

          // Fetch initial chain
          const chainRes = await fetch(
            `${apiBase}/audit-trail/${jobId}/cell/${firstRecon.sheet_name}/${firstRecon.cell_coord}`,
          )
          if (!chainRes.ok || cancelled) return
          const chainData = (await chainRes.json()) as SourceChainResponse
          if (cancelled) return
          setChain(chainData)
          if (chainData.components.length > 0) {
            setSelectedComponent(chainData.components[0])
            setActivePage(chainData.components[0].page)
          }
        }
      } catch {
        // Non-fatal fallback
      }
    }

    void fetchMetadataAndInitialChain()

    return () => {
      cancelled = true
    }
  }, [jobId, apiBase])

  // ── 2. Load PDF document binary ─────────────────────────────────────────
  useEffect(() => {
    let cancelled = false

    async function fetchPdf() {
      try {
        const doc = await loadPdf(`${apiBase}/review/${jobId}/pdf`)
        if (cancelled) return
        setPdfDoc(doc)
        setPdfError(null)
      } catch {
        if (cancelled) return
        setPdfError('Source PDF unavailable')
      } finally {
        if (!cancelled) setIsLoadingPdf(false)
      }
    }

    void fetchPdf()

    return () => {
      cancelled = true
    }
  }, [jobId, apiBase])

  // ── 3. Render active PDF page to canvas ─────────────────────────────────
  useEffect(() => {
    if (!pdfDoc || !canvasRef.current) return

    let cancelled = false
    const targetPage = selectedComponent ? selectedComponent.page : activePage

    async function drawPage() {
      if (!pdfDoc || !canvasRef.current) return

      if (targetPage < 1 || targetPage > pdfDoc.numPages) {
        if (!cancelled) setPdfError(`Page ${targetPage} not found in document`)
        return
      }

      try {
        await renderPage(pdfDoc, targetPage, canvasRef.current, 1.3)
        if (cancelled) return
        setPdfError(null)
        setActivePage(targetPage)
        if (canvasRef.current) {
          const width = parseInt(canvasRef.current.style.width, 10) || canvasRef.current.width
          const height = parseInt(canvasRef.current.style.height, 10) || canvasRef.current.height
          setCanvasDims({ width, height })
        }
      } catch (err) {
        if (cancelled) return
        setPdfError(err instanceof Error ? err.message : 'Failed to render PDF page')
      }
    }

    void drawPage()

    return () => {
      cancelled = true
    }
  }, [pdfDoc, selectedComponent, activePage])

  // ── Calculate BBox Highlight Overlay ─────────────────────────────────────
  let bboxStyle: PixelBoundingBox | null = null
  if (selectedComponent && selectedComponent.page === activePage && canvasDims.width > 0) {
    bboxStyle = normalizeBboxToPixels(selectedComponent.bbox, canvasDims.width, canvasDims.height)
  }

  const rollup = chain?.is_found ? computeChainRollup(chain.components) : null

  return (
    <div className="audit-page">
      <header className="audit-header">
        <div className="audit-header__left">
          <button
            type="button"
            className="audit-header__back-btn"
            onClick={onBack}
            aria-label="Back to dashboard"
          >
            ← Back
          </button>
          <div>
            <h1 className="audit-header__title">Audit Trail &amp; Source Chain Lookup</h1>
            <p className="audit-header__subtitle">Job: {jobId}</p>
          </div>
        </div>
        <div className="audit-header__right">
          <a
            href={buildAuditReportDownloadUrl(apiBase, jobId)}
            download={buildAuditReportFilename(jobId)}
            className="audit-header__export-btn"
            style={{
              backgroundColor: '#0f766e',
              borderColor: '#0f766e',
              color: '#ffffff',
              padding: '0.4rem 0.8rem',
              borderRadius: '4px',
              fontSize: '0.85rem',
              fontWeight: 500,
              textDecoration: 'none',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.375rem',
            }}
            aria-label={`Export Audit Report PDF for ${jobId}`}
          >
            Export Audit PDF
          </a>
        </div>
      </header>

      <div className="audit-body">
        {/* ── Left Pane: Query & Chain Display ── */}
        <div className="audit-sidebar">
          <section className="audit-query-section" aria-labelledby="query-heading">
            <h2 id="query-heading" className="audit-query-section__title">
              Lookup Cell Provenance
            </h2>

            <form
              className="audit-query-form"
              onSubmit={(e) => {
                e.preventDefault()
                void resolveByCell(selectedSheet, cellCoordInput)
              }}
            >
              <div className="audit-query-form__row">
                <select
                  className="audit-query-select"
                  value={selectedSheet}
                  onChange={(e) => setSelectedSheet(e.target.value)}
                  aria-label="Worksheet"
                >
                  <option value="Reconciliation">Reconciliation</option>
                  <option value="Source_Inputs">Source_Inputs</option>
                </select>

                <input
                  type="text"
                  className="audit-query-input"
                  value={cellCoordInput}
                  onChange={(e) => setCellCoordInput(e.target.value)}
                  placeholder="e.g. C4, C7, F2"
                  aria-label="Cell Coordinate"
                />

                <button type="submit" className="audit-query-btn" disabled={isLoadingChain}>
                  {isLoadingChain ? 'Resolving...' : 'Lookup'}
                </button>
              </div>
            </form>

            {/* Quick-select pills for generated workbook cells */}
            {provenanceRecords.length > 0 && (
              <div>
                <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.75rem' }}>
                  Generated Model Cells:
                </div>
                <div className="audit-quick-cells">
                  {provenanceRecords.map((rec) => {
                    const isActive =
                      chain?.sheet_name === rec.sheet_name && chain?.cell_coord === rec.cell_coord
                    return (
                      <button
                        key={rec.id}
                        type="button"
                        className={`audit-cell-pill ${isActive ? 'audit-cell-pill--active' : ''}`}
                        onClick={() => {
                          setSelectedSheet(rec.sheet_name)
                          setCellCoordInput(rec.cell_coord)
                          void resolveByCell(rec.sheet_name, rec.cell_coord)
                        }}
                      >
                        {rec.sheet_name === 'Reconciliation' ? 'Recon' : 'Input'}!{rec.cell_coord}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Provenance ID lookup option */}
            <div style={{ marginTop: '0.75rem' }}>
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  if (provIdInput.trim()) {
                    void resolveById(provIdInput)
                  }
                }}
                style={{ display: 'flex', gap: '0.5rem' }}
              >
                <input
                  type="text"
                  className="audit-query-input"
                  style={{ fontSize: '0.75rem' }}
                  value={provIdInput}
                  onChange={(e) => setProvIdInput(e.target.value)}
                  placeholder="Or enter Provenance URN ID..."
                  aria-label="Provenance URN ID"
                />
                <button
                  type="submit"
                  className="audit-query-btn"
                  style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                >
                  Find ID
                </button>
              </form>
            </div>
          </section>

          {chainError && (
            <div className="audit-error-state" role="alert">
              <p>{chainError}</p>
            </div>
          )}

          {chain && !chain.is_found && (
            <div className="audit-error-state" role="alert">
              <p>{chain.error_detail || 'No provenance record found for this cell.'}</p>
            </div>
          )}

          {chain && chain.is_found && (
            <>
              {/* Selected Cell Header Info with Status Rollup */}
              <div className="audit-target-card">
                <div className="audit-target-card__header">
                  <div>
                    <span className="audit-target-card__cell-ref">
                      {chain.sheet_name ? `${chain.sheet_name}!${chain.cell_coord}` : chain.node_id}
                    </span>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text)', marginLeft: '8px' }}>
                      {chain.is_formula ? 'Formula Cell' : 'Source Cell'}
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    {rollup && (
                      <span
                        className={`status-badge ${rollup.badgeClass}`}
                        title={rollup.summary}
                        aria-label={`Verification rollup: ${rollup.label}`}
                      >
                        {rollup.label}
                      </span>
                    )}
                    <button
                      type="button"
                      className="audit-refresh-btn"
                      onClick={() => {
                        if (chain.sheet_name && chain.cell_coord) {
                          void resolveByCell(chain.sheet_name, chain.cell_coord)
                        } else if (chain.provenance_id) {
                          void resolveById(chain.provenance_id)
                        }
                      }}
                      title="Refresh live review status (EC-10)"
                      aria-label="Refresh live review status"
                    >
                      ↻
                    </button>
                  </div>
                </div>
                {chain.formula_expression && (
                  <div className="audit-target-card__formula">{chain.formula_expression}</div>
                )}
              </div>

              {/* Resolved Components List */}
              <section className="audit-chain-section">
                <div className="audit-chain-section__header">
                  <h3 className="audit-chain-section__title">Contributing Source Records</h3>
                  <span className="audit-chain-section__count">
                    {chain.components.length}{' '}
                    {chain.components.length === 1 ? 'record' : 'records'}
                  </span>
                </div>

                <div className="audit-components-list">
                  {chain.components.map((comp, idx) => {
                    const isSelected = selectedComponent?.component_id === comp.component_id
                    return (
                      <article
                        key={comp.component_id || idx}
                        className={`audit-component-card ${
                          isSelected ? 'audit-component-card--active' : ''
                        } ${comp.is_missing ? 'audit-component-card--missing' : ''}`}
                      >
                        <div className="audit-component-card__header">
                          <div>
                            <h4 className="audit-component-card__label">
                              {comp.normalized_label || comp.label}
                            </h4>
                            {comp.normalized_label && comp.normalized_label !== comp.label && (
                              <p className="audit-component-card__orig-label">
                                Original: {comp.label}
                              </p>
                            )}
                          </div>
                          <StatusBadge status={comp.review_status} isMissing={comp.is_missing} />
                        </div>

                        <div className="audit-component-card__value-row">
                          <span className="audit-component-card__value">{comp.value}</span>
                          <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                            Page {comp.page}
                          </span>
                        </div>

                        <div className="audit-component-card__meta">
                          <span className="audit-component-card__meta-item">
                            📄 {comp.source_file}
                          </span>
                          <span className="audit-component-card__meta-item">
                            BBox: [{comp.bbox.x0.toFixed(0)}, {comp.bbox.y0.toFixed(0)},{' '}
                            {comp.bbox.x1.toFixed(0)}, {comp.bbox.y1.toFixed(0)}]
                          </span>
                        </div>

                        <div className="audit-component-card__actions">
                          <button
                            type="button"
                            className={`audit-pdf-link-btn ${
                              isSelected ? 'audit-pdf-link-btn--active' : ''
                            }`}
                            onClick={() => {
                              setSelectedComponent(comp)
                              setActivePage(comp.page)
                            }}
                            aria-label={`View ${comp.label} in PDF page ${comp.page}`}
                          >
                            <svg
                              width="14"
                              height="14"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              aria-hidden="true"
                            >
                              <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
                              <circle cx="12" cy="12" r="3" />
                            </svg>
                            View in PDF (p. {comp.page})
                          </button>
                        </div>
                      </article>
                    )
                  })}
                </div>
              </section>
            </>
          )}
        </div>

        {/* ── Right Pane: PDF Page Viewer & BBox Highlight ── */}
        <div className="audit-pdf-viewer">
          <div className="audit-pdf-toolbar">
            <div className="audit-pdf-toolbar__info">
              {activePage && <span className="audit-pdf-toolbar__page-info">Page {activePage}</span>}
              {selectedComponent && (
                <span style={{ color: '#94a3b8', fontSize: '0.8125rem' }}>
                  Highlighting: {selectedComponent.normalized_label || selectedComponent.label}
                </span>
              )}
            </div>
          </div>

          <div className="audit-pdf-canvas-container">
            {isLoadingPdf && (
              <div className="audit-empty-state" style={{ color: '#ffffff' }}>
                <p>Loading PDF document...</p>
              </div>
            )}

            {pdfError && (
              <div className="audit-error-state" role="alert">
                <p>{pdfError}</p>
              </div>
            )}

            {!pdfError && (
              <div className="audit-canvas-wrapper">
                <canvas ref={canvasRef} />
                {bboxStyle && (
                  <div
                    className="audit-bbox-highlight"
                    style={{
                      left: `${bboxStyle.left}px`,
                      top: `${bboxStyle.top}px`,
                      width: `${bboxStyle.width}px`,
                      height: `${bboxStyle.height}px`,
                    }}
                    title={`Source: ${selectedComponent?.source_file} (p. ${selectedComponent?.page})`}
                  />
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
