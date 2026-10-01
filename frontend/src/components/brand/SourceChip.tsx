import React, { useState } from 'react'
import { FileText, ExternalLink } from 'lucide-react'

export interface BoundingBox {
  x0: number
  y0: number
  x1: number
  y1: number
}

export interface SourceChipProps {
  sourceFile: string
  page: number
  bbox?: BoundingBox
  snippet?: string
  label?: string
  value?: string | number
  marker?: string
  onJumpToSource?: (page: number, bbox?: BoundingBox) => void
  className?: string
  style?: React.CSSProperties
}

export const SourceChip: React.FC<SourceChipProps> = ({
  sourceFile,
  page,
  bbox,
  snippet,
  label,
  value,
  marker,
  onJumpToSource,
  className = '',
  style,
}) => {
  const [isOpen, setIsOpen] = useState(false)

  const displayMarker = marker || `p.${page}`

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    onJumpToSource?.(page, bbox)
  }

  return (
    <div
      className="fn-source-chip-wrapper"
      onMouseEnter={() => setIsOpen(true)}
      onMouseLeave={() => setIsOpen(false)}
      style={{ display: 'inline-flex', verticalAlign: 'baseline', ...style }}
    >
      <button
        type="button"
        className={`fn-source-chip ${className}`}
        onClick={handleClick}
        onFocus={() => setIsOpen(true)}
        onBlur={() => setIsOpen(false)}
        aria-label={`View source citation: ${sourceFile}, page ${page}${label ? ` for ${label}` : ''}`}
        aria-expanded={isOpen}
      >
        <span style={{ fontSize: '10px', opacity: 0.85 }}>[</span>
        <span>{displayMarker}</span>
        <span style={{ fontSize: '10px', opacity: 0.85 }}>]</span>
      </button>

      {isOpen && (
        <div
          role="dialog"
          aria-label="Filing Source Citation"
          className="fn-source-chip__popover"
        >
          <div className="fn-source-chip__popover-title">
            <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <FileText size={13} style={{ color: 'var(--accent)' }} />
              <strong style={{ fontSize: '12px' }}>{sourceFile}</strong>
            </span>
            <span
              style={{
                fontSize: '11px',
                padding: '1px 5px',
                borderRadius: 'var(--fn-radius-sm)',
                backgroundColor: 'var(--surface-2)',
                color: 'var(--ink-secondary)',
                fontFamily: 'var(--fn-font-mono)',
              }}
            >
              Page {page}
            </span>
          </div>

          {(label || value !== undefined) && (
            <div
              style={{
                fontSize: '11px',
                color: 'var(--ink-muted)',
                marginBottom: '6px',
                display: 'flex',
                justifyContent: 'space-between',
              }}
            >
              <span>{label}</span>
              {value !== undefined && <strong className="tabular-nums" style={{ color: 'var(--ink)' }}>{value}</strong>}
            </div>
          )}

          {snippet ? (
            <div className="fn-source-chip__popover-snippet">
              &ldquo;{snippet}&rdquo;
            </div>
          ) : (
            <div
              className="fn-source-chip__popover-snippet"
              style={{ fontStyle: 'italic', color: 'var(--ink-muted)' }}
            >
              Verified figure citation tied to bounding box coordinates on page {page}.
            </div>
          )}

          <div
            className="fn-source-chip__popover-footer"
            onClick={handleClick}
            style={{ cursor: 'pointer' }}
          >
            <span>Jump to PDF citation</span>
            <ExternalLink size={11} aria-hidden="true" />
          </div>
        </div>
      )}
    </div>
  )
}
