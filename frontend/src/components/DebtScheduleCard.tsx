import { useState, useEffect } from 'react'

export interface DebtTranche {
  id: string
  instrument_name: string
  principal_amount: number | null
  principal_text: string
  interest_rate: number | null
  rate_text: string
  maturity_year: number | null
  senior_subordinated: string
  is_floating: boolean
  spread: number | null
  benchmark: string | null
  page: number
  bbox: { x0: number; y0: number; x1: number; y1: number }
}

export interface DebtSchedule {
  job_id: string
  company_id?: string | null
  filing_year?: number | null
  footnote_title: string
  tranches: DebtTranche[]
  total_debt: number | null
  weighted_avg_rate: number | null
  is_confirmed: boolean
}

interface DebtScheduleCardProps {
  jobId: string
  apiBase: string
  onTrancheSelect?: (tranche: DebtTranche) => void
}

export default function DebtScheduleCard({
  jobId,
  apiBase,
  onTrancheSelect,
}: DebtScheduleCardProps) {
  const [schedule, setSchedule] = useState<DebtSchedule | null>(null)
  const [editingTrancheId, setEditingTrancheId] = useState<string | null>(null)
  const [editPrincipal, setEditPrincipal] = useState<string>('')
  const [editRate, setEditRate] = useState<string>('')
  const [editMaturity, setEditMaturity] = useState<string>('')
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [isSaving, setIsSaving] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [isConfirmed, setIsConfirmed] = useState<boolean>(false)

  useEffect(() => {
    let isMounted = true
    setIsLoading(true)
    setError(null)

    fetch(`${apiBase}/footnote/${jobId}/debt`)
      .then((res) => {
        if (!res.ok) {
          if (res.status === 404) return null
          throw new Error(`Failed to load debt schedule: HTTP ${res.status}`)
        }
        return res.json() as Promise<DebtSchedule>
      })
      .then((data) => {
        if (isMounted && data) {
          setSchedule(data)
          setIsConfirmed(data.is_confirmed)
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Error loading debt schedule')
        }
      })
      .finally(() => {
        if (isMounted) setIsLoading(false)
      })

    return () => {
      isMounted = false
    }
  }, [jobId, apiBase])

  function handleStartEdit(tranche: DebtTranche) {
    setEditingTrancheId(tranche.id)
    setEditPrincipal(tranche.principal_amount !== null ? String(tranche.principal_amount) : '')
    setEditRate(tranche.interest_rate !== null ? String(tranche.interest_rate) : '')
    setEditMaturity(tranche.maturity_year !== null ? String(tranche.maturity_year) : '')
  }

  function handleCancelEdit() {
    setEditingTrancheId(null)
  }

  function handleSaveEdit(trancheId: string) {
    if (!schedule) return

    const parsedPrincipal = editPrincipal.trim() ? parseFloat(editPrincipal.trim()) : null
    const parsedRate = editRate.trim() ? parseFloat(editRate.trim()) : null
    const parsedMaturity = editMaturity.trim() ? parseInt(editMaturity.trim(), 10) : null

    const updatedTranches = schedule.tranches.map((t) => {
      if (t.id !== trancheId) return t
      return {
        ...t,
        principal_amount: isNaN(parsedPrincipal ?? NaN) ? t.principal_amount : parsedPrincipal,
        interest_rate: isNaN(parsedRate ?? NaN) ? t.interest_rate : parsedRate,
        maturity_year: isNaN(parsedMaturity ?? NaN) ? t.maturity_year : parsedMaturity,
      }
    })

    setSchedule({
      ...schedule,
      tranches: updatedTranches,
    })
    setEditingTrancheId(null)
  }

  async function handleConfirmSchedule() {
    if (!schedule) return
    setIsSaving(true)

    try {
      const res = await fetch(`${apiBase}/footnote/${jobId}/debt/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tranches: schedule.tranches }),
      })

      if (!res.ok) {
        throw new Error(`Confirm failed: HTTP ${res.status}`)
      }

      const updated = (await res.json()) as DebtSchedule
      setSchedule(updated)
      setIsConfirmed(true)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to confirm debt schedule')
    } finally {
      setIsSaving(false)
    }
  }

  if (isLoading) {
    return (
      <div className="debt-schedule-card" style={{ padding: '1rem', color: '#94a3b8' }}>
        Loading Note 8 Debt Schedule...
      </div>
    )
  }

  if (error || !schedule || schedule.tranches.length === 0) {
    return null // No debt footnote extracted for this filing
  }

  return (
    <div
      className="debt-schedule-card"
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
            💳 {schedule.footnote_title}
          </h3>
          <p style={{ margin: 0, fontSize: '0.8rem', color: '#94a3b8', marginTop: '2px' }}>
            Extracted {schedule.tranches.length} debt tranche
            {schedule.tranches.length === 1 ? '' : 's'}
          </p>
        </div>

        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          {schedule.total_debt !== null && (
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Total Principal</div>
              <strong style={{ fontSize: '0.95rem', color: '#38bdf8' }}>
                ${schedule.total_debt.toLocaleString()}
              </strong>
            </div>
          )}

          {schedule.weighted_avg_rate !== null && (
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Weighted Avg Coupon</div>
              <strong style={{ fontSize: '0.95rem', color: '#34d399' }}>
                {schedule.weighted_avg_rate.toFixed(2)}%
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
            {isConfirmed ? '✓ Confirmed' : isSaving ? 'Saving...' : 'Confirm Debt Schedule'}
          </button>
        </div>
      </div>

      {/* ── Tranches Table ── */}
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
              <th style={{ padding: '6px 8px' }}>Instrument</th>
              <th style={{ padding: '6px 8px', textAlign: 'right' }}>Principal</th>
              <th style={{ padding: '6px 8px', textAlign: 'center' }}>Coupon / Spread</th>
              <th style={{ padding: '6px 8px', textAlign: 'center' }}>Maturity</th>
              <th style={{ padding: '6px 8px' }}>Seniority</th>
              <th style={{ padding: '6px 8px', textAlign: 'right' }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {schedule.tranches.map((tranche) => {
              const isEditing = editingTrancheId === tranche.id
              return (
                <tr
                  key={tranche.id}
                  onClick={() => onTrancheSelect && onTrancheSelect(tranche)}
                  style={{
                    borderBottom: '1px solid rgba(255,255,255,0.05)',
                    cursor: onTrancheSelect ? 'pointer' : 'default',
                  }}
                >
                  <td style={{ padding: '8px', color: '#f8fafc', fontWeight: 500 }}>
                    {tranche.instrument_name}
                  </td>

                  <td style={{ padding: '8px', textAlign: 'right', color: '#38bdf8' }}>
                    {isEditing ? (
                      <input
                        type="text"
                        value={editPrincipal}
                        onChange={(e) => setEditPrincipal(e.target.value)}
                        style={{
                          width: '80px',
                          padding: '2px 4px',
                          background: '#0f172a',
                          color: '#fff',
                          border: '1px solid #475569',
                          borderRadius: '3px',
                          fontSize: '0.8rem',
                          textAlign: 'right',
                        }}
                      />
                    ) : (
                      `$${tranche.principal_amount?.toLocaleString() ?? tranche.principal_text}`
                    )}
                  </td>

                  <td style={{ padding: '8px', textAlign: 'center', color: '#34d399' }}>
                    {isEditing ? (
                      <input
                        type="text"
                        value={editRate}
                        onChange={(e) => setEditRate(e.target.value)}
                        placeholder="e.g. 5.25"
                        style={{
                          width: '60px',
                          padding: '2px 4px',
                          background: '#0f172a',
                          color: '#fff',
                          border: '1px solid #475569',
                          borderRadius: '3px',
                          fontSize: '0.8rem',
                          textAlign: 'center',
                        }}
                      />
                    ) : tranche.interest_rate !== null ? (
                      `${tranche.interest_rate}%`
                    ) : (
                      tranche.rate_text || '—'
                    )}
                  </td>

                  <td style={{ padding: '8px', textAlign: 'center', color: '#cbd5e1' }}>
                    {isEditing ? (
                      <input
                        type="text"
                        value={editMaturity}
                        onChange={(e) => setEditMaturity(e.target.value)}
                        placeholder="2028"
                        style={{
                          width: '55px',
                          padding: '2px 4px',
                          background: '#0f172a',
                          color: '#fff',
                          border: '1px solid #475569',
                          borderRadius: '3px',
                          fontSize: '0.8rem',
                          textAlign: 'center',
                        }}
                      />
                    ) : (
                      tranche.maturity_year || '—'
                    )}
                  </td>

                  <td style={{ padding: '8px' }}>
                    <span
                      style={{
                        fontSize: '0.75rem',
                        background: 'rgba(255,255,255,0.08)',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        color: '#cbd5e1',
                      }}
                    >
                      {tranche.senior_subordinated}
                    </span>
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
                            handleSaveEdit(tranche.id)
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
                          handleStartEdit(tranche)
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
        </table>
      </div>
    </div>
  )
}
