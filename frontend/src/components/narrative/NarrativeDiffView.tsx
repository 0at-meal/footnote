import { useState, useEffect } from 'react'

export interface NarrativeDiffToken {
  type: 'equal' | 'insert' | 'delete'
  text: string
}

export interface NarrativeDiff {
  company_id?: string | null
  item_number: string
  earlier_job_id: string
  later_job_id: string
  tokens: NarrativeDiffToken[]
  added_tokens: number
  removed_tokens: number
  unchanged_tokens: number
  similarity_ratio: number
}

interface NarrativeDiffViewProps {
  companyId: string
  earlierJobId: string
  laterJobId: string
  apiBase: string
  defaultItem?: string
}

export default function NarrativeDiffView({
  companyId,
  earlierJobId,
  laterJobId,
  apiBase,
  defaultItem = 'Item 7',
}: NarrativeDiffViewProps) {
  const [selectedItem, setSelectedItem] = useState<string>(defaultItem)
  const [diffData, setDiffData] = useState<NarrativeDiff | null>(null)
  const [showChangesOnly, setShowChangesOnly] = useState<boolean>(false)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isMounted = true
    setIsLoading(true)
    setError(null)

    fetch(`${apiBase}/narrative/${companyId}/diff`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        earlier_job_id: earlierJobId,
        later_job_id: laterJobId,
        item_number: selectedItem,
      }),
    })
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Failed to load narrative diff: HTTP ${res.status}`)
        }
        return res.json() as Promise<NarrativeDiff>
      })
      .then((data) => {
        if (isMounted) setDiffData(data)
      })
      .catch((err) => {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Error loading diff')
        }
      })
      .finally(() => {
        if (isMounted) setIsLoading(false)
      })

    return () => {
      isMounted = false
    }
  }, [companyId, earlierJobId, laterJobId, selectedItem, apiBase])

  return (
    <div
      className="narrative-diff-view"
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
            📝 Narrative Delta Tracker ({selectedItem})
          </h3>
          <p style={{ margin: 0, fontSize: '0.8rem', color: '#94a3b8', marginTop: '2px' }}>
            Word-by-word redline comparison across consecutive periods
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <select
            value={selectedItem}
            onChange={(e) => setSelectedItem(e.target.value)}
            style={{
              padding: '0.35rem 0.6rem',
              background: '#0f172a',
              color: '#f8fafc',
              border: '1px solid #475569',
              borderRadius: '4px',
              fontSize: '0.8rem',
            }}
          >
            <option value="Item 7">Item 7 (10-K MD&A)</option>
            <option value="Item 2">Item 2 (10-Q MD&A)</option>
            <option value="Item 1A">Item 1A (Risk Factors)</option>
          </select>

          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '0.8rem',
              color: '#cbd5e1',
              cursor: 'pointer',
            }}
          >
            <input
              type="checkbox"
              checked={showChangesOnly}
              onChange={(e) => setShowChangesOnly(e.target.checked)}
            />
            Highlight Changes Only
          </label>
        </div>
      </div>

      {isLoading && (
        <div style={{ padding: '1.5rem', textAlign: 'center', color: '#94a3b8' }}>
          Computing word-level narrative diff...
        </div>
      )}

      {error && (
        <div style={{ padding: '1rem', color: '#f87171', fontSize: '0.85rem' }}>
          {error}
        </div>
      )}

      {!isLoading && !error && diffData && (
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
              <span style={{ color: '#94a3b8' }}>Similarity: </span>
              <strong style={{ color: '#38bdf8' }}>
                {(diffData.similarity_ratio * 100).toFixed(1)}%
              </strong>
            </div>
            <div>
              <span style={{ color: '#94a3b8' }}>Added words: </span>
              <strong style={{ color: '#4ade80' }}>+{diffData.added_tokens}</strong>
            </div>
            <div>
              <span style={{ color: '#94a3b8' }}>Removed words: </span>
              <strong style={{ color: '#f87171' }}>-{diffData.removed_tokens}</strong>
            </div>
            <div>
              <span style={{ color: '#94a3b8' }}>Unchanged: </span>
              <strong style={{ color: '#cbd5e1' }}>{diffData.unchanged_tokens}</strong>
            </div>
          </div>

          {/* Diff render body */}
          <div
            style={{
              maxHeight: '400px',
              overflowY: 'auto',
              background: '#090d16',
              padding: '1rem',
              borderRadius: '6px',
              lineHeight: 1.6,
              fontSize: '0.85rem',
              fontFamily: 'ui-sans-serif, system-ui, sans-serif',
              whiteSpace: 'pre-wrap',
            }}
          >
            {diffData.tokens.map((token, idx) => {
              if (showChangesOnly && token.type === 'equal') {
                // Collapse large unchanged chunks
                if (token.text.length > 80) {
                  return (
                    <span
                      key={idx}
                      style={{ color: '#475569', fontStyle: 'italic', padding: '0 4px' }}
                    >
                      [...]
                    </span>
                  )
                }
              }

              if (token.type === 'insert') {
                return (
                  <span
                    key={idx}
                    style={{
                      backgroundColor: 'rgba(34, 197, 94, 0.25)',
                      color: '#86efac',
                      textDecoration: 'none',
                      borderRadius: '2px',
                      padding: '1px 2px',
                    }}
                  >
                    {token.text}
                  </span>
                )
              }

              if (token.type === 'delete') {
                return (
                  <span
                    key={idx}
                    style={{
                      backgroundColor: 'rgba(239, 68, 68, 0.25)',
                      color: '#fca5a5',
                      textDecoration: 'line-through',
                      borderRadius: '2px',
                      padding: '1px 2px',
                    }}
                  >
                    {token.text}
                  </span>
                )
              }

              return (
                <span key={idx} style={{ color: '#cbd5e1' }}>
                  {token.text}
                </span>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
