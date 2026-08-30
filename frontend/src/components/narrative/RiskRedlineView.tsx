import { useState, useEffect } from 'react'

export interface RiskFactorChange {
  heading: string
  change_type: 'added' | 'removed' | 'modified'
  severity_score: number
  added_text: string
  removed_text: string
}

export interface RiskFactorRedline {
  company_id?: string | null
  earlier_job_id: string
  later_job_id: string
  changes: RiskFactorChange[]
  added_count: number
  removed_count: number
  modified_count: number
}

interface RiskRedlineViewProps {
  companyId: string
  earlierJobId: string
  laterJobId: string
  apiBase: string
}

export default function RiskRedlineView({
  companyId,
  earlierJobId,
  laterJobId,
  apiBase,
}: RiskRedlineViewProps) {
  const [redline, setRedline] = useState<RiskFactorRedline | null>(null)
  const [expandedIndices, setExpandedIndices] = useState<Set<number>>(new Set())
  const [filterType, setFilterType] = useState<string>('all')
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isMounted = true
    setIsLoading(true)
    setError(null)

    fetch(`${apiBase}/narrative/${companyId}/risk-redline`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        earlier_job_id: earlierJobId,
        later_job_id: laterJobId,
      }),
    })
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Failed to load risk redline: HTTP ${res.status}`)
        }
        return res.json() as Promise<RiskFactorRedline>
      })
      .then((data) => {
        if (isMounted) setRedline(data)
      })
      .catch((err) => {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Error loading risk redline')
        }
      })
      .finally(() => {
        if (isMounted) setIsLoading(false)
      })

    return () => {
      isMounted = false
    }
  }, [companyId, earlierJobId, laterJobId, apiBase])

  function toggleExpand(idx: number) {
    setExpandedIndices((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) {
        next.delete(idx)
      } else {
        next.add(idx)
      }
      return next
    })
  }

  const filteredChanges = (redline?.changes || []).filter((c) => {
    if (filterType === 'all') return true
    return c.change_type === filterType
  })

  return (
    <div
      className="risk-redline-view"
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
          borderBottom: '1px solid #334155',
          paddingBottom: '0.75rem',
          marginBottom: '1rem',
        }}
      >
        <div>
          <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 600, color: '#f8fafc' }}>
            ⚠️ Item 1A Risk Factor Redline Tracker
          </h3>
          <p style={{ margin: 0, fontSize: '0.8rem', color: '#94a3b8', marginTop: '2px' }}>
            Forensic tracking of newly introduced, modified, and removed risk disclosures
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            style={{
              padding: '0.35rem 0.6rem',
              background: '#0f172a',
              color: '#f8fafc',
              border: '1px solid #475569',
              borderRadius: '4px',
              fontSize: '0.8rem',
            }}
          >
            <option value="all">All Changes</option>
            <option value="added">New Risks Only</option>
            <option value="modified">Modified Only</option>
            <option value="removed">Removed Only</option>
          </select>
        </div>
      </div>

      {isLoading && (
        <div style={{ padding: '1.5rem', textAlign: 'center', color: '#94a3b8' }}>
          Comparing Risk Factor disclosures across periods...
        </div>
      )}

      {error && (
        <div style={{ padding: '1rem', color: '#f87171', fontSize: '0.85rem' }}>
          {error}
        </div>
      )}

      {!isLoading && !error && redline && (
        <>
          {/* Summary metrics header */}
          <div
            style={{
              display: 'flex',
              gap: '1.5rem',
              background: '#0f172a',
              padding: '0.75rem 1rem',
              borderRadius: '6px',
              marginBottom: '1rem',
              fontSize: '0.85rem',
            }}
          >
            <div>
              <span style={{ color: '#94a3b8' }}>New Risks: </span>
              <strong style={{ color: '#4ade80' }}>+{redline.added_count}</strong>
            </div>
            <div>
              <span style={{ color: '#94a3b8' }}>Modified Risks: </span>
              <strong style={{ color: '#fbbf24' }}>{redline.modified_count}</strong>
            </div>
            <div>
              <span style={{ color: '#94a3b8' }}>Discontinued Risks: </span>
              <strong style={{ color: '#f87171' }}>-{redline.removed_count}</strong>
            </div>
          </div>

          {/* List of changes */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {filteredChanges.length === 0 ? (
              <div style={{ padding: '1rem', color: '#94a3b8', fontSize: '0.85rem' }}>
                No risk factor changes match the filter.
              </div>
            ) : (
              filteredChanges.map((change, idx) => {
                const isExpanded = expandedIndices.has(idx)
                let badgeColor = '#4ade80'
                let badgeBg = 'rgba(74, 222, 128, 0.15)'
                let badgeLabel = 'NEW'

                if (change.change_type === 'removed') {
                  badgeColor = '#f87171'
                  badgeBg = 'rgba(248, 113, 113, 0.15)'
                  badgeLabel = 'REMOVED'
                } else if (change.change_type === 'modified') {
                  badgeColor = '#fbbf24'
                  badgeBg = 'rgba(251, 191, 36, 0.15)'
                  badgeLabel = `MODIFIED (${Math.round(change.severity_score * 100)}% Δ)`
                }

                return (
                  <div
                    key={idx}
                    onClick={() => toggleExpand(idx)}
                    style={{
                      background: '#090d16',
                      border: '1px solid #334155',
                      borderRadius: '6px',
                      padding: '0.75rem 1rem',
                      cursor: 'pointer',
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        gap: '1rem',
                      }}
                    >
                      <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: '0.85rem' }}>
                        {change.heading}
                      </div>
                      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                        <span
                          style={{
                            fontSize: '0.75rem',
                            fontWeight: 700,
                            padding: '2px 6px',
                            borderRadius: '4px',
                            color: badgeColor,
                            backgroundColor: badgeBg,
                          }}
                        >
                          {badgeLabel}
                        </span>
                        <span style={{ color: '#64748b', fontSize: '0.8rem' }}>
                          {isExpanded ? '▲' : '▼'}
                        </span>
                      </div>
                    </div>

                    {isExpanded && (
                      <div
                        style={{
                          marginTop: '0.75rem',
                          paddingTop: '0.75rem',
                          borderTop: '1px solid #1e293b',
                          fontSize: '0.8rem',
                          lineHeight: 1.5,
                        }}
                      >
                        {change.added_text && (
                          <div style={{ marginBottom: '0.5rem' }}>
                            <strong style={{ color: '#4ade80' }}>Current Disclosure:</strong>
                            <p style={{ margin: '4px 0 0 0', color: '#cbd5e1' }}>
                              {change.added_text}
                            </p>
                          </div>
                        )}
                        {change.removed_text && (
                          <div>
                            <strong style={{ color: '#f87171' }}>Prior Disclosure:</strong>
                            <p style={{ margin: '4px 0 0 0', color: '#94a3b8', textDecoration: 'line-through' }}>
                              {change.removed_text}
                            </p>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })
            )}
          </div>
        </>
      )}
    </div>
  )
}
