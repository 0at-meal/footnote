import { useState, useEffect, useRef } from 'react'
import type { ReviewItem, ReviewItemsResponse, ReviewStatus } from '../../types/review'
import { loadPdf, renderPage } from '../../lib/pdf/renderer'
import type { PDFDocumentProxy } from '../../lib/pdf/renderer'
import { normalizeBboxToPixels } from '../../lib/pdf/coordinates'
import './ReviewPage.css'

interface Props {
  jobId: string
  apiBase: string
  onBack: () => void
}

const REVIEW_STATUS_LABELS: Record<ReviewStatus, string> = {
  auto_accepted: 'Auto Accepted',
  needs_review: 'Needs Review',
  manual_required: 'Manual Required',
  extraction_error: 'Extraction Error',
  pending_taxonomy_confirmation: 'Pending Taxonomy',
  flagged: 'Flagged',
  locked: 'Locked',
}

function ReviewStatusBadge({ status }: { status: ReviewStatus }) {
  return (
    <span
      className={`status-badge status-badge--${status}`}
      aria-label={`Status: ${REVIEW_STATUS_LABELS[status]}`}
    >
      {REVIEW_STATUS_LABELS[status]}
    </span>
  )
}

export default function ReviewPage({ jobId, apiBase, onBack }: Props) {
  const [items, setItems] = useState<ReviewItem[]>([])
  const [selectedItem, setSelectedItem] = useState<ReviewItem | null>(null)
  const [itemsLoading, setItemsLoading] = useState(true)
  const [itemsError, setItemsError] = useState<string | null>(null)

  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null)
  const [pdfLoading, setPdfLoading] = useState(true)
  const [pdfError, setPdfError] = useState<string | null>(null)

  const [currentPage, setCurrentPage] = useState<number>(1)
  const [pageRenderError, setPageRenderError] = useState<string | null>(null)
  const [canvasSize, setCanvasSize] = useState<{ width: number; height: number }>({ width: 0, height: 0 })

  // ── Action State (Feature 5 Step 3) ─────────────────────────────────────
  const [editingItemId, setEditingItemId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState<string>('')
  const [editLabel, setEditLabel] = useState<string>('')
  const [editError, setEditError] = useState<string | null>(null)
  const [isActionPending, setIsActionPending] = useState<boolean>(false)
  const [taxonomyPromptItem, setTaxonomyPromptItem] = useState<ReviewItem | null>(null)

  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  // ── 1. Fetch Review Items ───────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false

    async function fetchItems() {
      try {
        const res = await fetch(`${apiBase}/review/${jobId}/items`)
        if (!res.ok) {
          const detail = await res.json().catch(() => ({ detail: 'Failed to load extraction items' }))
          throw new Error(detail.detail || `Server error ${res.status}`)
        }
        const data = (await res.json()) as ReviewItemsResponse
        if (cancelled) return
        setItems(data.items)
        if (data.items.length > 0) {
          setSelectedItem(data.items[0])
          setCurrentPage(data.items[0].page)
        }
        setItemsError(null)
      } catch (err) {
        if (cancelled) return
        setItemsError(err instanceof Error ? err.message : 'Failed to load extraction items')
      } finally {
        if (!cancelled) setItemsLoading(false)
      }
    }

    void fetchItems()

    return () => {
      cancelled = true
    }
  }, [jobId, apiBase])

  // ── 2. Load PDF binary ──────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false

    async function fetchPdf() {
      try {
        const pdfUrl = `${apiBase}/review/${jobId}/pdf`
        const doc = await loadPdf(pdfUrl)
        if (cancelled) return
        setPdfDoc(doc)
        setPdfError(null)
      } catch (err) {
        if (cancelled) return
        // EC-7 handling: PDF unavailable or fetch error
        setPdfError(err instanceof Error ? err.message : 'Source PDF unavailable')
      } finally {
        if (!cancelled) setPdfLoading(false)
      }
    }

    void fetchPdf()

    return () => {
      cancelled = true
    }
  }, [jobId, apiBase])

  // ── 3. Render Canvas when PDF doc or selected item page changes ──────────
  useEffect(() => {
    if (!pdfDoc || !canvasRef.current) return

    let cancelled = false
    const targetPage = selectedItem ? selectedItem.page : currentPage

    async function draw() {
      if (!pdfDoc || !canvasRef.current) return
      try {
        await renderPage(pdfDoc, targetPage, canvasRef.current)
        if (cancelled) return
        setCurrentPage(targetPage)
        setPageRenderError(null)
        if (canvasRef.current) {
          const width = parseInt(canvasRef.current.style.width, 10) || canvasRef.current.clientWidth
          const height = parseInt(canvasRef.current.style.height, 10) || canvasRef.current.clientHeight
          setCanvasSize({ width, height })
        }
      } catch (err) {
        if (cancelled) return
        // EC-2 handling: Page not found in document
        setPageRenderError(err instanceof Error ? err.message : `Page ${targetPage} could not be rendered`)
      }
    }

    void draw()

    return () => {
      cancelled = true
    }
  }, [pdfDoc, selectedItem, currentPage])

  function handleSelectItem(item: ReviewItem) {
    setSelectedItem(item)
    setCurrentPage(item.page)
    // Clear editing mode when switching items
    if (editingItemId && editingItemId !== item.id) {
      setEditingItemId(null)
      setEditError(null)
    }
  }

  // ── Action Handlers (Feature 5 Step 3) ──────────────────────────────────

  function handleStartEdit(item: ReviewItem) {
    setEditingItemId(item.id)
    setEditValue(item.value)
    setEditLabel(item.label)
    setEditError(null)
  }

  function handleCancelEdit() {
    setEditingItemId(null)
    setEditError(null)
  }

  async function handleSaveEdit(item: ReviewItem) {
    if (!editLabel.trim()) {
      setEditError('Label cannot be empty.')
      return
    }

    setIsActionPending(true)
    setEditError(null)

    try {
      const res = await fetch(`${apiBase}/review/${jobId}/items/${item.id}/edit`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: editValue, label: editLabel }),
      })

      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: 'Failed to save edit' }))
        throw new Error(detail.detail || `Server error ${res.status}`)
      }

      const updatedItem = (await res.json()) as ReviewItem
      setItems((prev) => prev.map((it) => (it.id === updatedItem.id ? updatedItem : it)))
      setSelectedItem(updatedItem)
      setEditingItemId(null)
    } catch (err) {
      setEditError(err instanceof Error ? err.message : 'Failed to save edit')
    } finally {
      setIsActionPending(false)
    }
  }

  async function handleConfirm(item: ReviewItem, addToTaxonomy: boolean = false) {
    if (item.status === 'pending_taxonomy_confirmation' && !addToTaxonomy) {
      setTaxonomyPromptItem(item)
      return
    }

    setIsActionPending(true)

    try {
      const res = await fetch(`${apiBase}/review/${jobId}/items/${item.id}/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ add_to_taxonomy: addToTaxonomy }),
      })

      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: 'Failed to confirm item' }))
        throw new Error(detail.detail || `Server error ${res.status}`)
      }

      const updatedItem = (await res.json()) as ReviewItem
      setItems((prev) => prev.map((it) => (it.id === updatedItem.id ? updatedItem : it)))
      setSelectedItem(updatedItem)
      setTaxonomyPromptItem(null)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Confirmation failed')
    } finally {
      setIsActionPending(false)
    }
  }

  async function handleFlag(item: ReviewItem) {
    setIsActionPending(true)

    try {
      const res = await fetch(`${apiBase}/review/${jobId}/items/${item.id}/flag`, {
        method: 'POST',
      })

      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: 'Failed to update flag state' }))
        throw new Error(detail.detail || `Server error ${res.status}`)
      }

      const updatedItem = (await res.json()) as ReviewItem
      setItems((prev) => prev.map((it) => (it.id === updatedItem.id ? updatedItem : it)))
      setSelectedItem(updatedItem)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Flag action failed')
    } finally {
      setIsActionPending(false)
    }
  }

  async function handleUnlock(item: ReviewItem) {
    setIsActionPending(true)

    try {
      const res = await fetch(`${apiBase}/review/${jobId}/items/${item.id}/unlock`, {
        method: 'POST',
      })

      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: 'Failed to unlock item' }))
        throw new Error(detail.detail || `Server error ${res.status}`)
      }

      const updatedItem = (await res.json()) as ReviewItem
      setItems((prev) => prev.map((it) => (it.id === updatedItem.id ? updatedItem : it)))
      setSelectedItem(updatedItem)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Unlock action failed')
    } finally {
      setIsActionPending(false)
    }
  }

  return (
    <div className="review-layout">
      {/* ── Review Header ── */}
      <header className="review-header">
        <div className="review-header__left">
          <button
            type="button"
            className="review-header__back-btn"
            onClick={onBack}
            aria-label="Back to queue"
          >
            ← Back to Queue
          </button>
          <h1 className="review-header__title">
            Extraction Review
            {items.length > 0 && (
              <span className="section-title__badge">{items.length} items</span>
            )}
          </h1>
        </div>
        <div className="review-header__meta">
          Job: <span>{jobId}</span>
        </div>
      </header>

      {/* ── Split Body ── */}
      <div className="review-body">
        {/* ── Left Item Sidebar ── */}
        <aside className="review-sidebar" aria-label="Extracted line items">
          <div className="review-sidebar__header">
            <h2 className="review-sidebar__heading">Extracted Items</h2>
          </div>

          {itemsLoading && (
            <div className="job-list--empty">
              <p>Loading extracted items...</p>
            </div>
          )}

          {itemsError && (
            <div className="submission-errors" style={{ margin: 12 }}>
              <div className="submission-errors__header">
                <strong>Error loading items</strong>
              </div>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--error)' }}>
                {itemsError}
              </p>
            </div>
          )}

          {!itemsLoading && !itemsError && items.length === 0 && (
            <div className="job-list--empty">
              <p>No extracted items found for this job.</p>
            </div>
          )}

          {!itemsLoading && !itemsError && items.length > 0 && (
            <div className="review-sidebar__list" role="listbox" aria-label="Extracted items list">
              {items.map((item) => {
                const isSelected = selectedItem?.id === item.id
                const isEditing = editingItemId === item.id

                return (
                  <div
                    key={item.id}
                    role="option"
                    aria-selected={isSelected}
                    tabIndex={0}
                    className={`review-item-card ${isSelected ? 'review-item-card--selected' : ''}`}
                    onClick={() => handleSelectItem(item)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        if (!isEditing) {
                          e.preventDefault()
                          handleSelectItem(item)
                        }
                      }
                    }}
                  >
                    <div className="review-item-card__top">
                      <span className="review-item-card__label">{item.label}</span>
                      <ReviewStatusBadge status={item.status} />
                    </div>

                    {item.normalized_label && (
                      <span className="review-item-card__normalized">
                        ↳ {item.normalized_label}
                      </span>
                    )}

                    <div className="review-item-card__value-row">
                      <span className="review-item-card__value">{item.value}</span>
                      <span className="review-item-card__page">Page {item.page}</span>
                    </div>

                    {item.error_detail && (
                      <div className="review-item-card__error-detail">
                        {item.error_detail}
                      </div>
                    )}

                    {/* ── Inline Edit Mode ── */}
                    {isEditing ? (
                      <div
                        className="review-edit-form"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <div className="review-edit-field">
                          <label className="review-edit-label" htmlFor={`edit-label-${item.id}`}>
                            Label
                          </label>
                          <input
                            id={`edit-label-${item.id}`}
                            className="review-edit-input"
                            value={editLabel}
                            onChange={(e) => setEditLabel(e.target.value)}
                            placeholder="Structural label"
                          />
                        </div>
                        <div className="review-edit-field">
                          <label className="review-edit-label" htmlFor={`edit-value-${item.id}`}>
                            Value
                          </label>
                          <input
                            id={`edit-value-${item.id}`}
                            className="review-edit-input"
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            placeholder="Numeric value"
                          />
                        </div>

                        {editError && (
                          <p className="review-edit-error" role="alert">
                            {editError}
                          </p>
                        )}

                        <div className="review-edit-buttons">
                          <button
                            type="button"
                            className="review-btn review-btn--edit"
                            onClick={handleCancelEdit}
                            disabled={isActionPending}
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            className="review-btn review-btn--confirm"
                            onClick={() => void handleSaveEdit(item)}
                            disabled={isActionPending}
                          >
                            Save
                          </button>
                        </div>
                      </div>
                    ) : item.status === 'locked' ? (
                      /* ── Locked Item Actions (Feature 5 Step 4) ── */
                      <div
                        className="review-item-actions"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          type="button"
                          className="review-btn review-btn--unlock"
                          disabled={isActionPending}
                          onClick={() => void handleUnlock(item)}
                          title="Unlock item to permit edits"
                        >
                          <svg
                            width="12"
                            height="12"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            aria-hidden="true"
                          >
                            <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
                            <path d="M7 11V7a5 5 0 0 1 9.9-1" />
                          </svg>
                          Unlock
                        </button>
                      </div>
                    ) : (
                      /* ── Unlocked Item Actions (Feature 5 Step 3) ── */
                      <div
                        className="review-item-actions"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          type="button"
                          className="review-btn review-btn--confirm"
                          disabled={
                            item.status === 'extraction_error' ||
                            isActionPending
                          }
                          onClick={() => void handleConfirm(item)}
                          title={
                            item.status === 'extraction_error'
                              ? 'Edit with valid values before confirming'
                              : 'Confirm item and lock'
                          }
                        >
                          Confirm
                        </button>
                        <button
                          type="button"
                          className="review-btn review-btn--edit"
                          disabled={isActionPending}
                          onClick={() => handleStartEdit(item)}
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          className={`review-btn review-btn--flag ${item.status === 'flagged' ? 'review-btn--flagged' : ''}`}
                          disabled={isActionPending}
                          onClick={() => void handleFlag(item)}
                        >
                          {item.status === 'flagged' ? 'Flagged' : 'Flag'}
                        </button>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </aside>

        {/* ── Right PDF Viewer ── */}
        <main className="review-viewer" aria-label="PDF Document Viewer">
          <div className="review-viewer__toolbar">
            <div className="review-viewer__page-info">
              {pdfDoc ? `Page ${currentPage} of ${pdfDoc.numPages}` : 'Loading document...'}
            </div>
            {selectedItem && (
              <div style={{ fontSize: 12, color: 'var(--text)' }}>
                Source: {selectedItem.source_file}
              </div>
            )}
          </div>

          <div className="review-viewer__stage">
            {pdfLoading && (
              <div className="review-viewer__loading">
                <div className="review-viewer__spinner" />
                <span>Loading source PDF...</span>
              </div>
            )}

            {/* EC-7 handling: PDF binary unavailable */}
            {pdfError && (
              <div className="review-viewer__error" role="alert">
                <h3>Source PDF Unavailable</h3>
                <p>{pdfError}</p>
              </div>
            )}

            {/* EC-2 handling: Page not found */}
            {pageRenderError && !pdfError && (
              <div className="review-viewer__error" role="alert">
                <h3>Page Rendering Error</h3>
                <p>{pageRenderError}</p>
              </div>
            )}

            <div
              className="review-viewer__canvas-wrap"
              style={{
                display: !pdfLoading && !pdfError && !pageRenderError ? 'block' : 'none',
              }}
            >
              <canvas ref={canvasRef} className="review-viewer__canvas" />
              {canvasSize.width > 0 && (
                <div
                  className="review-viewer__overlay"
                  style={{ width: canvasSize.width, height: canvasSize.height }}
                >
                  {items
                    .filter((item) => item.page === currentPage)
                    .map((item) => {
                      const isSelected = selectedItem?.id === item.id
                      const pixelBox = normalizeBboxToPixels(
                        item.bbox,
                        canvasSize.width,
                        canvasSize.height,
                      )
                      return (
                        <div
                          key={item.id}
                          role="button"
                          tabIndex={0}
                          aria-label={`Highlight for ${item.label}: ${item.value}`}
                          className={`review-bbox ${isSelected ? 'review-bbox--active' : 'review-bbox--inactive'} ${item.status === 'extraction_error' ? 'review-bbox--extraction_error' : ''}`}
                          style={{
                            left: `${pixelBox.left}px`,
                            top: `${pixelBox.top}px`,
                            width: `${pixelBox.width}px`,
                            height: `${pixelBox.height}px`,
                          }}
                          onClick={(e) => {
                            e.stopPropagation()
                            handleSelectItem(item)
                          }}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault()
                              e.stopPropagation()
                              handleSelectItem(item)
                            }
                          }}
                          title={`${item.label}: ${item.value}`}
                        />
                      )
                    })}
                </div>
              )}
            </div>
          </div>
        </main>
      </div>

      {/* ── Taxonomy Addition Confirmation Modal (EC-5) ── */}
      {taxonomyPromptItem && (
        <div
          className="review-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-labelledby="tax-modal-title"
        >
          <div className="review-modal">
            <h3 id="tax-modal-title" className="review-modal__title">
              Confirm Taxonomy Addition
            </h3>
            <p className="review-modal__body">
              The label <strong>&ldquo;{taxonomyPromptItem.label}&rdquo;</strong> is unrecognized
              in the seed taxonomy. Confirming this item will add it to the active taxonomy baseline
              and lock the item.
            </p>
            <div className="review-modal__footer">
              <button
                type="button"
                className="review-btn review-btn--edit"
                onClick={() => setTaxonomyPromptItem(null)}
                disabled={isActionPending}
              >
                Cancel
              </button>
              <button
                type="button"
                className="review-btn review-btn--confirm"
                onClick={() => void handleConfirm(taxonomyPromptItem, true)}
                disabled={isActionPending}
              >
                Add to Taxonomy &amp; Confirm
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
