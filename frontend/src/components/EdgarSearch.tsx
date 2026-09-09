import { useState, useEffect, useRef } from 'react'
import type {
  EdgarCompanyResult,
  EdgarFiling,
  JobRecord,
  TargetMetric,
} from '../types/job'
import { TARGET_METRICS, DEFAULT_METRIC } from '../types/job'

interface EdgarSearchProps {
  apiBase: string
  onJobCreated: (job: JobRecord) => void
}

export default function EdgarSearch({ apiBase, onJobCreated }: EdgarSearchProps) {
  const [query, setQuery] = useState('')
  const [companies, setCompanies] = useState<EdgarCompanyResult[]>([])
  const [selectedCompany, setSelectedCompany] = useState<EdgarCompanyResult | null>(null)
  const [filings, setFilings] = useState<EdgarFiling[]>([])
  const [selectedFiling, setSelectedFiling] = useState<EdgarFiling | null>(null)
  const [targetMetric, setTargetMetric] = useState<TargetMetric>(DEFAULT_METRIC)
  const [isSearching, setIsSearching] = useState(false)
  const [isLoadingFilings, setIsLoadingFilings] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // ── Debounced Company Search (Ticket D-5) ───────────────────────────────────
  useEffect(() => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current)
    }

    if (!query.trim() || query.trim().length < 2) {
      setCompanies([])
      return
    }

    debounceTimerRef.current = setTimeout(async () => {
      setIsSearching(true)
      setError(null)
      try {
        const res = await fetch(
          `${apiBase}/upload/edgar/search?q=${encodeURIComponent(query.trim())}`,
        )
        if (!res.ok) {
          throw new Error(`Search failed: HTTP ${res.status}`)
        }
        const data = (await res.json()) as EdgarCompanyResult[]
        setCompanies(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to search SEC EDGAR')
        setCompanies([])
      } finally {
        setIsSearching(false)
      }
    }, 300)

    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current)
      }
    }
  }, [query, apiBase])

  // ── Fetch Filings for Selected Company ─────────────────────────────────────
  async function handleSelectCompany(comp: EdgarCompanyResult) {
    setSelectedCompany(comp)
    setSelectedFiling(null)
    setCompanies([])
    setQuery(comp.ticker ? `${comp.company_name} (${comp.ticker})` : comp.company_name)
    setIsLoadingFilings(true)
    setError(null)

    try {
      const res = await fetch(
        `${apiBase}/upload/edgar/filings/${comp.cik}?limit=15`,
      )
      if (!res.ok) {
        throw new Error(`Failed to load filings: HTTP ${res.status}`)
      }
      const data = (await res.json()) as EdgarFiling[]
      setFilings(data)
      if (data.length > 0) {
        setSelectedFiling(data[0])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to retrieve filings')
      setFilings([])
    } finally {
      setIsLoadingFilings(false)
    }
  }

  // ── Ingest Selected Filing Direct from EDGAR ───────────────────────────────
  async function handleIngestFiling() {
    if (!selectedCompany || !selectedFiling) return

    setIsSubmitting(true)
    setError(null)
    setSuccessMessage(null)

    try {
      const res = await fetch(`${apiBase}/upload/edgar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cik: selectedCompany.cik,
          accession_number: selectedFiling.accession_number,
          target_metric: targetMetric,
          filing_year: selectedFiling.filing_year,
          company_name: selectedCompany.company_name,
          primary_document: selectedFiling.primary_document,
        }),
      })

      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
        throw new Error(detail.detail || `Ingestion failed (${res.status})`)
      }

      const createdJob = (await res.json()) as JobRecord
      setSuccessMessage(
        `Successfully queued ${selectedFiling.form_type} (${selectedFiling.filing_date}) for ${selectedCompany.company_name}!`,
      )
      onJobCreated(createdJob)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to ingest filing from EDGAR')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div
      className="edgar-search-card"
      style={{
        background: 'var(--surface-raised, #1e293b)',
        border: '1px solid var(--border-color, #334155)',
        borderRadius: '8px',
        padding: '1.25rem',
        marginBottom: '1.5rem',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
        <span style={{ fontSize: '1.25rem' }}>🏛️</span>
        <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600, color: 'var(--text, #f8fafc)' }}>
          SEC EDGAR Direct Ingestion
        </h3>
        <span
          style={{
            fontSize: '0.75rem',
            background: 'rgba(59, 130, 246, 0.2)',
            color: '#60a5fa',
            padding: '2px 8px',
            borderRadius: '12px',
            marginLeft: 'auto',
          }}
        >
          Direct EDGAR API
        </span>
      </div>

      <div style={{ position: 'relative', marginBottom: '1rem' }}>
        <input
          type="text"
          className="edgar-search-input"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            if (selectedCompany) {
              setSelectedCompany(null)
              setFilings([])
              setSelectedFiling(null)
            }
          }}
          placeholder="Search company by ticker (e.g. AAPL, MSFT), name, or CIK..."
          aria-label="Search SEC EDGAR companies"
          style={{
            width: '100%',
            padding: '0.6rem 0.85rem',
            background: '#0f172a',
            border: '1px solid #475569',
            borderRadius: '6px',
            color: '#f8fafc',
            fontSize: '0.9rem',
            boxSizing: 'border-box',
          }}
        />

        {isSearching && (
          <div
            style={{
              position: 'absolute',
              right: '12px',
              top: '50%',
              transform: 'translateY(-50%)',
              fontSize: '0.8rem',
              color: '#94a3b8',
            }}
          >
            Searching...
          </div>
        )}

        {/* ── Search Dropdown ── */}
        {companies.length > 0 && (
          <div
            className="edgar-autocomplete-dropdown"
            role="listbox"
            style={{
              position: 'absolute',
              top: '100%',
              left: 0,
              right: 0,
              background: '#0f172a',
              border: '1px solid #475569',
              borderRadius: '6px',
              maxHeight: '220px',
              overflowY: 'auto',
              zIndex: 50,
              marginTop: '4px',
              boxShadow: '0 10px 15px -3px rgba(0,0,0,0.5)',
            }}
          >
            {companies.map((c) => (
              <div
                key={c.cik}
                role="option"
                aria-selected={false}
                tabIndex={0}
                onClick={() => void handleSelectCompany(c)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    void handleSelectCompany(c)
                  }
                }}
                style={{
                  padding: '0.5rem 0.75rem',
                  cursor: 'pointer',
                  borderBottom: '1px solid #1e293b',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div>
                  <strong style={{ color: '#f8fafc' }}>{c.company_name}</strong>
                  {c.ticker && (
                    <span style={{ marginLeft: '8px', color: '#38bdf8', fontSize: '0.8rem' }}>
                      ${c.ticker}
                    </span>
                  )}
                </div>
                <span style={{ color: '#64748b', fontSize: '0.75rem' }}>CIK {c.cik}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {isLoadingFilings && (
        <div style={{ color: '#94a3b8', fontSize: '0.85rem', padding: '0.5rem 0' }}>
          Loading filings from SEC EDGAR...
        </div>
      )}

      {/* ── Filings Picker ── */}
      {selectedCompany && filings.length > 0 && (
        <div
          style={{
            background: 'rgba(0, 0, 0, 0.25)',
            padding: '0.85rem',
            borderRadius: '6px',
            marginBottom: '1rem',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
            <span style={{ fontSize: '0.85rem', color: '#cbd5e1', fontWeight: 500 }}>
              Select Filing for {selectedCompany.company_name}:
            </span>
            <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
              {filings.length} filings found
            </span>
          </div>

          <select
            value={selectedFiling?.accession_number || ''}
            onChange={(e) => {
              const found = filings.find((f) => f.accession_number === e.target.value)
              if (found) setSelectedFiling(found)
            }}
            aria-label="Select SEC Filing"
            style={{
              width: '100%',
              padding: '0.5rem',
              background: '#0f172a',
              border: '1px solid #475569',
              borderRadius: '4px',
              color: '#f8fafc',
              fontSize: '0.85rem',
              marginBottom: '0.75rem',
            }}
          >
            {filings.map((f) => (
              <option key={f.accession_number} value={f.accession_number}>
                {f.form_type} ({f.filing_date}) — {f.description || f.primary_document || f.accession_number}
              </option>
            ))}
          </select>

          <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <label htmlFor="edgar-metric-select" style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
                Target Metric:
              </label>
              <select
                id="edgar-metric-select"
                value={targetMetric}
                onChange={(e) => setTargetMetric(e.target.value as TargetMetric)}
                style={{
                  padding: '0.35rem 0.5rem',
                  background: '#0f172a',
                  border: '1px solid #475569',
                  borderRadius: '4px',
                  color: '#f8fafc',
                  fontSize: '0.8rem',
                }}
              >
                {TARGET_METRICS.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="button"
              className="review-btn review-btn--generate"
              disabled={isSubmitting || !selectedFiling}
              onClick={() => void handleIngestFiling()}
              style={{
                marginLeft: 'auto',
                padding: '0.45rem 1rem',
                fontSize: '0.85rem',
                fontWeight: 600,
              }}
            >
              {isSubmitting ? 'Ingesting from EDGAR...' : 'Ingest Filing from SEC EDGAR →'}
            </button>
          </div>
        </div>
      )}

      {error && (
        <div
          role="alert"
          style={{
            background: 'rgba(239, 68, 68, 0.15)',
            border: '1px solid #ef4444',
            color: '#fca5a5',
            padding: '0.5rem 0.75rem',
            borderRadius: '4px',
            fontSize: '0.8rem',
            marginTop: '0.5rem',
          }}
        >
          {error}
        </div>
      )}

      {successMessage && (
        <div
          role="status"
          style={{
            background: 'rgba(34, 197, 94, 0.15)',
            border: '1px solid #22c55e',
            color: '#86efac',
            padding: '0.5rem 0.75rem',
            borderRadius: '4px',
            fontSize: '0.8rem',
            marginTop: '0.5rem',
          }}
        >
          {successMessage}
        </div>
      )}
    </div>
  )
}
