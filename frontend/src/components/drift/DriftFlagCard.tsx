import { useState } from 'react'

export interface RelabeledComponent {
  old_label: string
  new_label: string
  similarity_score: number
  is_confirmed: boolean
  justification?: string | null
}

export interface DriftFlag {
  flag_id: string
  job_id: string
  entity: string
  target_metric: string
  filing_year: number
  added_labels: string[]
  removed_labels: string[]
  relabeled_components?: RelabeledComponent[]
  prior_node_id: string
  created_at: string
}

interface DriftFlagCardProps {
  flag: DriftFlag
  apiBase: string
  onConfirmed?: (updatedFlag: DriftFlag) => void
}

export default function DriftFlagCard({
  flag,
  apiBase,
  onConfirmed,
}: DriftFlagCardProps) {
  const [currentFlag, setCurrentFlag] = useState<DriftFlag>(flag)
  const [confirmingIdx, setConfirmingIdx] = useState<number | null>(null)

  async function handleConfirmRelabel(idx: number, item: RelabeledComponent) {
    setConfirmingIdx(idx)
    try {
      const res = await fetch(`${apiBase}/drift/jobs/${currentFlag.job_id}/mark-relabeled`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          old_standard_label: item.old_label,
          new_standard_label: item.new_label,
          justification: 'Confirmed cosmetic relabeling by analyst review',
        }),
      })

      if (!res.ok) {
        throw new Error(`Failed to confirm relabeling: HTTP ${res.status}`)
      }

      const updated = (await res.json()) as DriftFlag
      setCurrentFlag(updated)
      if (onConfirmed) onConfirmed(updated)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Error confirming relabeling')
    } finally {
      setConfirmingIdx(null)
    }
  }

  const relabeled = currentFlag.relabeled_components || []

  return (
    <div
      className="drift-flag-card"
      style={{
        background: 'var(--surface-raised, #1e293b)',
        border: '1px solid #eab308',
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
          <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 600, color: '#facc15' }}>
            ⚡ Historical Drift Detected: {currentFlag.target_metric} ({currentFlag.filing_year})
          </h3>
          <p style={{ margin: 0, fontSize: '0.8rem', color: '#94a3b8', marginTop: '2px' }}>
            Entity: {currentFlag.entity} — Definition modified from prior baseline
          </p>
        </div>
      </div>

      {/* Cosmetic Relabelings */}
      {relabeled.length > 0 && (
        <div style={{ marginBottom: '1rem' }}>
          <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.85rem', color: '#38bdf8' }}>
            ✨ Detected Cosmetic Relabelings (Economic Substance Unchanged)
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {relabeled.map((item, idx) => (
              <div
                key={idx}
                style={{
                  background: '#090d16',
                  border: '1px solid #0284c7',
                  borderRadius: '6px',
                  padding: '0.6rem 0.85rem',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div>
                  <div style={{ fontSize: '0.85rem', color: '#f8fafc' }}>
                    <span style={{ color: '#f87171', textDecoration: 'line-through' }}>
                      {item.old_label}
                    </span>
                    {' → '}
                    <span style={{ color: '#4ade80', fontWeight: 600 }}>
                      {item.new_label}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.75rem', color: '#38bdf8', marginTop: '2px' }}>
                    Similarity: {Math.round(item.similarity_score * 100)}% match
                  </div>
                </div>

                <div>
                  {item.is_confirmed ? (
                    <span
                      style={{
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        color: '#4ade80',
                        backgroundColor: 'rgba(74, 222, 128, 0.15)',
                        padding: '3px 8px',
                        borderRadius: '4px',
                      }}
                    >
                      ✓ Relabeling Confirmed
                    </span>
                  ) : (
                    <button
                      type="button"
                      className="review-btn review-btn--confirm"
                      style={{ padding: '3px 8px', fontSize: '0.75rem' }}
                      disabled={confirmingIdx === idx}
                      onClick={() => void handleConfirmRelabel(idx, item)}
                    >
                      {confirmingIdx === idx ? 'Confirming...' : 'Confirm Relabeling'}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Added / Removed Labels */}
      {currentFlag.added_labels.length > 0 && (
        <div style={{ marginBottom: '0.5rem', fontSize: '0.85rem' }}>
          <strong style={{ color: '#4ade80' }}>Added Components: </strong>
          <span style={{ color: '#cbd5e1' }}>{currentFlag.added_labels.join(', ')}</span>
        </div>
      )}

      {currentFlag.removed_labels.length > 0 && (
        <div style={{ fontSize: '0.85rem' }}>
          <strong style={{ color: '#f87171' }}>Removed Components: </strong>
          <span style={{ color: '#cbd5e1' }}>{currentFlag.removed_labels.join(', ')}</span>
        </div>
      )}
    </div>
  )
}
