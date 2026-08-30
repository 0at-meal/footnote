import { useState, useEffect } from 'react'

export interface CustomerConcentration {
  customer_name: string
  revenue_percentage: number | null
  segment?: string | null
  disclosure_location: string
  job_id: string
  is_supplier: boolean
}

export interface ConcentrationSummary {
  job_id: string
  company_id?: string | null
  filing_year?: number | null
  customers: CustomerConcentration[]
  suppliers: CustomerConcentration[]
  has_high_concentration: boolean
  is_confirmed: boolean
}

interface ConcentrationCardProps {
  jobId: string
  apiBase: string
}

export default function ConcentrationCard({
  jobId,
  apiBase,
}: ConcentrationCardProps) {
  const [summary, setSummary] = useState<ConcentrationSummary | null>(null)
  const [editingIdx, setEditingIdx] = useState<number | null>(null)
  const [editName, setEditName] = useState<string>('')
  const [editPct, setEditPct] = useState<string>('')
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [isSaving, setIsSaving] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [isConfirmed, setIsConfirmed] = useState<boolean>(false)

  useEffect(() => {
    let isMounted = true
    setIsLoading(true)
    setError(null)

    fetch(`${apiBase}/footnote/${jobId}/concentration`)
      .then((res) => {
        if (!res.ok) {
          if (res.status === 404) return null
          throw new Error(`Failed to load concentration data: HTTP ${res.status}`)
        }
        return res.json() as Promise<ConcentrationSummary>
      })
      .then((data) => {
        if (isMounted && data) {
          setSummary(data)
          setIsConfirmed(data.is_confirmed)
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Error loading concentration')
        }
      })
      .finally(() => {
        if (isMounted) setIsLoading(false)
      })

    return () => {
      isMounted = false
    }
  }, [jobId, apiBase])

  function handleStartEdit(idx: number, item: CustomerConcentration) {
    setEditingIdx(idx)
    setEditName(item.customer_name)
    setEditPct(item.revenue_percentage !== null ? String(item.revenue_percentage) : '')
  }

  function handleCancelEdit() {
    setEditingIdx(null)
  }

  function handleSaveEdit(idx: number) {
    if (!summary) return

    const parsedPct = editPct.trim() ? parseFloat(editPct.trim()) : null
    const updatedCustomers = summary.customers.map((c, i) => {
      if (i !== idx) return c
      return {
        ...c,
        customer_name: editName.trim() || c.customer_name,
        revenue_percentage: isNaN(parsedPct ?? NaN) ? c.revenue_percentage : parsedPct,
      }
    })

    const hasHigh = updatedCustomers.some(
      (c) => (c.revenue_percentage ?? 0) >= 15.0,
    )

    setSummary({
      ...summary,
      customers: updatedCustomers,
      has_high_concentration: hasHigh,
    })
    setEditingIdx(null)
  }

  async function handleConfirm() {
    if (!summary) return
    setIsSaving(true)

    try {
      const res = await fetch(`${apiBase}/footnote/${jobId}/concentration/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customers: summary.customers,
          suppliers: summary.suppliers,
        }),
      })

      if (!res.ok) {
        throw new Error(`Confirm failed: HTTP ${res.status}`)
      }

      const updated = (await res.json()) as ConcentrationSummary
      setSummary(updated)
      setIsConfirmed(true)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to confirm concentration disclosures')
    } finally {
      setIsSaving(false)
    }
  }

  if (isLoading) {
    return (
      <div className="concentration-card" style={{ padding: '0.75rem', color: '#94a3b8' }}>
        Loading Concentration Disclosures...
      </div>
    )
  }

  if (error || !summary || (summary.customers.length === 0 && summary.suppliers.length === 0)) {
    return null
  }

  return (
    <div
      className="concentration-card"
      style={{
        background: 'var(--surface-raised, #1e293b)',
        border: summary.has_high_concentration ? '1px solid #f59e0b' : '1px solid #334155',
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
          borderBottom: '1px solid #334155',
          paddingBottom: '0.75rem',
          marginBottom: '1rem',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 600, color: '#f8fafc' }}>
              🎯 Customer & Supplier Concentration (ASC 280)
            </h3>
            {summary.has_high_concentration && (
              <span
                style={{
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  padding: '2px 6px',
                  borderRadius: '4px',
                  backgroundColor: 'rgba(245, 158, 11, 0.2)',
                  color: '#fbbf24',
                  border: '1px solid #f59e0b',
                }}
              >
                ⚠️ High Concentration (&ge;15%)
              </span>
            )}
          </div>
          <p style={{ margin: 0, fontSize: '0.8rem', color: '#94a3b8', marginTop: '2px' }}>
            Major counterparty disclosures accounting for &ge;10% of revenue
          </p>
        </div>

        <button
          type="button"
          className="review-btn review-btn--confirm"
          disabled={isSaving || isConfirmed}
          onClick={() => void handleConfirm()}
          style={{ padding: '0.4rem 0.85rem', fontSize: '0.8rem' }}
        >
          {isConfirmed ? '✓ Confirmed' : isSaving ? 'Saving...' : 'Confirm Concentration'}
        </button>
      </div>

      {/* Counterparty Table */}
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
              <th style={{ padding: '6px 8px' }}>Counterparty</th>
              <th style={{ padding: '6px 8px' }}>Type</th>
              <th style={{ padding: '6px 8px', textAlign: 'right' }}>Revenue / Purchase Share</th>
              <th style={{ padding: '6px 8px' }}>Segment</th>
              <th style={{ padding: '6px 8px', textAlign: 'right' }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {summary.customers.map((c, idx) => {
              const isEditing = editingIdx === idx
              const isHigh = (c.revenue_percentage ?? 0) >= 15.0
              return (
                <tr
                  key={idx}
                  style={{
                    borderBottom: '1px solid rgba(255,255,255,0.05)',
                  }}
                >
                  <td style={{ padding: '8px', color: '#f8fafc', fontWeight: 500 }}>
                    {isEditing ? (
                      <input
                        type="text"
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        style={{
                          width: '120px',
                          padding: '2px 4px',
                          background: '#0f172a',
                          color: '#fff',
                          border: '1px solid #475569',
                          borderRadius: '3px',
                          fontSize: '0.8rem',
                        }}
                      />
                    ) : (
                      c.customer_name
                    )}
                  </td>

                  <td style={{ padding: '8px' }}>
                    <span
                      style={{
                        fontSize: '0.75rem',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        backgroundColor: 'rgba(56, 189, 248, 0.15)',
                        color: '#38bdf8',
                      }}
                    >
                      Customer
                    </span>
                  </td>

                  <td
                    style={{
                      padding: '8px',
                      textAlign: 'right',
                      fontWeight: 600,
                      color: isHigh ? '#fbbf24' : '#34d399',
                    }}
                  >
                    {isEditing ? (
                      <input
                        type="text"
                        value={editPct}
                        onChange={(e) => setEditPct(e.target.value)}
                        style={{
                          width: '60px',
                          padding: '2px 4px',
                          background: '#0f172a',
                          color: '#fff',
                          border: '1px solid #475569',
                          borderRadius: '3px',
                          fontSize: '0.8rem',
                          textAlign: 'right',
                        }}
                      />
                    ) : c.revenue_percentage !== null ? (
                      `${c.revenue_percentage.toFixed(1)}%`
                    ) : (
                      '—'
                    )}
                  </td>

                  <td style={{ padding: '8px', color: '#94a3b8' }}>
                    {c.segment || 'Consolidated'}
                  </td>

                  <td style={{ padding: '8px', textAlign: 'right' }}>
                    {isEditing ? (
                      <div style={{ display: 'inline-flex', gap: '4px' }}>
                        <button
                          type="button"
                          className="review-btn review-btn--confirm"
                          style={{ padding: '2px 6px', fontSize: '0.75rem' }}
                          onClick={() => handleSaveEdit(idx)}
                        >
                          Save
                        </button>
                        <button
                          type="button"
                          className="review-btn review-btn--edit"
                          style={{ padding: '2px 6px', fontSize: '0.75rem' }}
                          onClick={handleCancelEdit}
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        className="review-btn review-btn--edit"
                        style={{ padding: '2px 6px', fontSize: '0.75rem' }}
                        onClick={() => handleStartEdit(idx, c)}
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
