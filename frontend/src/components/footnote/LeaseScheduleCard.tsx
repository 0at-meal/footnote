import { useState, useEffect } from 'react'

export interface LeaseCommitmentYear {
  year_label: string
  operating_amount: number | null
  finance_amount: number | null
  total_amount: number | null
  page: number
  bbox: { x0: number; y0: number; x1: number; y1: number }
}

export interface LeaseSchedule {
  job_id: string
  company_id?: string | null
  filing_year?: number | null
  footnote_title: string
  years: LeaseCommitmentYear[]
  operating_total: number | null
  finance_total: number | null
  operating_discount_rate: number | null
  finance_discount_rate: number | null
  as_of_date?: string | null
  is_confirmed: boolean
}

interface LeaseScheduleCardProps {
  jobId: string
  apiBase: string
  onYearSelect?: (year: LeaseCommitmentYear) => void
}

export default function LeaseScheduleCard({
  jobId,
  apiBase,
  onYearSelect,
}: LeaseScheduleCardProps) {
  const [schedule, setSchedule] = useState<LeaseSchedule | null>(null)
  const [editingYearIndex, setEditingYearIndex] = useState<number | null>(null)
  const [editOperating, setEditOperating] = useState<string>('')
  const [editFinance, setEditFinance] = useState<string>('')
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [isSaving, setIsSaving] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [isConfirmed, setIsConfirmed] = useState<boolean>(false)

  useEffect(() => {
    let isMounted = true
    setIsLoading(true)
    setError(null)

    fetch(`${apiBase}/footnote/${jobId}/lease`)
      .then((res) => {
        if (!res.ok) {
          if (res.status === 404) return null
          throw new Error(`Failed to load lease schedule: HTTP ${res.status}`)
        }
        return res.json() as Promise<LeaseSchedule>
      })
      .then((data) => {
        if (isMounted && data) {
          setSchedule(data)
          setIsConfirmed(data.is_confirmed)
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Error loading lease schedule')
        }
      })
      .finally(() => {
        if (isMounted) setIsLoading(false)
      })

    return () => {
      isMounted = false
    }
  }, [jobId, apiBase])

  function handleStartEdit(idx: number, year: LeaseCommitmentYear) {
    setEditingYearIndex(idx)
    setEditOperating(year.operating_amount !== null ? String(year.operating_amount) : '')
    setEditFinance(year.finance_amount !== null ? String(year.finance_amount) : '')
  }

  function handleCancelEdit() {
    setEditingYearIndex(null)
  }

  function handleSaveEdit(idx: number) {
    if (!schedule) return

    const parsedOp = editOperating.trim() ? parseFloat(editOperating.trim()) : null
    const parsedFin = editFinance.trim() ? parseFloat(editFinance.trim()) : null

    const updatedYears = schedule.years.map((y, i) => {
      if (i !== idx) return y
      const op = isNaN(parsedOp ?? NaN) ? y.operating_amount : parsedOp
      const fin = isNaN(parsedFin ?? NaN) ? y.finance_amount : parsedFin
      const total = (op ?? 0) + (fin ?? 0)
      return {
        ...y,
        operating_amount: op,
        finance_amount: fin,
        total_amount: total > 0 ? total : null,
      }
    })

    const opTotal = updatedYears
      .map((y) => y.operating_amount ?? 0)
      .reduce((a, b) => a + b, 0)
    const finTotal = updatedYears
      .map((y) => y.finance_amount ?? 0)
      .reduce((a, b) => a + b, 0)

    setSchedule({
      ...schedule,
      years: updatedYears,
      operating_total: opTotal > 0 ? opTotal : null,
      finance_total: finTotal > 0 ? finTotal : null,
    })
    setEditingYearIndex(null)
  }

  async function handleConfirmSchedule() {
    if (!schedule) return
    setIsSaving(true)

    try {
      const res = await fetch(`${apiBase}/footnote/${jobId}/lease/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          years: schedule.years,
          operating_discount_rate: schedule.operating_discount_rate,
          finance_discount_rate: schedule.finance_discount_rate,
        }),
      })

      if (!res.ok) {
        throw new Error(`Confirm failed: HTTP ${res.status}`)
      }

      const updated = (await res.json()) as LeaseSchedule
      setSchedule(updated)
      setIsConfirmed(true)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to confirm lease schedule')
    } finally {
      setIsSaving(false)
    }
  }

  if (isLoading) {
    return (
      <div className="lease-schedule-card" style={{ padding: '0.75rem', color: '#94a3b8' }}>
        Loading Note 12 Lease Schedule...
      </div>
    )
  }

  if (error || !schedule || schedule.years.length === 0) {
    return null
  }

  return (
    <div
      className="lease-schedule-card"
      style={{
        background: 'var(--surface-raised, #1e293b)',
        border: '1px solid var(--border-color, #334155)',
        borderRadius: '8px',
        padding: '1.25rem',
        marginTop: '1rem',
        marginBottom: '1rem',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '1rem',
          borderBottom: '1px solid #334155',
          paddingBottom: '0.75rem',
        }}
      >
        <div>
          <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 600, color: '#f8fafc' }}>
            🏢 {schedule.footnote_title}
          </h3>
          <p style={{ margin: 0, fontSize: '0.8rem', color: '#94a3b8', marginTop: '2px' }}>
            ASC 842 Undiscounted Future Commitments Waterfall
          </p>
        </div>

        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          {schedule.operating_total !== null && (
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Operating Total</div>
              <strong style={{ fontSize: '0.95rem', color: '#38bdf8' }}>
                ${schedule.operating_total.toLocaleString()}
              </strong>
            </div>
          )}

          {schedule.finance_total !== null && (
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Finance Total</div>
              <strong style={{ fontSize: '0.95rem', color: '#a78bfa' }}>
                ${schedule.finance_total.toLocaleString()}
              </strong>
            </div>
          )}

          <button
            type="button"
            className="review-btn review-btn--confirm"
            disabled={isSaving || isConfirmed}
            onClick={() => void handleConfirmSchedule()}
            style={{ padding: '0.4rem 0.85rem', fontSize: '0.8rem' }}
          >
            {isConfirmed ? '✓ Confirmed' : isSaving ? 'Saving...' : 'Confirm Lease Schedule'}
          </button>
        </div>
      </div>

      {/* ── Waterfall Table ── */}
      <div style={{ overflowX: 'auto' }}>
        <table
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: '0.85rem',
            textAlign: 'left',
          }}
        >
          <thead>
            <tr style={{ color: '#94a3b8', borderBottom: '1px solid #334155' }}>
              <th style={{ padding: '6px 8px' }}>Fiscal Year / Maturity</th>
              <th style={{ padding: '6px 8px', textAlign: 'right' }}>Operating Lease ($M)</th>
              <th style={{ padding: '6px 8px', textAlign: 'right' }}>Finance Lease ($M)</th>
              <th style={{ padding: '6px 8px', textAlign: 'right' }}>Total Undiscounted ($M)</th>
              <th style={{ padding: '6px 8px', textAlign: 'right' }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {schedule.years.map((year, idx) => {
              const isEditing = editingYearIndex === idx
              return (
                <tr
                  key={idx}
                  onClick={() => onYearSelect && onYearSelect(year)}
                  style={{
                    borderBottom: '1px solid rgba(255,255,255,0.05)',
                    cursor: onYearSelect ? 'pointer' : 'default',
                  }}
                >
                  <td style={{ padding: '8px', color: '#f8fafc', fontWeight: 500 }}>
                    {year.year_label}
                  </td>

                  <td style={{ padding: '8px', textAlign: 'right', color: '#38bdf8' }}>
                    {isEditing ? (
                      <input
                        type="text"
                        value={editOperating}
                        onChange={(e) => setEditOperating(e.target.value)}
                        style={{
                          width: '75px',
                          padding: '2px 4px',
                          background: '#0f172a',
                          color: '#fff',
                          border: '1px solid #475569',
                          borderRadius: '3px',
                          fontSize: '0.8rem',
                          textAlign: 'right',
                        }}
                      />
                    ) : year.operating_amount !== null ? (
                      `$${year.operating_amount.toLocaleString()}`
                    ) : (
                      '—'
                    )}
                  </td>

                  <td style={{ padding: '8px', textAlign: 'right', color: '#a78bfa' }}>
                    {isEditing ? (
                      <input
                        type="text"
                        value={editFinance}
                        onChange={(e) => setEditFinance(e.target.value)}
                        style={{
                          width: '75px',
                          padding: '2px 4px',
                          background: '#0f172a',
                          color: '#fff',
                          border: '1px solid #475569',
                          borderRadius: '3px',
                          fontSize: '0.8rem',
                          textAlign: 'right',
                        }}
                      />
                    ) : year.finance_amount !== null ? (
                      `$${year.finance_amount.toLocaleString()}`
                    ) : (
                      '—'
                    )}
                  </td>

                  <td
                    style={{
                      padding: '8px',
                      textAlign: 'right',
                      color: '#34d399',
                      fontWeight: 600,
                    }}
                  >
                    {year.total_amount !== null ? `$${year.total_amount.toLocaleString()}` : '—'}
                  </td>

                  <td style={{ padding: '8px', textAlign: 'right' }}>
                    {isEditing ? (
                      <div style={{ display: 'inline-flex', gap: '4px' }}>
                        <button
                          type="button"
                          className="review-btn review-btn--confirm"
                          style={{ padding: '2px 6px', fontSize: '0.75rem' }}
                          onClick={(e) => {
                            e.stopPropagation()
                            handleSaveEdit(idx)
                          }}
                        >
                          Save
                        </button>
                        <button
                          type="button"
                          className="review-btn review-btn--edit"
                          style={{ padding: '2px 6px', fontSize: '0.75rem' }}
                          onClick={(e) => {
                            e.stopPropagation()
                            handleCancelEdit()
                          }}
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        className="review-btn review-btn--edit"
                        style={{ padding: '2px 6px', fontSize: '0.75rem' }}
                        onClick={(e) => {
                          e.stopPropagation()
                          handleStartEdit(idx, year)
                        }}
                      >
                        Edit
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
          {(schedule.operating_discount_rate !== null ||
            schedule.finance_discount_rate !== null) && (
            <tfoot>
              <tr style={{ borderTop: '1px solid #475569', color: '#94a3b8' }}>
                <td style={{ padding: '8px', fontWeight: 600 }}>Weighted-Avg Discount Rate</td>
                <td style={{ padding: '8px', textAlign: 'right', color: '#38bdf8' }}>
                  {schedule.operating_discount_rate !== null
                    ? `${schedule.operating_discount_rate}%`
                    : '—'}
                </td>
                <td style={{ padding: '8px', textAlign: 'right', color: '#a78bfa' }}>
                  {schedule.finance_discount_rate !== null
                    ? `${schedule.finance_discount_rate}%`
                    : '—'}
                </td>
                <td colSpan={2} />
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  )
}
