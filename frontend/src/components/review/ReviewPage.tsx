import { useState, useEffect, useRef } from 'react'
import type { ReviewItem, ReviewItemsResponse, ReviewStatus, StatementType } from '../../types/review'
import { loadPdf, renderPage, PDF_RENDER_SCALE } from '../../lib/pdf/renderer'
import type { PDFDocumentProxy } from '../../lib/pdf/renderer'
import { normalizeBboxToPixels } from '../../lib/pdf/coordinates'
import DebtScheduleCard from '../DebtScheduleCard'
import LeaseScheduleCard from '../footnote/LeaseScheduleCard'
import ConcentrationCard from '../footnote/ConcentrationCard'
import './ReviewPage.css'

interface Props {
  jobId: string
  apiBase: string
  onBack: () => void
  onAuditTrail?: (jobId: string) => void
  initialParserUsed?: 'docling' | 'pymupdf' | 'mixed' | null
  initialItems?: ReviewItem[]
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

const STATEMENT_LABELS: Record<StatementType, string> = {
  income_statement: 'IS',
  balance_sheet: 'BS',
  cash_flow: 'CF',
  non_gaap_bridge: 'Bridge',
  kpi: 'KPI',
}

function StatementBadge({ type }: { type?: StatementType | null }) {
  if (!type) return null
  return (
    <span
      className={`statement-badge statement-badge--${type}`}
      title={`Statement: ${STATEMENT_LABELS[type]}`}
      aria-label={`Statement: ${STATEMENT_LABELS[type]}`}
    >
      {STATEMENT_LABELS[type]}
    </span>
  )
}

type FilterTab =
  | 'flagged'
  | 'all'
  | 'income_statement'
  | 'non_gaap_bridge'
  | 'cash_flow'
  | 'balance_sheet'
  | 'kpi'

export default function ReviewPage({
  jobId,
  apiBase,
  onBack,
  onAuditTrail,
  initialParserUsed = null,
  initialItems = [],
}: Props) {
  const [items, setItems] = useState<ReviewItem[]>(initialItems)
  const [selectedItem, setSelectedItem] = useState<ReviewItem | null>(
    initialItems.length > 0 ? initialItems[0] : null,
  )
  const [itemsLoading, setItemsLoading] = useState(initialItems.length === 0)
  const [itemsError, setItemsError] = useState<string | null>(null)

  const [activeTab, setActiveTab] = useState<FilterTab>('flagged')

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

  // ── Model Generation State (Ticket 4.1) ─────────────────────────────────
  const [isGeneratingModel, setIsGeneratingModel] = useState<boolean>(false)
  const [generateModelSuccess, setGenerateModelSuccess] = useState<{ totalCells: number; message: string } | null>(null)
  const [generateModelError, setGenerateModelError] = useState<string | null>(null)
  const [parserUsed, setParserUsed] = useState<string | null>(initialParserUsed)
  const [isParserBannerDismissed, setIsParserBannerDismissed] = useState<boolean>(false)
  const [selectedBulkTaxonomyIds, setSelectedBulkTaxonomyIds] = useState<Set<string>>(new Set())
  const [customCanonicalNames, setCustomCanonicalNames] = useState<Record<string, string>>({})
  const [isBulkConfirmingTaxonomy, setIsBulkConfirmingTaxonomy] = useState<boolean>(false)

  const lockedCount = items.filter((i) => i.status === 'locked').length

  const isFlagged = (item: ReviewItem) =>
    item.status === 'needs_review' ||
    item.status === 'manual_required' ||
    item.status === 'extraction_error' ||
    item.status === 'pending_taxonomy_confirmation' ||
    item.status === 'flagged'

  const flaggedCount = items.filter(isFlagged).length
  const totalCount = items.length
  const isNeedsReview = items.some(i => i.statement_type === 'income_statement' && (i.status === 'needs_review' || i.status === 'manual_required' || i.status === 'extraction_error'))
  const bridgeNeedsReview = items.some(i => i.statement_type === 'non_gaap_bridge' && (i.status === 'needs_review' || i.status === 'manual_required' || i.status === 'extraction_error'))
  const cfNeedsReview = items.some(i => i.statement_type === 'cash_flow' && (i.status === 'needs_review' || i.status === 'manual_required' || i.status === 'extraction_error'))
  const bsNeedsReview = items.some(i => i.statement_type === 'balance_sheet' && (i.status === 'needs_review' || i.status === 'manual_required' || i.status === 'extraction_error'))
  const isCount = items.filter((i) => i.statement_type === 'income_statement').length
  const bridgeCount = items.filter((i) => i.statement_type === 'non_gaap_bridge').length
  const cfCount = items.filter((i) => i.statement_type === 'cash_flow').length
  const bsCount = items.filter((i) => i.statement_type === 'balance_sheet').length
  const kpiCount = items.filter((i) => i.statement_type === 'kpi').length

  const filteredItems = items.filter((item) => {
    if (activeTab === 'flagged') {
      return isFlagged(item)
    }
    if (activeTab === 'income_statement') {
      return item.statement_type === 'income_statement'
    }
    if (activeTab === 'non_gaap_bridge') {
      return item.statement_type === 'non_gaap_bridge'
    }
    if (activeTab === 'cash_flow') {
      return item.statement_type === 'cash_flow'
    }
    if (activeTab === 'balance_sheet') {
      return item.statement_type === 'balance_sheet'
    }
    if (activeTab === 'kpi') {
      return item.statement_type === 'kpi'
    }
    return true // 'all'
  })

  // Group filtered items by table_name
  type TableGroup = {
    tableName: string | null
    items: ReviewItem[]
  }

  const tableGroups: TableGroup[] = []
  filteredItems.forEach((item) => {
    const currentTable = item.table_name || null
    const lastGroup = tableGroups[tableGroups.length - 1]
    if (lastGroup && lastGroup.tableName === currentTable) {
      lastGroup.items.push(item)
    } else {
      tableGroups.push({ tableName: currentTable, items: [item] })
    }
  })

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
        if (data.parser_used) {
          setParserUsed(data.parser_used)
        }
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
        await renderPage(pdfDoc, targetPage, canvasRef.current, PDF_RENDER_SCALE)
        if (cancelled) return
        setCurrentPage(targetPage)
        setPageRenderError(null)
        if (canvasRef.current) {
          const rect = canvasRef.current.getBoundingClientRect()
          setCanvasSize({ width: Math.round(rect.width), height: Math.round(rect.height) })
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

  // ── Bulk Taxonomy Confirmation Handler (Ticket C-5) ─────────────────────
  async function handleBulkConfirmTaxonomy() {
    const pending = items.filter(
      (it) =>
        it.status === 'pending_taxonomy_confirmation' ||
        it.taxonomy_status === 'pending_taxonomy_confirmation',
    )
    const selected = pending.filter((it) => selectedBulkTaxonomyIds.has(it.id))
    if (selected.length === 0) return

    setIsBulkConfirmingTaxonomy(true)
    try {
      const confirmations = selected.map((it) => ({
        item_id: it.id,
        canonical_name: customCanonicalNames[it.id] || it.normalized_label || it.label,
        statement_type: it.statement_type || 'non_gaap_bridge',
      }))

      const res = await fetch(`${apiBase}/review/${jobId}/bulk-confirm-taxonomy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmations }),
      })

      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: 'Bulk taxonomy confirmation failed' }))
        throw new Error(detail.detail || `Server error ${res.status}`)
      }

      const data = (await res.json()) as { items?: ReviewItem[] }
      if (data.items) {
        setItems(data.items)
      }
      setSelectedBulkTaxonomyIds(new Set())
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Bulk taxonomy confirmation failed')
    } finally {
      setIsBulkConfirmingTaxonomy(false)
    }
  }

  // ── Model Generation Handler (Ticket 4.1) ────────────────────────────────
  async function handleGenerateModel() {
    setIsGeneratingModel(true)
    setGenerateModelError(null)
    setGenerateModelSuccess(null)

    try {
      const res = await fetch(`${apiBase}/models/${jobId}/generate`, {
        method: 'POST',
      })

      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: 'Model generation failed' }))
        throw new Error(detail.detail || `Server error ${res.status}`)
      }

      const data = (await res.json()) as { total_cells_generated?: number; is_success?: boolean }
      const lineItemCount = lockedCount
      setGenerateModelSuccess({
        totalCells: data.total_cells_generated ?? lineItemCount,
        message: `Model generated with ${lineItemCount} line item${lineItemCount === 1 ? '' : 's'}`,
      })
    } catch (err) {
      setGenerateModelError(err instanceof Error ? err.message : 'Model generation failed')
    } finally {
      setIsGeneratingModel(false)
    }
  }

  async function handleApproveBridgeAndGenerateModel() {
    setIsGeneratingModel(true)
    setGenerateModelError(null)
    setGenerateModelSuccess(null)
    try {
      // 1. Batch confirm all target candidates (Ticket 4.1)
      const batchRes = await fetch(`${apiBase}/review/${jobId}/confirm-batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_candidates_only: true,
          auto_add_pending_taxonomy: true,
        }),
      })

      if (!batchRes.ok) {
        const detail = await batchRes.json().catch(() => ({ detail: 'Failed to batch approve items' }))
        throw new Error(detail.detail || `Server error ${batchRes.status}`)
      }

      const batchData = await batchRes.json()
      if (batchData.items) {
        setItems(batchData.items)
      }

      // 2. Generate model
      const genRes = await fetch(`${apiBase}/models/${jobId}/generate`, {
        method: 'POST',
      })

      if (!genRes.ok) {
        const detail = await genRes.json().catch(() => ({ detail: 'Model compilation failed' }))
        throw new Error(detail.detail || `Server error ${genRes.status}`)
      }

      const genData = await genRes.json()
      const totalCells = genData.total_cells_generated ?? (batchData.total_locked || 1)
      setGenerateModelSuccess({
        totalCells,
        message: `Reconciliation items approved and Excel model generated (${batchData.total_locked || totalCells} items)`,
      })
    } catch (err) {
      setGenerateModelError(err instanceof Error ? err.message : 'Batch approval & generation failed')
    } finally {
      setIsGeneratingModel(false)
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
        <div className="review-header__right">
          <div className="review-header__meta">
            Job: <span>{jobId}</span>
          </div>
          {lockedCount > 0 && (
            <button
              type="button"
              className="review-btn review-btn--edit"
              disabled={isGeneratingModel}
              onClick={() => void handleGenerateModel()}
              aria-label="Generate Excel Model"
              title="Compile currently locked items into Excel model"
            >
              {isGeneratingModel ? 'Generating Model...' : `Generate Excel Model (${lockedCount})`}
            </button>
          )}
          <button
            type="button"
            className="review-btn review-btn--generate"
            disabled={items.length === 0 || isGeneratingModel}
            onClick={() => void handleApproveBridgeAndGenerateModel()}
            aria-label="Approve & Generate Complete Financial Model (6 Tabs)"
            title="Batch approve all reconciliation items and compile Excel model (1-Click)"
          >
            {isGeneratingModel ? 'Approving & Generating Model...' : 'Approve & Generate Complete Financial Model (6 Tabs)'}
          </button>
        </div>
      </header>

      {/* ── Degraded Quality Warning Banner (Ticket 5.2) ── */}
      {(parserUsed === 'pymupdf' || parserUsed === 'mixed') && !isParserBannerDismissed && (
        <div
          className="review-banner review-banner--warning"
          role="alert"
          style={{
            backgroundColor: '#451a03',
            border: '1px solid #d97706',
            color: '#fef3c7',
            padding: '0.75rem 1rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '1rem',
            marginBottom: '0.5rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}>
            <span style={{ fontSize: '1.1rem' }}>⚠️</span>
            <span>
              <strong>Degraded Extraction Quality</strong> — Docling native parsing was unavailable for this filing. Layout was extracted using the PyMuPDF fallback parser. Bounding boxes and confidence scores may be less precise. Please review highlighted items carefully.
            </span>
          </div>
          <button
            type="button"
            className="review-banner__close-btn"
            onClick={() => setIsParserBannerDismissed(true)}
            aria-label="Dismiss warning"
            style={{
              background: 'transparent',
              border: 'none',
              color: '#fef3c7',
              cursor: 'pointer',
              fontSize: '1rem',
              padding: '0.25rem 0.5rem',
            }}
          >
            ✕
          </button>
        </div>
      )}

      {/* ── Model Generation Status Banners (Ticket 4.1) ── */}
      {generateModelSuccess && (
        <div className="review-banner review-banner--success" role="status">
          <div className="review-banner__content">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M20 6 9 17l-5-5" />
            </svg>
            <span>{generateModelSuccess.message}</span>
          </div>
          <div className="review-banner__actions">
            <a
              href={`${apiBase}/models/${jobId}/download`}
              download={`${jobId}_model.xlsx`}
              className="review-banner__link-btn"
              aria-label={`Download Excel model for ${jobId}`}
            >
              Download Excel (.xlsx)
            </a>
            {onAuditTrail && (
              <button
                type="button"
                className="review-banner__link-btn review-banner__link-btn--secondary"
                onClick={() => onAuditTrail(jobId)}
              >
                View Audit Trail
              </button>
            )}
            <button
              type="button"
              className="review-banner__close-btn"
              onClick={() => setGenerateModelSuccess(null)}
              aria-label="Dismiss message"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {generateModelError && (
        <div className="review-banner review-banner--error" role="alert">
          <div className="review-banner__content">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>{generateModelError}</span>
          </div>
          <button
            type="button"
            className="review-banner__close-btn"
            onClick={() => setGenerateModelError(null)}
            aria-label="Dismiss error"
          >
            ✕
          </button>
        </div>
      )}

      {/* ── Split Body ── */}
      <div className="review-body">
        {/* ── Left Item Sidebar ── */}
        <aside className="review-sidebar" aria-label="Extracted line items">
          <div className="review-sidebar__header">
            <h2 className="review-sidebar__heading">Extracted Items</h2>
          </div>

          {/* ── Scoped Filter Tabs (Ticket 1.2.2) ── */}
          <div className="review-tabs" role="tablist" aria-label="Filter extracted items">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'flagged'}
              className={`review-tab ${activeTab === 'flagged' ? 'review-tab--active' : ''}`}
              onClick={() => setActiveTab('flagged')}
            >
              Flagged
              <span className="review-tab__badge">{flaggedCount}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'all'}
              className={`review-tab ${activeTab === 'all' ? 'review-tab--active' : ''}`}
              onClick={() => setActiveTab('all')}
            >
              All
              <span className="review-tab__badge">{totalCount}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'income_statement'}
              className={`review-tab ${activeTab === 'income_statement' ? 'review-tab--active' : ''}`}
              onClick={() => setActiveTab('income_statement')}
            >
              IS
              <span className="review-tab__badge">{isCount}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'non_gaap_bridge'}
              className={`review-tab ${activeTab === 'non_gaap_bridge' ? 'review-tab--active' : ''}`}
              onClick={() => setActiveTab('non_gaap_bridge')}
            >
              Bridge
              <span className="review-tab__badge">{bridgeCount}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'cash_flow'}
              className={`review-tab ${activeTab === 'cash_flow' ? 'review-tab--active' : ''}`}
              onClick={() => setActiveTab('cash_flow')}
            >
              CF
              <span className="review-tab__badge">{cfCount}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'balance_sheet'}
              className={`review-tab ${activeTab === 'balance_sheet' ? 'review-tab--active' : ''}`}
              onClick={() => setActiveTab('balance_sheet')}
            >
              BS
              <span className="review-tab__badge">{bsCount}</span>
            </button>
            {kpiCount > 0 && (
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'kpi'}
                className={`review-tab ${activeTab === 'kpi' ? 'review-tab--active' : ''}`}
                onClick={() => setActiveTab('kpi')}
              >
                KPI
                <span className="review-tab__badge">{kpiCount}</span>
              </button>
            )}
          </div>
          {/* ?? Statement Readiness Indicators (Ticket D.2.2) ?? */}
          {items.length > 0 && (
            <div className="review-readiness-chips" style={{ display: 'flex', gap: '8px', padding: '6px 12px', flexWrap: 'wrap', fontSize: '11px', background: 'var(--surface)', borderBottom: '1px solid var(--border)' }}>
              <span style={{ color: isNeedsReview ? '#d97706' : '#15803d', display: 'inline-flex', alignItems: 'center', gap: '4px', fontWeight: 500 }}>
                {isNeedsReview ? '?' : '?'} IS: {isNeedsReview ? 'Review needed' : 'Ready'}
              </span>
              <span style={{ color: bridgeNeedsReview ? '#d97706' : '#15803d', display: 'inline-flex', alignItems: 'center', gap: '4px', fontWeight: 500 }}>
                {bridgeNeedsReview ? '?' : '?'} Bridge: {bridgeNeedsReview ? 'Review needed' : 'Ready'}
              </span>
              <span style={{ color: cfNeedsReview ? '#d97706' : '#15803d', display: 'inline-flex', alignItems: 'center', gap: '4px', fontWeight: 500 }}>
                {cfNeedsReview ? '?' : '?'} CF: {cfNeedsReview ? 'Review needed' : 'Ready'}
              </span>
              <span style={{ color: bsNeedsReview ? '#d97706' : '#15803d', display: 'inline-flex', alignItems: 'center', gap: '4px', fontWeight: 500 }}>
                {bsNeedsReview ? '?' : '?'} BS: {bsNeedsReview ? 'Review needed' : 'Ready'}
              </span>
            </div>
          )}

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

          {!itemsLoading && !itemsError && filteredItems.length === 0 && (
            <div className="job-list--empty" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', padding: '1.5rem 1rem', alignItems: 'center', textAlign: 'center' }}>
              <p style={{ margin: 0, color: 'var(--text-muted, #94a3b8)', fontSize: '0.875rem' }}>
                {activeTab === 'flagged'
                  ? items.length > 0
                    ? 'All items reviewed. Ready to generate the financial model.'
                    : 'No extracted items found.'
                  : 'No reconciliation items found.'}
              </p>
              {activeTab === 'flagged' && items.length > 0 && (
                <button
                  type="button"
                  className="review-btn review-btn--generate"
                  disabled={isGeneratingModel}
                  onClick={() => void handleApproveBridgeAndGenerateModel()}
                  style={{ width: '100%', marginTop: '0.25rem', padding: '0.5rem 0.75rem', fontSize: '0.85rem' }}
                  aria-label="Approve & Generate Complete Financial Model (6 Tabs) →"
                >
                  {isGeneratingModel
                    ? 'Approving & Generating Model...'
                    : 'Approve & Generate Complete Financial Model (6 Tabs) →'}
                </button>
              )}
            </div>
          )}

          {/* ── Bulk Taxonomy Confirmation Panel (Ticket C-5) ── */}
          {(() => {
            const pendingTaxonomyItems = items.filter(
              (it) =>
                it.status === 'pending_taxonomy_confirmation' ||
                it.taxonomy_status === 'pending_taxonomy_confirmation',
            )
            if (pendingTaxonomyItems.length === 0) return null

            const allSelected =
              pendingTaxonomyItems.length > 0 &&
              pendingTaxonomyItems.every((it) => selectedBulkTaxonomyIds.has(it.id))

            const toggleSelectAll = () => {
              if (allSelected) {
                setSelectedBulkTaxonomyIds(new Set())
              } else {
                setSelectedBulkTaxonomyIds(new Set(pendingTaxonomyItems.map((it) => it.id)))
              }
            }

            const toggleItem = (id: string) => {
              setSelectedBulkTaxonomyIds((prev) => {
                const next = new Set(prev)
                if (next.has(id)) next.delete(id)
                else next.add(id)
                return next
              })
            }

            return (
              <div
                className="review-bulk-taxonomy-panel"
                style={{
                  background: 'var(--surface-raised, #1e293b)',
                  border: '1px solid var(--border-color, #334155)',
                  borderRadius: '6px',
                  padding: '10px 12px',
                  margin: '8px 12px',
                  fontSize: '0.85rem',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: '8px',
                  }}
                >
                  <strong style={{ color: '#f59e0b' }}>
                    Pending Taxonomy Confirmations ({pendingTaxonomyItems.length})
                  </strong>
                  <button
                    type="button"
                    className="review-btn review-btn--edit"
                    style={{ fontSize: '11px', padding: '2px 6px' }}
                    onClick={toggleSelectAll}
                  >
                    {allSelected ? 'Deselect All' : 'Select All'}
                  </button>
                </div>
                <div
                  style={{
                    maxHeight: '180px',
                    overflowY: 'auto',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '6px',
                    marginBottom: '8px',
                  }}
                >
                  {pendingTaxonomyItems.map((pItem) => {
                    const isChecked = selectedBulkTaxonomyIds.has(pItem.id)
                    const canonicalVal =
                      customCanonicalNames[pItem.id] ??
                      pItem.normalized_label ??
                      pItem.label
                    return (
                      <div
                        key={pItem.id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          background: 'rgba(0,0,0,0.2)',
                          padding: '4px 6px',
                          borderRadius: '4px',
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => toggleItem(pItem.id)}
                          aria-label={`Select ${pItem.label}`}
                        />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div
                            style={{
                              fontSize: '12px',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {pItem.label} ({pItem.value})
                          </div>
                          <input
                            type="text"
                            value={canonicalVal}
                            onChange={(e) =>
                              setCustomCanonicalNames((prev) => ({
                                ...prev,
                                [pItem.id]: e.target.value,
                              }))
                            }
                            placeholder="Canonical name"
                            style={{
                              width: '100%',
                              fontSize: '11px',
                              padding: '2px 4px',
                              marginTop: '2px',
                              background: '#0f172a',
                              color: '#fff',
                              border: '1px solid #475569',
                              borderRadius: '3px',
                            }}
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
                <button
                  type="button"
                  className="review-btn review-btn--confirm"
                  disabled={
                    selectedBulkTaxonomyIds.size === 0 ||
                    isBulkConfirmingTaxonomy
                  }
                  onClick={() => void handleBulkConfirmTaxonomy()}
                  style={{ width: '100%', fontSize: '12px', padding: '6px' }}
                >
                  {isBulkConfirmingTaxonomy
                    ? 'Confirming Taxonomy...'
                    : `Batch Confirm Selected (${selectedBulkTaxonomyIds.size})`}
                </button>
              </div>
            )
          })()}

          {/* ── Debt Schedule Footnote Card (Feature 8, Step E) ── */}
          <DebtScheduleCard
            jobId={jobId}
            apiBase={apiBase}
            onTrancheSelect={(tranche) => setCurrentPage(tranche.page)}
          />

          {/* ── Lease Schedule Footnote Card (Feature 8, Step F) ── */}
          <LeaseScheduleCard
            jobId={jobId}
            apiBase={apiBase}
            onYearSelect={(year) => setCurrentPage(year.page)}
          />

          {/* ── Customer & Supplier Concentration Card (Feature 8, Step I) ── */}
          <ConcentrationCard jobId={jobId} apiBase={apiBase} />

          {!itemsLoading && !itemsError && filteredItems.length > 0 && (
            <div className="review-sidebar__list" role="listbox" aria-label="Extracted items list">
              {tableGroups.map((group, groupIdx) => (
                <div key={groupIdx} className="review-table-group">
                  {group.tableName && (
                    <div className="review-table-header" title={`Table: ${group.tableName}`}>
                      <span className="review-table-header__icon">📊</span>
                      <span className="review-table-header__title">{group.tableName}</span>
                    </div>
                  )}
                  <div className="review-table-group__items">
                    {group.items.map((item) => {
                      const isSelected = selectedItem?.id === item.id
                      const isEditing = editingItemId === item.id
                      const isCandidate = item.is_target_metric_candidate !== false

                      return (
                        <div
                          key={item.id}
                          role="option"
                          aria-selected={isSelected}
                          tabIndex={0}
                          className={`review-item-card ${isSelected ? 'review-item-card--selected' : ''} ${isCandidate ? 'review-item-card--candidate' : ''}`}
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
                      <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                        <StatementBadge type={item.statement_type} />
                        <ReviewStatusBadge status={item.status} />
                      </div>
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
            </div>
          ))}
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
