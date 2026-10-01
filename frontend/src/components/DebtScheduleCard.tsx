import { useState, useEffect, useMemo } from 'react'
import { CreditCard, Check, Edit2, X, BarChart3 } from 'lucide-react'
import { DataTable, type ColumnDef } from './ui/DataTable'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'

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
  initialSchedule?: DebtSchedule
  onTrancheSelect?: (tranche: DebtTranche) => void
}

export default function DebtScheduleCard({
  jobId,
  apiBase,
  initialSchedule,
  onTrancheSelect,
}: DebtScheduleCardProps) {
  const [schedule, setSchedule] = useState<DebtSchedule | null>(initialSchedule ?? null)
  const [editingTrancheId, setEditingTrancheId] = useState<string | null>(null)
  const [editPrincipal, setEditPrincipal] = useState<string>('')
  const [editRate, setEditRate] = useState<string>('')
  const [editMaturity, setEditMaturity] = useState<string>('')
  const [isLoading, setIsLoading] = useState<boolean>(!initialSchedule)
  const [isSaving, setIsSaving] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [isConfirmed, setIsConfirmed] = useState<boolean>(initialSchedule?.is_confirmed ?? false)

  useEffect(() => {
    if (initialSchedule) return

    let isMounted = true

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
  }, [jobId, apiBase, initialSchedule])

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

  // Calculate tie-out check between tranches sum and total_debt
  const tieOut = useMemo(() => {
    if (!schedule || schedule.total_debt === null || schedule.total_debt === undefined) {
      return null
    }
    const trancheSum = schedule.tranches.reduce((acc, t) => acc + (t.principal_amount ?? 0), 0)
    const diff = Math.abs(trancheSum - schedule.total_debt)
    const passed = diff < 0.01
    return {
      passed,
      trancheSum,
      totalDebt: schedule.total_debt,
      diff,
    }
  }, [schedule])

  // Aggregate maturity ladder by year
  const maturityLadder = useMemo(() => {
    if (!schedule || schedule.tranches.length === 0) return []
    const yearMap = new Map<string, number>()
    for (const t of schedule.tranches) {
      const year = t.maturity_year ? String(t.maturity_year) : 'Thereafter / Other'
      const amt = t.principal_amount ?? 0
      yearMap.set(year, (yearMap.get(year) ?? 0) + amt)
    }

    // Sort years chronologically, placing 'Thereafter / Other' last
    const sortedEntries = Array.from(yearMap.entries()).sort(([a], [b]) => {
      if (a === 'Thereafter / Other') return 1
      if (b === 'Thereafter / Other') return -1
      return Number(a) - Number(b)
    })

    const maxVal = Math.max(...sortedEntries.map(([, amt]) => amt), 1)

    return sortedEntries.map(([year, amount]) => ({
      year,
      amount,
      pct: (amount / maxVal) * 100,
    }))
  }, [schedule])

  if (isLoading) {
    return (
      <div className="debt-schedule-card fn-card" style={{ padding: '1.5rem', color: 'var(--ink-muted)' }}>
        Loading Note 8 Debt Schedule...
      </div>
    )
  }

  if (error || !schedule || schedule.tranches.length === 0) {
    return null
  }

  const columns: ColumnDef<DebtTranche>[] = [
    {
      key: 'instrument_name',
      header: 'Instrument',
      truncate: true,
      width: '35%',
      render: (t) => (
        <span style={{ fontWeight: 500, color: 'var(--ink)' }}>
          {t.instrument_name}
        </span>
      ),
    },
    {
      key: 'principal_amount',
      header: 'Principal',
      units: '($M)',
      isNumeric: true,
      render: (t) => {
        if (editingTrancheId === t.id) {
          return (
            <input
              type="text"
              value={editPrincipal}
              onChange={(e) => setEditPrincipal(e.target.value)}
              aria-label="Edit Principal"
              style={{
                width: '85px',
                padding: '2px 4px',
                background: 'var(--surface-2)',
                color: 'var(--ink)',
                border: '1px solid var(--accent)',
                borderRadius: '3px',
                fontSize: '0.8rem',
                textAlign: 'right',
              }}
            />
          )
        }
        return t.principal_amount !== null ? `$${t.principal_amount.toLocaleString()}` : t.principal_text || '—'
      },
    },
    {
      key: 'interest_rate',
      header: 'Coupon / Rate',
      align: 'center',
      isNumeric: true,
      render: (t) => {
        if (editingTrancheId === t.id) {
          return (
            <input
              type="text"
              value={editRate}
              onChange={(e) => setEditRate(e.target.value)}
              aria-label="Edit Rate"
              placeholder="e.g. 5.25"
              style={{
                width: '65px',
                padding: '2px 4px',
                background: 'var(--surface-2)',
                color: 'var(--ink)',
                border: '1px solid var(--accent)',
                borderRadius: '3px',
                fontSize: '0.8rem',
                textAlign: 'center',
              }}
            />
          )
        }
        return t.interest_rate !== null ? `${t.interest_rate}%` : t.rate_text || '—'
      },
    },
    {
      key: 'maturity_year',
      header: 'Maturity',
      align: 'center',
      isNumeric: true,
      render: (t) => {
        if (editingTrancheId === t.id) {
          return (
            <input
              type="text"
              value={editMaturity}
              onChange={(e) => setEditMaturity(e.target.value)}
              aria-label="Edit Maturity Year"
              placeholder="2028"
              style={{
                width: '60px',
                padding: '2px 4px',
                background: 'var(--surface-2)',
                color: 'var(--ink)',
                border: '1px solid var(--accent)',
                borderRadius: '3px',
                fontSize: '0.8rem',
                textAlign: 'center',
              }}
            />
          )
        }
        return t.maturity_year || '—'
      },
    },
    {
      key: 'senior_subordinated',
      header: 'Seniority',
      render: (t) => (
        <span
          style={{
            fontSize: '0.75rem',
            background: 'var(--surface-2)',
            border: '1px solid var(--border)',
            padding: '2px 6px',
            borderRadius: '4px',
            color: 'var(--ink-secondary)',
          }}
        >
          {t.senior_subordinated}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'Action',
      align: 'right',
      render: (t) => {
        if (editingTrancheId === t.id) {
          return (
            <div style={{ display: 'inline-flex', gap: '4px' }}>
              <Button
                variant="primary"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation()
                  handleSaveEdit(t.id)
                }}
              >
                Save
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation()
                  handleCancelEdit()
                }}
              >
                <X size={12} aria-hidden="true" />
              </Button>
            </div>
          )
        }
        return (
          <Button
            variant="secondary"
            size="sm"
            onClick={(e) => {
              e.stopPropagation()
              handleStartEdit(t)
            }}
          >
            <Edit2 size={12} aria-hidden="true" />
            <span>Edit</span>
          </Button>
        )
      },
    },
  ]

  return (
    <div
      className="debt-schedule-card fn-card"
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--fn-radius-md)',
        padding: '1.25rem',
        marginTop: '1rem',
        marginBottom: '1rem',
        boxShadow: 'var(--fn-shadow-sm)',
      }}
    >
      {/* ── Header ── */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: '1rem',
          marginBottom: '1.25rem',
          borderBottom: '1px solid var(--border)',
          paddingBottom: '1rem',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <CreditCard size={18} style={{ color: 'var(--accent)' }} aria-hidden="true" />
            <h3
              style={{
                margin: 0,
                fontSize: '1.1rem',
                fontWeight: 600,
                color: 'var(--ink)',
                fontFamily: 'var(--fn-font-sans)',
              }}
            >
              {schedule.footnote_title}
            </h3>
          </div>
          <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--ink-muted)' }}>
            Extracted {schedule.tranches.length} debt tranche
            {schedule.tranches.length === 1 ? '' : 's'}
          </p>
        </div>

        {/* Hero numbers and Primary action */}
        <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          {schedule.total_debt !== null && (
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--ink-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Total Principal
              </div>
              <div
                style={{
                  fontSize: '1.35rem',
                  fontWeight: 700,
                  fontFamily: 'var(--fn-font-serif)',
                  color: 'var(--ink)',
                  lineHeight: 1.2,
                }}
              >
                ${schedule.total_debt.toLocaleString()}M
              </div>
            </div>
          )}

          {schedule.weighted_avg_rate !== null && (
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--ink-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Weighted Avg Coupon
              </div>
              <div
                className="fn-tabular tabular-nums"
                style={{
                  fontSize: '1.1rem',
                  fontWeight: 600,
                  fontFamily: 'var(--fn-font-mono)',
                  color: 'var(--ok)',
                  lineHeight: 1.2,
                }}
              >
                {schedule.weighted_avg_rate.toFixed(2)}%
              </div>
            </div>
          )}

          {/* Tie-out Badge */}
          {tieOut && (
            <div>
              {tieOut.passed ? (
                <Badge variant="ok">
                  Tie-out: PASS (Tranches sum to Total Principal)
                </Badge>
              ) : (
                <Badge variant="danger">
                  Tie-out: FAIL (Diff ${tieOut.diff.toLocaleString()}M)
                </Badge>
              )}
            </div>
          )}

          {/* Primary Action Button */}
          <Button
            variant="primary"
            disabled={isSaving || isConfirmed}
            onClick={() => void handleConfirmSchedule()}
          >
            <Check size={14} aria-hidden="true" />
            <span>{isConfirmed ? '✓ Confirmed' : isSaving ? 'Saving...' : 'Confirm Debt Schedule'}</span>
          </Button>
        </div>
      </div>

      {/* ── Maturity Ladder Chart (Accessible Bar Chart) ── */}
      {maturityLadder.length > 0 && (
        <div
          style={{
            marginBottom: '1.5rem',
            padding: '1rem',
            backgroundColor: 'var(--surface-2)',
            borderRadius: 'var(--fn-radius-sm)',
            border: '1px solid var(--border)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '0.75rem' }}>
            <BarChart3 size={15} style={{ color: 'var(--ink-secondary)' }} aria-hidden="true" />
            <h4
              style={{
                margin: 0,
                fontSize: '0.85rem',
                fontWeight: 600,
                color: 'var(--ink-secondary)',
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
              }}
            >
              Maturity Ladder by Year
            </h4>
          </div>

          {/* Screen reader text alternative */}
          <div className="sr-only" aria-live="polite">
            Maturity schedule summary:
            {maturityLadder.map((bar) => ` Year ${bar.year}: $${bar.amount.toLocaleString()}M;`).join('')}
          </div>

          {/* Visual accessible horizontal bar ladder */}
          <div
            role="img"
            aria-label="Maturity schedule chart by year showing principal due per maturity period"
            style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}
          >
            {maturityLadder.map((bar) => (
              <div
                key={bar.year}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '110px 1fr 90px',
                  alignItems: 'center',
                  gap: '12px',
                  fontSize: '0.8rem',
                }}
              >
                <span style={{ fontWeight: 500, color: 'var(--ink-secondary)' }}>
                  {bar.year}
                </span>
                <div
                  style={{
                    height: '14px',
                    backgroundColor: 'rgba(43, 75, 238, 0.12)',
                    borderRadius: '3px',
                    overflow: 'hidden',
                    position: 'relative',
                  }}
                >
                  <div
                    style={{
                      height: '100%',
                      width: `${bar.pct}%`,
                      backgroundColor: 'var(--accent)',
                      borderRadius: '3px',
                      transition: 'width var(--fn-motion-state)',
                    }}
                  />
                </div>
                <span
                  className="fn-tabular tabular-nums"
                  style={{
                    textAlign: 'right',
                    fontFamily: 'var(--fn-font-mono)',
                    color: 'var(--ink)',
                    fontWeight: 500,
                  }}
                >
                  ${bar.amount.toLocaleString()}M
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Tranches Table via DataTable ── */}
      <DataTable<DebtTranche>
        columns={columns}
        data={schedule.tranches}
        keyExtractor={(t) => t.id}
        onRowClick={(t) => onTrancheSelect && onTrancheSelect(t)}
        emptyMessage="No debt tranches extracted"
      />
    </div>
  )
}
