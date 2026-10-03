import { useState, useEffect, useLayoutEffect, useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import type { ReviewItem, ReviewItemsResponse, ReviewStatus, StatementType } from '../../types/review'
import { loadPdf, createSerialRenderer, PDF_RENDER_SCALE } from '../../lib/pdf/renderer'
import type { PDFDocumentProxy, SerialPageRenderer } from '../../lib/pdf/renderer'
import { normalizeBboxToPixels } from '../../lib/pdf/coordinates'
import { secSourceLink } from '../../lib/secLinks'
import { buildAuditReportDownloadUrl, buildAuditReportFilename } from '../../lib/audit_report'
import DebtScheduleCard from '../DebtScheduleCard'
import LeaseScheduleCard from '../footnote/LeaseScheduleCard'
import ConcentrationCard from '../footnote/ConcentrationCard'
import { SourceChip } from '../brand/SourceChip'
import {
  ArrowLeft,
  Check,
  Edit2,
  Flag,
  LockOpen,
  Download,
  Table2,
  AlertCircle,
  CheckCircle2,
  Cpu,
  ChevronDown,
  ChevronRight,
  Info,
  History,
  FileText,
  HelpCircle,
  ZoomIn,
  ZoomOut,
  Maximize2,
} from 'lucide-react'
import './ReviewPage.css'

interface Props {
  jobId: string
  apiBase: string
  onBack: () => void
  onAuditTrail?: (jobId: string) => void
  initialParserUsed?: 'docling' | 'pymupdf' | 'mixed' | null
  initialItems?: ReviewItem[]
}

// Zoom snaps to 25% steps (so 100% and 150% are exact levels); Fit width may land between them.
const ZOOM_STEP = 0.25
const ZOOM_MIN = 0.5
const ZOOM_MAX = 2.5
const zoomIn = (z: number) => Math.min(ZOOM_MAX, (Math.floor(z / ZOOM_STEP + 1e-6) + 1) * ZOOM_STEP)
const zoomOut = (z: number) => Math.max(ZOOM_MIN, (Math.ceil(z / ZOOM_STEP - 1e-6) - 1) * ZOOM_STEP)

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

function ItemStatusVisual({ status }: { status: ReviewStatus }) {
  if (status === 'locked' || status === 'auto_accepted') {
    return (
      <span
        title={REVIEW_STATUS_LABELS[status]}
        aria-label={`Status: ${REVIEW_STATUS_LABELS[status]}`}
        style={{ color: 'var(--ok, #1f8a5b)', fontSize: '13px', lineHeight: 1 }}
      >
        ●
      </span>
    )
  }
  if (status === 'needs_review' || status === 'pending_taxonomy_confirmation' || status === 'flagged') {
    return (
      <span
        title={REVIEW_STATUS_LABELS[status]}
        aria-label={`Status: ${REVIEW_STATUS_LABELS[status]}`}
        style={{ color: 'var(--warn, #b7791f)', fontSize: '13px', lineHeight: 1 }}
      >
        ◐
      </span>
    )
  }
  return (
    <span
      title={REVIEW_STATUS_LABELS[status]}
      aria-label={`Status: ${REVIEW_STATUS_LABELS[status]}`}
      style={{ color: 'var(--danger, #c2410c)', fontSize: '13px', lineHeight: 1 }}
    >
      ○
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
  | 'footnotes'

const isFlaggedItem = (item: ReviewItem) =>
  item.status === 'needs_review' ||
  item.status === 'manual_required' ||
  item.status === 'extraction_error' ||
  item.status === 'pending_taxonomy_confirmation' ||
  item.status === 'flagged'

function matchesTab(item: ReviewItem, tab: FilterTab): boolean {
  if (tab === 'flagged') return isFlaggedItem(item)
  if (tab === 'all') return true
  if (tab === 'footnotes') return false
  return item.statement_type === tab
}

/** Default selection: the first item visible in `tab` (AUD-019), else the first item. */
function firstItemFor(items: ReviewItem[], tab: FilterTab): ReviewItem | null {
  return items.find((i) => matchesTab(i, tab)) ?? items[0] ?? null
}

/** Rows of the virtualized item list: table headings and item cards. */
type ListRow = { kind: 'table'; key: string; tableName: string } | { kind: 'item'; key: string; item: ReviewItem }

export default function ReviewPage({
  jobId,
  apiBase,
  onBack,
  onAuditTrail,
  initialParserUsed = null,
  initialItems = [],
}: Props) {
  const [items, setItems] = useState<ReviewItem[]>(initialItems)
  const [selectedItem, setSelectedItem] = useState<ReviewItem | null>(() => firstItemFor(initialItems, 'flagged'))
  const [itemsLoading, setItemsLoading] = useState(initialItems.length === 0)
  const [itemsError, setItemsError] = useState<string | null>(null)

  const [activeTab, setActiveTab] = useState<FilterTab>('flagged')
  const activeTabRef = useRef<FilterTab>('flagged')

  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null)
  const [pdfLoading, setPdfLoading] = useState(true)
  const [pdfError, setPdfError] = useState<string | null>(null)

  const [currentPage, setCurrentPage] = useState<number>(() => firstItemFor(initialItems, 'flagged')?.page ?? 1)
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
  const [generateModelSuccess, setGenerateModelSuccess] = useState<{ totalCells: number; message: string } | null>(null)
  const [generateModelError, setGenerateModelError] = useState<string | null>(null)
  const [parserUsed, setParserUsed] = useState<string | null>(initialParserUsed)
  const [selectedBulkTaxonomyIds, setSelectedBulkTaxonomyIds] = useState<Set<string>>(new Set())
  const [customCanonicalNames, setCustomCanonicalNames] = useState<Record<string, string>>({})
  const [isBulkConfirmingTaxonomy, setIsBulkConfirmingTaxonomy] = useState<boolean>(false)

  // ── Redesign States (FN-062) ─────────────────────────────────────────────
  const [showDetailsPopover, setShowDetailsPopover] = useState(false)
  const [showExportDropdown, setShowExportDropdown] = useState(false)
  const [showShortcutModal, setShowShortcutModal] = useState(false)
  const [isTaxonomyPanelCollapsed, setIsTaxonomyPanelCollapsed] = useState(false)
  const [zoomScale, setZoomScale] = useState(1.0)
  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('fn-review-split-width')
      if (saved) return parseInt(saved, 10) || 480
    }
    return 480
  })

  const lockedCount = items.filter((i) => i.status === 'locked').length
  const verifiedCount = items.filter((i) => i.status === 'locked' || i.status === 'auto_accepted').length
  const needsReviewCount = items.filter(
    (i) => i.status === 'needs_review' || i.status === 'pending_taxonomy_confirmation' || i.status === 'flagged',
  ).length
  const manualCount = items.filter((i) => i.status === 'manual_required' || i.status === 'extraction_error').length

  const flaggedCount = items.filter(isFlaggedItem).length
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

  const filteredItems = items.filter((item) => matchesTab(item, activeTab))

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

  const listRows: ListRow[] = []
  tableGroups.forEach((group, groupIdx) => {
    if (group.tableName) listRows.push({ kind: 'table', key: `table-${groupIdx}`, tableName: group.tableName })
    group.items.forEach((it) => listRows.push({ kind: 'item', key: it.id, item: it }))
  })

  // One virtualized list (FN-062 / AUD-019): only the visible cards are mounted, so a 954-item
  // filing stays responsive. Content above the list (taxonomy panel, empty state) is the scroll margin.
  const listScrollRef = useRef<HTMLDivElement | null>(null)
  const listHeadRef = useRef<HTMLDivElement | null>(null)
  const [listOffset, setListOffset] = useState(0)
  useLayoutEffect(() => {
    const head = listHeadRef.current
    if (!head) return
    const update = () => setListOffset(head.offsetTop + head.offsetHeight)
    update()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(update)
    observer.observe(head)
    return () => observer.disconnect()
  }, [activeTab])
  // React Compiler is not enabled in this project, so the memoization caveat this rule warns about does not apply.
  // eslint-disable-next-line react-hooks/incompatible-library
  const rowVirtualizer = useVirtualizer({
    count: listRows.length,
    getScrollElement: () => listScrollRef.current,
    estimateSize: (index) => (listRows[index]?.kind === 'table' ? 36 : 120),
    getItemKey: (index) => listRows[index]?.key ?? index,
    overscan: 8,
    scrollMargin: listOffset,
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
        const first = firstItemFor(data.items, activeTabRef.current)
        if (first) {
          setSelectedItem(first)
          setCurrentPage(first.page)
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

  // ── 3. Render Canvas when PDF doc or target page changes (AUD-001) ───────
  // Renders are serialized per canvas: the previous pdf.js RenderTask is cancelled and
  // awaited before the next one starts, and the effect never sets the state it depends on.
  const rendererRef = useRef<SerialPageRenderer | null>(null)
  if (rendererRef.current === null) rendererRef.current = createSerialRenderer()
  // The viewed page is independent of the selection (AUD-020): selecting an item moves to its
  // page, but Next/Prev can then browse away from it.
  const targetPage = currentPage
  const renderScale = PDF_RENDER_SCALE * zoomScale
  const [renderAttempt, setRenderAttempt] = useState(0)
  const stageRef = useRef<HTMLDivElement | null>(null)
  const highlightRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const renderer = rendererRef.current
    return () => renderer?.cancel()
  }, [])

  useEffect(() => {
    if (!pdfDoc || !canvasRef.current || !rendererRef.current) return
    let active = true
    const canvas = canvasRef.current
    rendererRef.current
      .render(pdfDoc, targetPage, canvas, renderScale)
      .then((result) => {
        if (!active || result === 'superseded') return
        setPageRenderError(null)
        // Zoom re-renders at a higher scale, so the canvas's CSS size is the page size in
        // layout pixels; size the highlight overlay from it, not from a transformed rect.
        setCanvasSize({ width: parseFloat(canvas.style.width) || 0, height: parseFloat(canvas.style.height) || 0 })
      })
      .catch((err: unknown) => {
        if (!active) return
        // EC-2 handling: Page not found in document
        setPageRenderError(err instanceof Error ? err.message : `Page ${targetPage} could not be rendered`)
      })
    return () => {
      active = false
    }
  }, [pdfDoc, targetPage, renderScale, renderAttempt])

  // Bring the selected item's highlight into view once its page is drawn, and again whenever
  // an item is clicked (even the already-selected one, after the reviewer scrolled away).
  const selectedItemId = selectedItem?.id
  const [scrollRequest, setScrollRequest] = useState(0)
  useEffect(() => {
    highlightRef.current?.scrollIntoView?.({ block: 'center', inline: 'center' })
  }, [selectedItemId, canvasSize, scrollRequest])

  async function handleFitWidth() {
    const stage = stageRef.current
    if (!pdfDoc || !stage) return
    const page = await pdfDoc.getPage(currentPage)
    const pageWidth = page.getViewport({ scale: PDF_RENDER_SCALE }).width
    const style = window.getComputedStyle(stage)
    const available = stage.clientWidth - (parseFloat(style.paddingLeft) || 0) - (parseFloat(style.paddingRight) || 0)
    if (available <= 0 || pageWidth <= 0) return
    setZoomScale(Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Number((available / pageWidth).toFixed(3)))))
  }

  function handleSelectItem(item: ReviewItem) {
    setSelectedItem(item)
    setCurrentPage(item.page)
    setScrollRequest((n) => n + 1)
    // Retry after a failed render when the user picks another item.
    if (pageRenderError) {
      setPageRenderError(null)
      setRenderAttempt((n) => n + 1)
    }
    // Clear editing mode when switching items
    if (editingItemId && editingItemId !== item.id) {
      setEditingItemId(null)
      setEditError(null)
    }
  }

  function handleTabChange(tab: FilterTab) {
    setActiveTab(tab)
    activeTabRef.current = tab
    // Keep the selection inside the visible list (AUD-019).
    if (tab !== 'footnotes' && !(selectedItem && matchesTab(selectedItem, tab))) {
      const first = items.find((i) => matchesTab(i, tab))
      if (first) handleSelectItem(first)
    }
  }

  // Keep the selected card in view in the virtualized list (J/K, tab changes, initial load).
  const selectedRowIndex = listRows.findIndex((r) => r.kind === 'item' && r.item.id === selectedItemId)
  useEffect(() => {
    if (selectedRowIndex >= 0) rowVirtualizer.scrollToIndex(selectedRowIndex, { align: 'auto' })
  }, [selectedRowIndex, rowVirtualizer])

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
      setEditError(null)
    } catch (err) {
      setEditError(err instanceof Error ? err.message : 'Confirmation failed')
    } finally {
      setIsActionPending(false)
    }
  }

  async function handleFlag(item: ReviewItem) {
    setIsActionPending(true)
    setEditError(null)

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
      setEditError(null)
    } catch (err) {
      setEditError(err instanceof Error ? err.message : 'Flag action failed')
    } finally {
      setIsActionPending(false)
    }
  }

  async function handleUnlock(item: ReviewItem) {
    setIsActionPending(true)
    setEditError(null)

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
      setEditError(null)
    } catch (err) {
      setEditError(err instanceof Error ? err.message : 'Unlock action failed')
    } finally {
      setIsActionPending(false)
    }
  }

  // ── Bulk Taxonomy Confirmation Handler (Ticket C-5) ─────────────────────
  async function handleBulkConfirmTaxonomy() {
    const pending = items.filter(
      (it) =>
        it.is_target_metric_candidate !== false &&
        (it.status === 'pending_taxonomy_confirmation' ||
          it.taxonomy_status === 'pending_taxonomy_confirmation'),
    )
    const selected = pending.filter((it) => selectedBulkTaxonomyIds.has(it.id))
    if (selected.length === 0) return

    setIsBulkConfirmingTaxonomy(true)
    setEditError(null)
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
      setEditError(err instanceof Error ? err.message : 'Bulk taxonomy confirmation failed')
    } finally {
      setIsBulkConfirmingTaxonomy(false)
    }
  }

  // ── Model Generation Handler (Ticket 4.1) ────────────────────────────────
  async function handleGenerateModel() {
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
    }
  }

  // ── Keyboard Navigation & Shortcuts (FN-062) ───────────────────────────
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName?.toLowerCase()
      if (tag === 'input' || tag === 'textarea' || tag === 'select') {
        if (e.key === 'Escape') {
          handleCancelEdit()
        }
        return
      }

      if (e.key === '?') {
        e.preventDefault()
        setShowShortcutModal((prev) => !prev)
      } else if (e.key === 'Escape') {
        setShowShortcutModal(false)
        setShowExportDropdown(false)
        setShowDetailsPopover(false)
        if (editingItemId) {
          handleCancelEdit()
        }
      } else if (e.key.toLowerCase() === 'j') {
        e.preventDefault()
        if (filteredItems.length === 0) return
        const currentIndex = selectedItem ? filteredItems.findIndex((it) => it.id === selectedItem.id) : -1
        const nextIndex = (currentIndex + 1) % filteredItems.length
        handleSelectItem(filteredItems[nextIndex])
      } else if (e.key.toLowerCase() === 'k') {
        e.preventDefault()
        if (filteredItems.length === 0) return
        const currentIndex = selectedItem ? filteredItems.findIndex((it) => it.id === selectedItem.id) : 0
        const prevIndex = (currentIndex - 1 + filteredItems.length) % filteredItems.length
        handleSelectItem(filteredItems[prevIndex])
      } else if (e.key.toLowerCase() === 'y') {
        if (selectedItem && !isActionPending) {
          e.preventDefault()
          void handleConfirm(selectedItem)
        }
      } else if (e.key.toLowerCase() === 'e') {
        if (selectedItem && !isActionPending) {
          e.preventDefault()
          handleStartEdit(selectedItem)
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filteredItems, selectedItem, editingItemId, isActionPending])

  const handleMouseDownResizer = (e: React.MouseEvent) => {
    e.preventDefault()
    const startX = e.clientX
    const startWidth = sidebarWidth

    const handleMouseMove = (ev: MouseEvent) => {
      const newWidth = Math.max(320, Math.min(800, startWidth + (ev.clientX - startX)))
      setSidebarWidth(newWidth)
      localStorage.setItem('fn-review-split-width', String(newWidth))
    }

    const handleMouseUp = () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
  }

  return (
    <div className="review-layout">
      {/* ── Review Header ── */}
      <header className="review-header">
        <div className="review-header__left">
          <button
            type="button"
            className="review-header__back-btn fn-btn fn-btn--ghost fn-btn--sm"
            onClick={onBack}
            aria-label="Back to queue"
          >
            <ArrowLeft size={14} aria-hidden="true" />
            <span>Back to Queue</span>
          </button>
          <div className="review-header__title-group">
            <h1 className="review-header__title">
              Extraction Review
            </h1>
            {items.length > 0 && (
              <span className="review-header__count-badge">{items.length} items</span>
            )}
          </div>

          {/* Traceability: Compact Details Popover */}
          <div className="review-header__traceability">
            <div style={{ position: 'relative' }}>
              <button
                type="button"
                className="fn-btn fn-btn--ghost fn-btn--sm review-header__meta-btn"
                onClick={() => setShowDetailsPopover(!showDetailsPopover)}
                aria-label="Job traceability details"
                title={`Compliance Job ID: ${jobId}`}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                  padding: '2px 8px',
                  borderRadius: 'var(--fn-radius-sm)',
                  border: '1px solid var(--border)',
                  background: 'var(--surface-2)',
                  color: 'var(--ink-secondary)',
                  fontSize: '11px',
                  cursor: 'pointer',
                }}
              >
                <Info size={12} aria-hidden="true" />
                <span>Job: {jobId.length > 12 ? `${jobId.slice(0, 10)}…` : jobId}</span>
              </button>

              {/* Full details popover menu */}
              {showDetailsPopover && (
                <div
                  className="review-details-popover"
                  style={{
                    position: 'absolute',
                    top: '100%',
                    left: 0,
                    marginTop: '6px',
                    zIndex: 100,
                    background: 'var(--surface)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--fn-radius-md)',
                    boxShadow: 'var(--fn-shadow-md)',
                    padding: '10px 14px',
                    minWidth: '240px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '6px',
                  }}
                >
                  <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--ink)' }}>Job Traceability</div>
                  <div className="review-header__meta" title={`Compliance Job ID: ${jobId}`}>
                    <span>Job:</span> {jobId}
                  </div>
                </div>
              )}
            </div>

            {/* Hidden Job ID for DOM/test compatibility */}
            <div className="review-header__meta" style={{ display: 'none' }}>
              <span>Job:</span> {jobId}
            </div>

            {parserUsed && (
              <span
                className="status-badge status-badge--pending"
                data-testid="parser-engine-badge"
                style={{ fontSize: '11px', padding: '2px 6px', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
              >
                <Cpu size={12} aria-hidden="true" />
                Engine: {parserUsed === 'pymupdf' ? 'PyMuPDF' : parserUsed === 'ixbrl_html' ? 'iXBRL / HTML' : parserUsed}
              </span>
            )}
          </div>
        </div>

        {/* Header Right: Keyboard shortcuts and Primary Split Button */}
        <div className="review-header__right" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button
            type="button"
            className="fn-btn fn-btn--ghost fn-btn--sm"
            onClick={() => setShowShortcutModal(true)}
            title="Keyboard shortcuts (?)"
            aria-label="Keyboard shortcuts"
          >
            <HelpCircle size={15} aria-hidden="true" />
          </button>

          <div className="review-split-btn">
            <button
              type="button"
              className="fn-btn fn-btn--primary fn-btn--sm review-split-btn__main review-btn--generate"
              onClick={() => void handleGenerateModel()}
              aria-label="Export to Excel"
            >
              <Download size={13} aria-hidden="true" />
              <span>Export to Excel</span>
            </button>
            <button
              type="button"
              className="fn-btn fn-btn--primary fn-btn--sm review-split-btn__toggle"
              onClick={() => setShowExportDropdown((prev) => !prev)}
              aria-label="Export options"
              aria-expanded={showExportDropdown}
            >
              <ChevronDown size={13} aria-hidden="true" />
            </button>

            {showExportDropdown && (
              <div
                className="review-export-dropdown"
                style={{
                  position: 'absolute',
                  right: 0,
                  top: '100%',
                  marginTop: '4px',
                  backgroundColor: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--fn-radius-md)',
                  boxShadow: 'var(--fn-shadow-md)',
                  zIndex: 100,
                  minWidth: '180px',
                  padding: '4px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '2px',
                }}
              >
                <a
                  href={`${apiBase}/models/${jobId}/download`}
                  download={`${jobId}_model.xlsx`}
                  className="fn-btn fn-btn--ghost fn-btn--sm"
                  style={{ justifyContent: 'flex-start', gap: '8px', textDecoration: 'none' }}
                  onClick={() => setShowExportDropdown(false)}
                >
                  <Download size={13} aria-hidden="true" />
                  <span>Download .xlsx</span>
                </a>
                {onAuditTrail && (
                  <button
                    type="button"
                    className="fn-btn fn-btn--ghost fn-btn--sm"
                    style={{ justifyContent: 'flex-start', gap: '8px' }}
                    onClick={() => {
                      setShowExportDropdown(false)
                      onAuditTrail(jobId)
                    }}
                  >
                    <History size={13} aria-hidden="true" />
                    <span>View Audit Trail</span>
                  </button>
                )}
                <a
                  href={buildAuditReportDownloadUrl(apiBase, jobId)}
                  download={buildAuditReportFilename(jobId)}
                  className="fn-btn fn-btn--ghost fn-btn--sm"
                  style={{ justifyContent: 'flex-start', gap: '8px', textDecoration: 'none' }}
                  onClick={() => setShowExportDropdown(false)}
                >
                  <FileText size={13} aria-hidden="true" />
                  <span>Export Audit PDF</span>
                </a>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* ── Progress: Stacked Bar (verified / needs review / manual) and item counts ── */}
      <div
        className="review-progress-section"
        style={{
          padding: '8px 20px',
          backgroundColor: 'var(--surface-2)',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          flexDirection: 'column',
          gap: '6px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px' }}>
          <span style={{ fontWeight: 500, color: 'var(--ink)' }}>
            {`${items.length} items, ${verifiedCount} verified, ${needsReviewCount} need review${manualCount > 0 ? `, ${manualCount} manual` : ''}`}
          </span>
          <span style={{ fontSize: '11px', color: 'var(--ink-muted)' }}>
            {items.length > 0 ? `${Math.round((verifiedCount / items.length) * 100)}% verified` : '0%'}
          </span>
        </div>
        <div
          className="review-progress-stacked"
          role="progressbar"
          aria-label="Extraction verification progress"
          aria-valuenow={verifiedCount}
          aria-valuemin={0}
          aria-valuemax={items.length}
        >
          <div
            style={{
              width: `${items.length > 0 ? (verifiedCount / items.length) * 100 : 0}%`,
              backgroundColor: 'var(--ok)',
              transition: 'width var(--fn-motion-state)',
            }}
            title={`Verified: ${verifiedCount}`}
          />
          <div
            style={{
              width: `${items.length > 0 ? (needsReviewCount / items.length) * 100 : 0}%`,
              backgroundColor: 'var(--warn)',
              transition: 'width var(--fn-motion-state)',
            }}
            title={`Needs review: ${needsReviewCount}`}
          />
          <div
            style={{
              width: `${items.length > 0 ? (manualCount / items.length) * 100 : 0}%`,
              backgroundColor: 'var(--danger)',
              transition: 'width var(--fn-motion-state)',
            }}
            title={`Manual: ${manualCount}`}
          />
        </div>
      </div>


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
              onClick={() => handleTabChange('flagged')}
            >
              Flagged
              <span className="review-tab__badge">{flaggedCount}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'all'}
              className={`review-tab ${activeTab === 'all' ? 'review-tab--active' : ''}`}
              onClick={() => handleTabChange('all')}
            >
              All
              <span className="review-tab__badge">{totalCount}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'income_statement'}
              className={`review-tab ${activeTab === 'income_statement' ? 'review-tab--active' : ''}`}
              onClick={() => handleTabChange('income_statement')}
            >
              IS
              <span className="review-tab__badge">{isCount}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'non_gaap_bridge'}
              className={`review-tab ${activeTab === 'non_gaap_bridge' ? 'review-tab--active' : ''}`}
              onClick={() => handleTabChange('non_gaap_bridge')}
            >
              Bridge
              <span className="review-tab__badge">{bridgeCount}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'cash_flow'}
              className={`review-tab ${activeTab === 'cash_flow' ? 'review-tab--active' : ''}`}
              onClick={() => handleTabChange('cash_flow')}
            >
              CF
              <span className="review-tab__badge">{cfCount}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'balance_sheet'}
              className={`review-tab ${activeTab === 'balance_sheet' ? 'review-tab--active' : ''}`}
              onClick={() => handleTabChange('balance_sheet')}
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
                onClick={() => handleTabChange('kpi')}
              >
                KPI
                <span className="review-tab__badge">{kpiCount}</span>
              </button>
            )}
            {/* Footnote schedules get their own tab so they never push the item list down (AUD-019). */}
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'footnotes'}
              className={`review-tab ${activeTab === 'footnotes' ? 'review-tab--active' : ''}`}
              onClick={() => handleTabChange('footnotes')}
            >
              Footnotes
            </button>
          </div>
          {/* ── Statement Readiness Indicators (Ticket D.2.2) ── */}
          {items.length > 0 && (
            <div className="review-readiness-chips">
              <span className={`review-readiness-chip ${isNeedsReview ? 'review-readiness-chip--review' : 'review-readiness-chip--ready'}`}>
                {isNeedsReview ? <AlertCircle size={12} aria-hidden="true" /> : <CheckCircle2 size={12} aria-hidden="true" />}
                <span>IS: {isNeedsReview ? 'Review needed' : 'Ready'}</span>
              </span>
              <span className={`review-readiness-chip ${bridgeNeedsReview ? 'review-readiness-chip--review' : 'review-readiness-chip--ready'}`}>
                {bridgeNeedsReview ? <AlertCircle size={12} aria-hidden="true" /> : <CheckCircle2 size={12} aria-hidden="true" />}
                <span>Bridge: {bridgeNeedsReview ? 'Review needed' : 'Ready'}</span>
              </span>
              <span className={`review-readiness-chip ${cfNeedsReview ? 'review-readiness-chip--review' : 'review-readiness-chip--ready'}`}>
                {cfNeedsReview ? <AlertCircle size={12} aria-hidden="true" /> : <CheckCircle2 size={12} aria-hidden="true" />}
                <span>CF: {cfNeedsReview ? 'Review needed' : 'Ready'}</span>
              </span>
              <span className={`review-readiness-chip ${bsNeedsReview ? 'review-readiness-chip--review' : 'review-readiness-chip--ready'}`}>
                {bsNeedsReview ? <AlertCircle size={12} aria-hidden="true" /> : <CheckCircle2 size={12} aria-hidden="true" />}
                <span>BS: {bsNeedsReview ? 'Review needed' : 'Ready'}</span>
              </span>
            </div>
          )}

          <div ref={listScrollRef} className="review-sidebar__scroll-container" style={{ position: 'relative' }}>
          {activeTab === 'footnotes' ? (
            <div className="review-footnotes" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <p style={{ margin: '4px 2px', fontSize: '12px', color: 'var(--ink-muted)' }}>
                Debt, lease and concentration schedules from the filing&apos;s footnotes. Schedules that were not found are not shown.
              </p>
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
            </div>
          ) : (
          <>
          <div ref={listHeadRef} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
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
            </div>
          )}

          {/* ── Bulk Taxonomy Confirmation Panel (Ticket C-5) ── */}
          {(() => {
            const pendingTaxonomyItems = items.filter(
              (it) =>
                it.is_target_metric_candidate !== false &&
                (it.status === 'pending_taxonomy_confirmation' ||
                  it.taxonomy_status === 'pending_taxonomy_confirmation'),
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
                    marginBottom: isTaxonomyPanelCollapsed ? 0 : '8px',
                    cursor: 'pointer',
                  }}
                  onClick={() => setIsTaxonomyPanelCollapsed(!isTaxonomyPanelCollapsed)}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    {isTaxonomyPanelCollapsed ? (
                      <ChevronRight size={14} aria-hidden="true" style={{ color: '#f59e0b' }} />
                    ) : (
                      <ChevronDown size={14} aria-hidden="true" style={{ color: '#f59e0b' }} />
                    )}
                    <strong style={{ color: '#f59e0b' }}>
                      Pending Taxonomy Confirmations ({pendingTaxonomyItems.length})
                    </strong>
                  </div>
                  {!isTaxonomyPanelCollapsed && (
                    <button
                      type="button"
                      className="review-btn review-btn--edit"
                      style={{ fontSize: '11px', padding: '2px 6px' }}
                      onClick={(e) => {
                        e.stopPropagation()
                        toggleSelectAll()
                      }}
                    >
                      {allSelected ? 'Deselect All' : 'Select All'}
                    </button>
                  )}
                </div>
                {!isTaxonomyPanelCollapsed && (
                  <>
                    <div
                      style={{
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
                  </>
                )}
              </div>
            )
          })()}
          </div>

          {!itemsLoading && !itemsError && filteredItems.length > 0 && (
            <div
              className="review-sidebar__list"
              role="listbox"
              aria-label="Extracted items list"
              style={{ position: 'relative', height: rowVirtualizer.getTotalSize(), flexShrink: 0 }}
            >
              {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                const row = listRows[virtualRow.index]
                return (
                  <div
                    key={virtualRow.key}
                    data-index={virtualRow.index}
                    ref={rowVirtualizer.measureElement}
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      paddingBottom: '6px',
                      transform: `translateY(${virtualRow.start - rowVirtualizer.options.scrollMargin}px)`,
                    }}
                  >
                    {row.kind === 'table' ? (
                    <div className="review-table-header" title={`Table: ${row.tableName}`}>
                      <span className="review-table-header__icon"><Table2 size={13} aria-hidden="true" /></span>
                      <span className="review-table-header__title">{row.tableName}</span>
                    </div>
                    ) : (() => {
                      const item = row.item
                      const isSelected = selectedItem?.id === item.id
                      const isEditing = editingItemId === item.id
                      const isCandidate = item.is_target_metric_candidate !== false

                      return (
                        <div
                          key={item.id}
                          data-item-id={item.id}
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
                      <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                        <ItemStatusVisual status={item.status} />
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
                      <span className="review-item-card__value fn-tabular tabular-nums">{item.value}</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span className="review-item-card__page">Page {item.page}</span>
                        <SourceChip
                          sourceFile={item.source_file || 'filing.pdf'}
                          page={item.page}
                          bbox={item.bbox}
                          label={item.label}
                          value={item.value}
                          onJumpToSource={(p) => {
                            setCurrentPage(p)
                            handleSelectItem(item)
                          }}
                        />
                      </div>
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
                            className="fn-btn fn-btn--secondary fn-btn--sm review-btn review-btn--edit"
                            onClick={handleCancelEdit}
                            disabled={isActionPending}
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            className="fn-btn fn-btn--primary fn-btn--sm review-btn review-btn--confirm"
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
                          className="fn-btn fn-btn--secondary fn-btn--sm review-btn review-btn--unlock"
                          disabled={isActionPending}
                          onClick={() => void handleUnlock(item)}
                          title="Unlock item to permit edits"
                        >
                          <LockOpen size={12} aria-hidden="true" />
                          <span>Unlock</span>
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
                          className="fn-btn fn-btn--secondary fn-btn--sm review-btn review-btn--confirm"
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
                          <Check size={12} aria-hidden="true" />
                          <span>Confirm</span>
                        </button>
                        <button
                          type="button"
                          className="fn-btn fn-btn--secondary fn-btn--sm review-btn review-btn--edit"
                          disabled={isActionPending}
                          onClick={() => handleStartEdit(item)}
                        >
                          <Edit2 size={12} aria-hidden="true" />
                          <span>Edit</span>
                        </button>
                        <button
                          type="button"
                          className={`fn-btn fn-btn--secondary fn-btn--sm review-btn review-btn--flag ${item.status === 'flagged' ? 'review-btn--flagged' : ''}`}
                          disabled={isActionPending}
                          onClick={() => void handleFlag(item)}
                        >
                          <Flag size={12} aria-hidden="true" />
                          <span>{item.status === 'flagged' ? 'Flagged' : 'Flag'}</span>
                        </button>
                      </div>
                      )}
                    </div>
                  )
                    })()}
                  </div>
                )
              })}
            </div>
          )}
          </>
          )}
          </div>
        </aside>

        {/* ── Resizable Split Pane Divider (FN-062) ── */}
        <div
          className="review-resizer"
          onMouseDown={handleMouseDownResizer}
          title="Drag to resize pane"
        />

        {/* ── Right Document Viewer (PDF or HTML) ── */}
        <main className="review-viewer" aria-label="Document Viewer" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div className="review-viewer__toolbar" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 16px', borderBottom: '1px solid var(--border)', backgroundColor: 'var(--surface)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button
                type="button"
                className="fn-btn fn-btn--ghost fn-btn--sm"
                disabled={currentPage <= 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                aria-label="Previous page"
              >
                ‹
              </button>
              <div className="review-viewer__page-info" style={{ fontSize: '12px', fontWeight: 500 }}>
                {pdfDoc ? `Page ${currentPage} of ${pdfDoc.numPages}` : 'Loading document...'}
              </div>
              <button
                type="button"
                className="fn-btn fn-btn--ghost fn-btn--sm"
                disabled={!pdfDoc || currentPage >= pdfDoc.numPages}
                onClick={() => setCurrentPage((p) => Math.min(pdfDoc?.numPages || p, p + 1))}
                aria-label="Next page"
              >
                ›
              </button>
            </div>

            {/* Zoom Controls & Source Indicator */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <button
                  type="button"
                  className="fn-btn fn-btn--ghost fn-btn--sm"
                  onClick={() => setZoomScale(zoomOut)}
                  title="Zoom out"
                  aria-label="Zoom out"
                >
                  <ZoomOut size={13} aria-hidden="true" />
                </button>
                <span style={{ fontSize: '11px', minWidth: '38px', textAlign: 'center', color: 'var(--ink-muted)' }}>
                  {Math.round(zoomScale * 100)}%
                </span>
                <button
                  type="button"
                  className="fn-btn fn-btn--ghost fn-btn--sm"
                  onClick={() => setZoomScale(zoomIn)}
                  title="Zoom in"
                  aria-label="Zoom in"
                >
                  <ZoomIn size={13} aria-hidden="true" />
                </button>
                <button
                  type="button"
                  className="fn-btn fn-btn--ghost fn-btn--sm"
                  onClick={() => void handleFitWidth()}
                  disabled={!pdfDoc}
                  title="Fit width"
                  aria-label="Fit width"
                >
                  <Maximize2 size={13} aria-hidden="true" />
                </button>
              </div>

              {selectedItem && (
                <div style={{ fontSize: '11px', color: 'var(--ink-muted)', borderLeft: '1px solid var(--border)', paddingLeft: '8px' }}>
                  Source: {selectedItem.source_file}
                </div>
              )}
            </div>
          </div>

          {/* Viewer Stage: HTML (FN-032) or PDF with Single Item Sweep (FN-062) */}
          {selectedItem?.locator?.type === 'html' ? (
            // AUD-018 / D9: HTML-sourced items link out to the filing on sec.gov. (The previous
            // iframe pointed at a route that does not exist, with an allow-same-origin +
            // allow-scripts sandbox.) The viewer is chosen by locator type, not file extension.
            (() => {
              const loc = selectedItem.locator
              const href = secSourceLink(loc, selectedItem.label)
              return (
                <div className="review-viewer__stage review-html-source" style={{ padding: '24px', flex: 1, overflow: 'auto' }}>
                  <h3 style={{ marginTop: 0 }}>Source: SEC EDGAR HTML filing</h3>
                  <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '4px 12px', fontSize: '13px' }}>
                    <dt>Document</dt>
                    <dd style={{ margin: 0 }}>{loc.document}</dd>
                    <dt>Accession</dt>
                    <dd style={{ margin: 0 }}>{loc.accession}</dd>
                    <dt>Element</dt>
                    <dd style={{ margin: 0 }}>
                      <code>{loc.element_path}</code>
                    </dd>
                  </dl>
                  {href ? (
                    <a className="fn-btn fn-btn--primary fn-btn--sm" href={href} target="_blank" rel="noopener noreferrer">
                      Open on sec.gov
                    </a>
                  ) : (
                    <p role="note" style={{ fontSize: '13px', color: 'var(--ink-muted)' }}>
                      No sec.gov link: the filer&apos;s CIK is not recorded for this item.
                    </p>
                  )}
                </div>
              )
            })()
          ) : (
            <div ref={stageRef} className="review-viewer__stage" style={{ flex: 1, overflow: 'auto', padding: '16px', display: 'flex' }}>
              {pdfLoading && (
                <div className="review-viewer__loading">
                  <div className="review-viewer__spinner" />
                  <span>Loading source PDF...</span>
                </div>
              )}

              {pdfError && (
                <div className="review-viewer__error" role="alert">
                  <h3>Source PDF Unavailable</h3>
                  <p>{pdfError}</p>
                </div>
              )}

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
                  position: 'relative',
                  backgroundColor: '#ffffff',
                  boxShadow: 'var(--fn-shadow-md)',
                  borderRadius: '2px',
                  // Auto margins centre the page but, unlike justify-content: center, never push
                  // a zoomed page past the stage's left edge where it cannot be scrolled to.
                  margin: '0 auto',
                  flexShrink: 0,
                  alignSelf: 'flex-start',
                }}
              >
                <canvas ref={canvasRef} className="review-viewer__canvas" />
                {canvasSize.width > 0 && selectedItem && selectedItem.page === currentPage && (
                  <div
                    className="review-viewer__overlay"
                    style={{ width: canvasSize.width, height: canvasSize.height, position: 'absolute', inset: 0, pointerEvents: 'none' }}
                  >
                    {(() => {
                      const pixelBox = normalizeBboxToPixels(
                        selectedItem.bbox,
                        canvasSize.width,
                        canvasSize.height,
                      )
                      return (
                        <div
                          ref={highlightRef}
                          role="img"
                          aria-label={`Highlight for ${selectedItem.label}: ${selectedItem.value}`}
                          className="review-highlight-single"
                          style={{
                            left: `${pixelBox.left}px`,
                            top: `${pixelBox.top}px`,
                            width: `${pixelBox.width}px`,
                            height: `${pixelBox.height}px`,
                          }}
                          title={`${selectedItem.label}: ${selectedItem.value}`}
                        />
                      )
                    })()}
                  </div>
                )}
              </div>
            </div>
          )}
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

      {/* ── Keyboard Shortcuts Sheet Modal (FN-062) ── */}
      {showShortcutModal && (
        <div
          className="review-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="Keyboard Shortcuts"
          onClick={() => setShowShortcutModal(false)}
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(20, 18, 15, 0.45)',
            backdropFilter: 'blur(3px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
          }}
        >
          <div
            className="review-modal"
            onClick={(e) => e.stopPropagation()}
            style={{
              backgroundColor: 'var(--surface)',
              borderRadius: 'var(--fn-radius-lg)',
              border: '1px solid var(--border)',
              boxShadow: 'var(--fn-shadow-lg)',
              padding: '20px 24px',
              maxWidth: '420px',
              width: '100%',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 600, color: 'var(--ink)' }}>Keyboard Shortcuts</h3>
              <button
                type="button"
                onClick={() => setShowShortcutModal(false)}
                className="fn-btn fn-btn--ghost fn-btn--sm"
                aria-label="Close shortcuts"
              >
                ✕
              </button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '13px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--ink-secondary)' }}>Next line item</span>
                <kbd style={{ padding: '2px 8px', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: '4px', fontWeight: 600 }}>J</kbd>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--ink-secondary)' }}>Previous line item</span>
                <kbd style={{ padding: '2px 8px', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: '4px', fontWeight: 600 }}>K</kbd>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--ink-secondary)' }}>Accept / confirm item</span>
                <kbd style={{ padding: '2px 8px', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: '4px', fontWeight: 600 }}>Y</kbd>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--ink-secondary)' }}>Edit item</span>
                <kbd style={{ padding: '2px 8px', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: '4px', fontWeight: 600 }}>E</kbd>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--ink-secondary)' }}>Cancel / Close</span>
                <kbd style={{ padding: '2px 8px', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: '4px', fontWeight: 600 }}>Esc</kbd>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--ink-secondary)' }}>Shortcut help sheet</span>
                <kbd style={{ padding: '2px 8px', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: '4px', fontWeight: 600 }}>?</kbd>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
