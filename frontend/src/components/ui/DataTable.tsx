import React from 'react'

export interface ColumnDef<T> {
  key: string
  header: string
  align?: 'left' | 'center' | 'right'
  isNumeric?: boolean
  render?: (item: T, index: number) => React.ReactNode
  width?: string | number
}

export interface DataTableProps<T> {
  columns: ColumnDef<T>[]
  data: T[]
  keyExtractor: (item: T, index: number) => string
  emptyMessage?: string
  className?: string
  style?: React.CSSProperties
  zebra?: boolean
}

export function DataTable<T>({
  columns,
  data,
  keyExtractor,
  emptyMessage = 'No records found',
  className = '',
  style,
  zebra = true,
}: DataTableProps<T>) {
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
            }}
          >
            {columns.map((col) => (
              <th
                key={col.key}
                style={{
                  padding: '10px 14px',
                  fontWeight: 600,
                  fontSize: 'var(--fn-text-12)',
                  color: 'var(--ink-secondary)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                  textAlign: col.align || (col.isNumeric ? 'right' : 'left'),
                  width: col.width,
                }}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
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
            data.map((item, rowIdx) => (
              <tr
                key={keyExtractor(item, rowIdx)}
                style={{
                  borderBottom: '1px solid var(--border)',
                  backgroundColor: zebra && rowIdx % 2 === 1 ? 'var(--surface-2)' : 'transparent',
                  transition: 'background-color var(--fn-motion-hover)',
                }}
                className="fn-table-row"
              >
                {columns.map((col) => {
                  const val = (item as Record<string, unknown>)[col.key]
                  const textAlign = col.align || (col.isNumeric ? 'right' : 'left')
                  return (
                    <td
                      key={col.key}
                      style={{
                        padding: '10px 14px',
                        textAlign,
                        fontVariantNumeric: col.isNumeric ? 'tabular-nums' : undefined,
                        fontFamily: col.isNumeric ? 'var(--fn-font-mono)' : 'inherit',
                        color: 'var(--ink)',
                      }}
                    >
                      {col.render ? col.render(item, rowIdx) : String(val ?? '')}
                    </td>
                  )
                })}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
