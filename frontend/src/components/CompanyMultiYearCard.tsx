import { useState } from 'react'
import type { CompanyWithJobs, MultiYearModelResponse } from '../types/job'
import { Layers, Download } from 'lucide-react'
import { formatFiscalPeriod } from '../lib/fiscal_period'

interface Props {
  company: CompanyWithJobs
  apiBase?: string
}

export default function CompanyMultiYearCard({
  company,
  apiBase = 'http://localhost:8000',
}: Props) {
  const [isGenerating, setIsGenerating] = useState(false)
  const [generationResult, setGenerationResult] =
    useState<MultiYearModelResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const completedJobs = company.jobs.filter((j) => j.status === 'done')

  if (completedJobs.length < 1) {
    return null
  }

  const sortedJobs = [...completedJobs].sort(
    (a, b) => (a.filing_year ?? 0) - (b.filing_year ?? 0),
  )
  const yearsList = sortedJobs
    .map((j) => formatFiscalPeriod(j.filename, j.filing_year))
    .join(', ')

  async function handleBuildMultiYearModel() {
    setIsGenerating(true)
    setError(null)

    try {
      const res = await fetch(
        `${apiBase}/companies/${company.company_id}/multi-year-model`,
        {
          method: 'POST',
        },
      )

      if (!res.ok) {
        const detail = await res.text()
        let parsedDetail = detail
        try {
          const jsonErr = JSON.parse(detail)
          if (jsonErr.detail) parsedDetail = jsonErr.detail
        } catch {
          // Keep raw detail string
        }
        setError(`Failed to build multi-year model: ${parsedDetail}`)
        return
      }

      const data: MultiYearModelResponse = await res.json()
      setGenerationResult(data)
    } catch {
      setError(
        'Network error — could not reach server. Is the backend running?',
      )
    } finally {
      setIsGenerating(false)
    }
  }

  return (
    <div
      className="company-multi-year-card"
      style={{
        backgroundColor: 'var(--fn-bg-surface)',
        border: '1px solid var(--fn-border-subtle)',
        borderRadius: '0.5rem',
        padding: '1rem 1.25rem',
        marginBottom: '1.5rem',
      }}
      aria-label="Multi-Year Model Section"
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '0.75rem',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <h3
              style={{
                margin: 0,
                fontSize: '0.9375rem',
                fontWeight: 600,
                color: 'var(--fn-text-primary)',
              }}
            >
              Company Financial Models: {company.name}{' '}
              {company.ticker ? `(${company.ticker})` : ''}
            </h3>
            <span className="status-badge status-badge--done">
              {completedJobs.length} Filings Ready
            </span>
          </div>
          <p
            style={{
              margin: '0.25rem 0 0 0',
              fontSize: '0.8125rem',
              color: 'var(--fn-text-muted)',
            }}
          >
            Includes {yearsList}
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          {completedJobs.length >= 2 ? (
            <button
              type="button"
              className="fn-btn fn-btn--primary fn-btn--sm"
              onClick={() => void handleBuildMultiYearModel()}
              disabled={isGenerating}
              aria-label="Build Multi-Year Model"
            >
              <Layers size={13} aria-hidden="true" />
              <span>{isGenerating ? 'Building Model...' : 'Build Multi-Year Model'}</span>
            </button>
          ) : (
            <span style={{ fontSize: '0.8125rem', color: 'var(--fn-text-muted)' }}>
              (Requires at least 2 completed filings)
            </span>
          )}

          {generationResult && (
            <a
              href={`${apiBase}${generationResult.download_url}`}
              download={`${company.company_id}_multi_year.xlsx`}
              className="fn-btn fn-btn--secondary fn-btn--sm"
              aria-label="Download Multi-Year Model (xlsx)"
            >
              <Download size={13} aria-hidden="true" />
              <span>Download Multi-Year Model (.xlsx)</span>
            </a>
          )}
        </div>
      </div>

      {generationResult && (
        <div
          style={{
            marginTop: '0.75rem',
            paddingTop: '0.75rem',
            borderTop: '1px solid var(--fn-border-subtle)',
            fontSize: '0.8125rem',
            color: 'var(--fn-status-success)',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          ✓ Multi-year workbook generated with{' '}
          {generationResult.total_cells_generated} total cells across{' '}
          {generationResult.years.length} fiscal years.
        </div>
      )}

      {error && (
        <div
          style={{
            marginTop: '0.75rem',
            paddingTop: '0.75rem',
            borderTop: '1px solid var(--fn-status-error-border)',
            fontSize: '0.8125rem',
            color: 'var(--fn-status-error)',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
          role="alert"
        >
          {error}
        </div>
      )}
    </div>
  )
}
