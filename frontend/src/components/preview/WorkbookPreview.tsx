import React, { useState, useEffect } from 'react'
import { Download, CheckCircle2, AlertCircle, FileSpreadsheet, ExternalLink } from 'lucide-react'
import { Button } from '../ui/Button'
import { Badge } from '../ui/Badge'

export interface CheckItem {
  id: string
  name: string
  passed: boolean
  detail?: string
}

export interface WorkbookRow {
  rowNumber: number
  label: string
  value: number | string | null
  formula?: string
  status?: 'verified' | 'auto_accepted' | 'needs_review' | 'manual_required'
  comment?: string
  sourcePage?: number
  isTotal?: boolean
  isHeader?: boolean
}

export interface WorkbookPreviewProps {
  jobId: string
  companyName: string
  period?: string
  sheetName?: string
  statusHeader?: string
  checks?: CheckItem[]
  rows?: WorkbookRow[]
  onExportExcel: () => void
  isExporting?: boolean
  onCellClick?: (row: WorkbookRow) => void
}

import { DEFAULT_SAMPLE_ROWS, DEFAULT_CHECKS } from './sampleData'

export default function WorkbookPreview({
  jobId,
  companyName,
  period = 'FY2025',
  sheetName = 'EBITDA_Bridge',
  statusHeader,
  checks = DEFAULT_CHECKS,
  rows = DEFAULT_SAMPLE_ROWS,
  onExportExcel,
  isExporting = false,
  onCellClick,
}: WorkbookPreviewProps) {
  const [selectedRowIndex, setSelectedRowIndex] = useState<number>(0)
  const [celebrate, setCelebrate] = useState<boolean>(true)

  // Calculate check counts
  const totalChecks = checks.length
  const passedChecks = checks.filter((c) => c.passed).length
  const allChecksPassed = totalChecks > 0 && passedChecks === totalChecks

  // Compute status header if not supplied
  const unverifiedCount = rows.filter(
    (r) => r.status === 'needs_review' || r.status === 'manual_required',
  ).length
  const computedStatus =
    statusHeader ?? (unverifiedCount === 0 ? 'VERIFIED' : `DRAFT: ${unverifiedCount} item${unverifiedCount === 1 ? '' : 's'} unverified`)

  // Restrained celebration transition timer
  useEffect(() => {
    const timer = setTimeout(() => {
      setCelebrate(false)
    }, 4500)
    return () => clearTimeout(timer)
  }, [])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedRowIndex((prev) => Math.min(rows.length - 1, prev + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedRowIndex((prev) => Math.max(0, prev - 1))
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      if (rows[selectedRowIndex] && onCellClick) {
        onCellClick(rows[selectedRowIndex])
      }
    }
  }

  const selectedRow = rows[selectedRowIndex]

  return (
    <div
      className="fn-workbook-preview fn-card"
      data-job-id={jobId}
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--fn-radius-lg)',
        boxShadow: 'var(--fn-shadow-md)',
        overflow: 'hidden',
        fontFamily: 'var(--fn-font-sans)',
      }}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      role="region"
      aria-label="Workbook preview and export"
    >
      {/* ── Top Bar: Check Summary, Payoff Moment, and Export Action ── */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem',
          padding: '1rem 1.25rem',
          backgroundColor: 'var(--surface-2)',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <FileSpreadsheet size={20} style={{ color: 'var(--accent)' }} aria-hidden="true" />
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontWeight: 600, fontSize: '0.95rem', color: 'var(--ink)' }}>
                {sheetName}
              </span>
              <Badge variant={computedStatus === 'VERIFIED' ? 'ok' : 'warn'}>
                {computedStatus}
              </Badge>
            </div>
            <div style={{ fontSize: '0.8rem', color: 'var(--ink-muted)', marginTop: '2px' }}>
              {companyName} · {period}
            </div>
          </div>
        </div>

        {/* Check summary and Payoff Badge */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '0.85rem',
              color: allChecksPassed ? 'var(--ok)' : 'var(--warn)',
              fontWeight: 500,
            }}
          >
            {allChecksPassed ? (
              <CheckCircle2 size={16} aria-hidden="true" />
            ) : (
              <AlertCircle size={16} aria-hidden="true" />
            )}
            <span>
              {passedChecks}/{totalChecks} checks passed
            </span>
          </div>

          {/* Celebratory but restrained payoff badge */}
          {celebrate && (
            <div
              className="fn-payoff-moment"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 10px',
                borderRadius: 'var(--fn-radius-sm)',
                backgroundColor: 'rgba(31, 138, 91, 0.12)',
                border: '1px solid var(--ok)',
                color: 'var(--ok)',
                fontSize: '0.8rem',
                fontWeight: 600,
                animation: 'fn-fade-in 280ms ease-out',
              }}
            >
              <span>✦ Ready for modeling</span>
            </div>
          )}

          {/* Primary Export to Excel action */}
          <Button
            variant="primary"
            disabled={isExporting}
            onClick={onExportExcel}
            aria-label="Export to Excel"
          >
            <Download size={14} aria-hidden="true" />
            <span>{isExporting ? 'Exporting...' : 'Export to Excel'}</span>
          </Button>
        </div>
      </div>

      {/* ── Read-only Excel Grid Spec Preview ── */}
      <div
        style={{
          overflowX: 'auto',
          maxHeight: '420px',
          overflowY: 'auto',
          backgroundColor: 'var(--surface)',
        }}
      >
        <table
          role="grid"
          aria-label="Workbook preview grid"
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: 'var(--fn-text-13)',
            fontFamily: 'var(--fn-font-sans)',
          }}
        >
          <thead>
            <tr
              style={{
                backgroundColor: 'var(--surface-2)',
                borderBottom: '1px solid var(--border)',
                position: 'sticky',
                top: 0,
                zIndex: 1,
              }}
            >
              <th
                style={{
                  width: '50px',
                  padding: '6px 10px',
                  textAlign: 'center',
                  color: 'var(--ink-muted)',
                  fontSize: '11px',
                  borderRight: '1px solid var(--border)',
                }}
              >
                #
              </th>
              <th
                style={{
                  padding: '8px 14px',
                  textAlign: 'left',
                  color: 'var(--ink-secondary)',
                  fontWeight: 600,
                  fontSize: '11px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                }}
              >
                Col A (Line Item)
              </th>
              <th
                style={{
                  width: '160px',
                  padding: '8px 14px',
                  textAlign: 'right',
                  color: 'var(--ink-secondary)',
                  fontWeight: 600,
                  fontSize: '11px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                }}
              >
                Col B ({period})
              </th>
              <th
                style={{
                  width: '160px',
                  padding: '8px 14px',
                  textAlign: 'left',
                  color: 'var(--ink-secondary)',
                  fontWeight: 600,
                  fontSize: '11px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                }}
              >
                Provenance / Formula
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => {
              const isSelected = selectedRowIndex === idx
              const isManualRequired = row.status === 'manual_required'
              const isNeedsReview = row.status === 'needs_review'

              // Styling per Invariant I3:
              // - uncertain cells yellow (#FEF08A)
              // - manual-required empty with red fill (#FEE2E2)
              let cellBg = 'transparent'
              let cellColor = 'var(--ink)'
              if (isManualRequired) {
                cellBg = 'rgba(194, 65, 12, 0.12)'
                cellColor = 'var(--danger)'
              } else if (isNeedsReview) {
                cellBg = 'rgba(255, 230, 128, 0.35)'
              }

              return (
                <tr
                  key={row.rowNumber}
                  role="row"
                  aria-selected={isSelected}
                  onClick={() => {
                    setSelectedRowIndex(idx)
                    if (onCellClick) onCellClick(row)
                  }}
                  style={{
                    borderBottom: '1px solid var(--border)',
                    backgroundColor: isSelected
                      ? 'rgba(43, 75, 238, 0.08)'
                      : row.isTotal
                        ? 'var(--surface-2)'
                        : 'transparent',
                    cursor: 'pointer',
                    fontWeight: row.isTotal ? 600 : 400,
                  }}
                >
                  {/* Row Number */}
                  <td
                    style={{
                      padding: '8px 10px',
                      textAlign: 'center',
                      color: 'var(--ink-muted)',
                      fontSize: '11px',
                      borderRight: '1px solid var(--border)',
                      backgroundColor: 'var(--surface-2)',
                      userSelect: 'none',
                    }}
                  >
                    {row.rowNumber}
                  </td>

                  {/* Col A: Label */}
                  <td
                    style={{
                      padding: '8px 14px',
                      color: 'var(--ink)',
                      paddingLeft: row.isTotal ? '14px' : '24px',
                    }}
                  >
                    {row.label}
                  </td>

                  {/* Col B: Value */}
                  <td
                    className="fn-tabular tabular-nums"
                    style={{
                      padding: '8px 14px',
                      textAlign: 'right',
                      fontFamily: 'var(--fn-font-mono)',
                      backgroundColor: cellBg,
                      color: cellColor,
                      borderLeft: isNeedsReview || isManualRequired ? '2px solid var(--warn)' : 'none',
                    }}
                    title={row.comment}
                  >
                    {isManualRequired ? (
                      <span
                        style={{
                          fontSize: '11px',
                          color: 'var(--danger)',
                          fontStyle: 'italic',
                          fontWeight: 500,
                        }}
                      >
                        [Manual Required]
                      </span>
                    ) : typeof row.value === 'number' ? (
                      row.value < 0 ? `(${Math.abs(row.value).toLocaleString()})` : row.value.toLocaleString()
                    ) : (
                      row.value || '—'
                    )}
                  </td>

                  {/* Provenance / Formula */}
                  <td
                    style={{
                      padding: '8px 14px',
                      fontSize: '11px',
                      color: 'var(--ink-muted)',
                      fontFamily: row.formula ? 'var(--fn-font-mono)' : 'inherit',
                    }}
                  >
                    {row.formula ? (
                      <span style={{ color: 'var(--accent)', fontWeight: 500 }}>{row.formula}</span>
                    ) : row.sourcePage ? (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                        <span>p.{row.sourcePage}</span>
                        <ExternalLink size={10} aria-hidden="true" />
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* ── Active Cell Inspector Footer ── */}
      {selectedRow && (
        <div
          style={{
            padding: '8px 16px',
            backgroundColor: 'var(--surface-2)',
            borderTop: '1px solid var(--border)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            fontSize: '12px',
            color: 'var(--ink-secondary)',
          }}
        >
          <div>
            <strong>Row {selectedRow.rowNumber}:</strong> {selectedRow.label}
            {selectedRow.formula && (
              <span style={{ marginLeft: '8px', color: 'var(--accent)', fontFamily: 'var(--fn-font-mono)' }}>
                Formula: {selectedRow.formula}
              </span>
            )}
            {selectedRow.comment && (
              <span style={{ marginLeft: '8px', color: 'var(--warn)' }}>
                ⚠ {selectedRow.comment}
              </span>
            )}
          </div>
          <div style={{ color: 'var(--ink-muted)', fontSize: '11px' }}>
            Use ↑/↓ arrows to navigate rows
          </div>
        </div>
      )}
    </div>
  )
}
