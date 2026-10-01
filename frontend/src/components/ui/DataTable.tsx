import React, { useState, useRef, useCallback } from 'react'

export interface ColumnDef<T> {
  key: string
  header: string
  units?: string
  align?: 'left' | 'center' | 'right'
  isNumeric?: boolean
  truncate?: boolean
  width?: string | number
  minWidth?: number
  render?: (item: T, index: number) => React.ReactNode
}

export interface DataTableProps<T> {
  columns: ColumnDef<T>[]
  data: T[]
  keyExtractor: (item: T, index: number) => string
  emptyMessage?: string
  className?: string
  style?: React.CSSProperties
  zebra?: boolean
  stickyHeader?: boolean
  resizable?: boolean
  selectable?: boolean
  selectedKeys?: Set<string>
  onSelectionChange?: (keys: Set<string>) => void
  onRowClick?: (item: T, index: number) => void
}

import { formatNegativeInParens } from '../../lib/formatters'

export function DataTable<T>({
  columns,
  data,
  keyExtractor,
  emptyMessage = 'No records found',
  className = '',
  style,
  zebra = true,
  stickyHeader = true,
  resizable = true,
  selectable = false,
  selectedKeys,
  onSelectionChange,
  onRowClick,
}: DataTableProps<T>) {
  const [colWidths, setColWidths] = useState<Record<string, number>>({})
  const resizingCol = useRef<{ key: string; startX: number; startWidth: number } | null>(null)

  const handleMouseDownResize = useCallback(
    (key: string, e: React.MouseEvent) => {
      e.preventDefault()
      e.stopPropagation()
      const th = (e.currentTarget.parentElement as HTMLElement)
      const startWidth = th ? th.offsetWidth : 120
      resizingCol.current = { key, startX: e.clientX, startWidth }

      const handleMouseMove = (moveEvent: MouseEvent) => {
        if (!resizingCol.current) return
        const diff = moveEvent.clientX - resizingCol.current.startX
        const newWidth = Math.max(50, resizingCol.current.startWidth + diff)
        setColWidths((prev) => ({ ...prev, [resizingCol.current!.key]: newWidth }))
      }

      const handleMouseUp = () => {
        resizingCol.current = null
        window.removeEventListener('mousemove', handleMouseMove)
        window.removeEventListener('mouseup', handleMouseUp)
      }

      window.addEventListener('mousemove', handleMouseMove)
      window.addEventListener('mouseup', handleMouseUp)
    },
    [],
  )

  const allSelected = selectable && data.length > 0 && selectedKeys && data.every((d, i) => selectedKeys.has(keyExtractor(d, i)))
  const someSelected =
    selectable &&
    selectedKeys &&
    selectedKeys.size > 0 &&
    !allSelected &&
    data.some((d, i) => selectedKeys.has(keyExtractor(d, i)))

  const handleSelectAll = () => {
    if (!onSelectionChange) return
    if (allSelected) {
      onSelectionChange(new Set())
    } else {
      const next = new Set<string>()
      data.forEach((d, i) => next.add(keyExtractor(d, i)))
      onSelectionChange(next)
    }
  }

  const handleRowSelect = (key: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!onSelectionChange || !selectedKeys) return
    const next = new Set(selectedKeys)
    if (next.has(key)) {
      next.delete(key)
    } else {
      next.add(key)
    }
    onSelectionChange(next)
  }

  return (
    <div
      className={`fn-data-table-container ${className}`}
      style={{
        width: '100%',
        overflowX: 'auto',
        border: '1px solid var(--border)',
        borderRadius: 'var(--fn-radius-md)',
        backgroundColor: 'var(--surface)',
        boxShadow: 'var(--fn-shadow-sm)',
        ...style,
      }}
    >
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          textAlign: 'left',
          fontSize: 'var(--fn-text-13)',
          fontFamily: 'var(--fn-font-sans)',
        }}
      >
        <thead>
          <tr
            style={{
              backgroundColor: 'var(--surface-2)',
              borderBottom: '1px solid var(--border)',
              position: stickyHeader ? 'sticky' : 'static',
              top: 0,
              zIndex: 2,
            }}
          >
            {selectable && (
              <th
                style={{
                  width: '40px',
                  padding: '10px 12px',
                  textAlign: 'center',
                  backgroundColor: 'var(--surface-2)',
                }}
              >
                <input
                  type="checkbox"
                  checked={Boolean(allSelected)}
                  ref={(el) => {
                    if (el) el.indeterminate = Boolean(someSelected)
                  }}
                  onChange={handleSelectAll}
                  aria-label="Select all rows"
                  style={{ cursor: 'pointer', accentColor: 'var(--accent)' }}
                />
              </th>
            )}
            {columns.map((col) => {
              const textAlign = col.align || (col.isNumeric ? 'right' : 'left')
              const width = colWidths[col.key] || col.width
              return (
                <th
                  key={col.key}
                  style={{
                    padding: '10px 14px',
                    fontWeight: 600,
                    fontSize: 'var(--fn-text-12)',
                    color: 'var(--ink-secondary)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                    textAlign,
                    width,
                    minWidth: col.minWidth,
                    position: 'relative',
                    userSelect: 'none',
                    backgroundColor: 'var(--surface-2)',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'baseline',
                      gap: '4px',
                      justifyContent: textAlign === 'right' ? 'flex-end' : textAlign === 'center' ? 'center' : 'flex-start',
                    }}
                  >
                    <span>{col.header}</span>
                    {col.units && (
                      <span
                        className="fn-table-units"
                        style={{
                          fontSize: '10px',
                          color: 'var(--ink-muted)',
                          textTransform: 'none',
                          fontWeight: 400,
                        }}
                      >
                        {col.units}
                      </span>
                    )}
                  </div>
                  {resizable && (
                    <div
                      onMouseDown={(e) => handleMouseDownResize(col.key, e)}
                      style={{
                        position: 'absolute',
                        right: 0,
                        top: 0,
                        bottom: 0,
                        width: '6px',
                        cursor: 'col-resize',
                        userSelect: 'none',
                        zIndex: 3,
                      }}
                      title="Resize column"
                    />
                  )}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {data.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length + (selectable ? 1 : 0)}
                style={{
                  padding: '32px 16px',
                  textAlign: 'center',
                  color: 'var(--ink-muted)',
                  fontSize: 'var(--fn-text-13)',
                }}
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            data.map((item, rowIdx) => {
              const rowKey = keyExtractor(item, rowIdx)
              const isSelected = selectedKeys?.has(rowKey)
              return (
                <tr
                  key={rowKey}
                  onClick={() => onRowClick && onRowClick(item, rowIdx)}
                  style={{
                    borderBottom: '1px solid var(--border)',
                    backgroundColor: isSelected
                      ? 'rgba(43, 75, 238, 0.08)'
                      : zebra && rowIdx % 2 === 1
                        ? 'var(--surface-2)'
                        : 'transparent',
                    transition: 'background-color var(--fn-motion-hover)',
                    cursor: onRowClick ? 'pointer' : 'default',
                  }}
                  className={`fn-table-row ${isSelected ? 'fn-table-row--selected' : ''}`}
                >
                  {selectable && (
                    <td
                      style={{
                        padding: '10px 12px',
                        textAlign: 'center',
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={Boolean(isSelected)}
                        onClick={(e) => handleRowSelect(rowKey, e)}
                        onChange={() => {}}
                        aria-label={`Select row ${rowIdx + 1}`}
                        style={{ cursor: 'pointer', accentColor: 'var(--accent)' }}
                      />
                    </td>
                  )}
                  {columns.map((col) => {
                    const rawVal = (item as Record<string, unknown>)[col.key]
                    const textAlign = col.align || (col.isNumeric ? 'right' : 'left')
                    const displayVal = col.render
                      ? col.render(item, rowIdx)
                      : col.isNumeric
                        ? formatNegativeInParens(rawVal)
                        : String(rawVal ?? '')

                    const titleText =
                      typeof displayVal === 'string' || typeof displayVal === 'number'
                        ? String(displayVal)
                        : undefined

                    return (
                      <td
                        key={col.key}
                        title={col.truncate ? titleText : undefined}
                        style={{
                          padding: '10px 14px',
                          textAlign,
                          fontVariantNumeric: col.isNumeric ? 'tabular-nums' : undefined,
                          fontFamily: col.isNumeric ? 'var(--fn-font-mono)' : 'inherit',
                          color: 'var(--ink)',
                          maxWidth: col.truncate ? (colWidths[col.key] || col.width || '180px') : undefined,
                          whiteSpace: col.truncate ? 'nowrap' : undefined,
                          overflow: col.truncate ? 'hidden' : undefined,
                          textOverflow: col.truncate ? 'ellipsis' : undefined,
                        }}
                      >
                        {displayVal}
                      </td>
                    )
                  })}
                </tr>
              )
            })
          )}
        </tbody>
      </table>
    </div>
  )
}
