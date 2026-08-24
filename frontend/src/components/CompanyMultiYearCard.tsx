import { useState } from 'react'
import type { CompanyWithJobs, MultiYearModelResponse } from '../types/job'

interface Props {
  company: CompanyWithJobs
  apiBase?: string
}

export default function CompanyMultiYearCard({
  company,
  apiBase = 'http://localhost:8000',
}: Props) {
  const [isGenerating, setIsGenerating] = useState(false)
  const [isGeneratingFull, setIsGeneratingFull] = useState(false)
  const [generationResult, setGenerationResult] =
    useState<MultiYearModelResponse | null>(null)
  const [fullModelResult, setFullModelResult] =
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
    .map((j) => (j.filing_year ? `FY${j.filing_year}` : `FY(${j.filename})`))
    .join(', ')

  async function handleBuildFullModel() {
    setIsGeneratingFull(true)
    setError(null)

    try {
      const res = await fetch(
        `${apiBase}/companies/${company.company_id}/full-model`,
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
        setError(`Failed to build full model: ${parsedDetail}`)
        return
      }

      const data: MultiYearModelResponse = await res.json()
      setFullModelResult(data)
    } catch {
      setError(
        'Network error ? could not reach server. Is the backend running?',
      )
    } finally {
      setIsGeneratingFull(false)
    }
  }

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
        'Network error ? could not reach server. Is the backend running?',
      )
    } finally {
      setIsGenerating(false)
    }
  }

  return (
    <div
      className="company-multi-year-card"
      style={{
        backgroundColor: '#f8fafc',
        border: '1px solid #cbd5e1',
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
                color: '#0f172a',
              }}
            >
              Company Financial Models: {company.name}{' '}
              {company.ticker ? `(${company.ticker})` : ''}
            </h3>
            <span
              style={{
                backgroundColor: '#e0e7ff',
                color: '#3730a3',
                fontSize: '0.75rem',
                padding: '0.125rem 0.5rem',
                borderRadius: '9999px',
                fontWeight: 500,
              }}
            >
              {completedJobs.length} Filings Ready
            </span>
          </div>
          <p
            style={{
              margin: '0.25rem 0 0 0',
              fontSize: '0.8125rem',
              color: '#64748b',
            }}
          >
            Includes {yearsList}
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={() => void handleBuildFullModel()}
            disabled={isGeneratingFull}
            style={{
              backgroundColor: '#16a34a',
              borderColor: '#16a34a',
              color: '#ffffff',
              padding: '0.45rem 0.85rem',
              fontSize: '0.8125rem',
              fontWeight: 600,
              borderRadius: '0.375rem',
              cursor: isGeneratingFull ? 'not-allowed' : 'pointer',
              opacity: isGeneratingFull ? 0.7 : 1,
            }}
            aria-label="Generate 6-Tab Model"
          >
            {isGeneratingFull ? 'Generating 6-Tab Model...' : 'Generate 6-Tab Model'}
          </button>

          {completedJobs.length >= 2 && (
            <button
              type="button"
              onClick={() => void handleBuildMultiYearModel()}
              disabled={isGenerating}
              style={{
                backgroundColor: '#2563eb',
                borderColor: '#2563eb',
                color: '#ffffff',
                padding: '0.45rem 0.85rem',
                fontSize: '0.8125rem',
                fontWeight: 500,
                borderRadius: '0.375rem',
                cursor: isGenerating ? 'not-allowed' : 'pointer',
                opacity: isGenerating ? 0.7 : 1,
              }}
              aria-label="Build Multi-Year Model"
            >
              {isGenerating ? 'Building Model...' : 'Build Multi-Year Model'}
            </button>
          )}

          {fullModelResult && (
            <a
              href={`${apiBase}${fullModelResult.download_url}`}
              download={`company_${company.company_id}_full_model.xlsx`}
              style={{
                backgroundColor: '#059669',
                borderColor: '#059669',
                color: '#ffffff',
                textDecoration: 'none',
                padding: '0.45rem 0.85rem',
                fontSize: '0.8125rem',
                fontWeight: 600,
                borderRadius: '0.375rem',
                display: 'inline-flex',
                alignItems: 'center',
              }}
              aria-label="Download Full Model (.xlsx)"
            >
              Download Full Model (.xlsx)
            </a>
          )}

          {generationResult && (
            <a
              href={`${apiBase}${generationResult.download_url}`}
              download={`${company.company_id}_multi_year.xlsx`}
              style={{
                backgroundColor: '#15803d',
                borderColor: '#15803d',
                color: '#ffffff',
                textDecoration: 'none',
                padding: '0.45rem 0.85rem',
                fontSize: '0.8125rem',
                fontWeight: 500,
                borderRadius: '0.375rem',
                display: 'inline-flex',
                alignItems: 'center',
              }}
              aria-label="Download Multi-Year Model (xlsx)"
            >
              Download Multi-Year Model (.xlsx)
            </a>
          )}
        </div>
      </div>

      {fullModelResult && (
        <div
          style={{
            marginTop: '0.75rem',
            paddingTop: '0.75rem',
            borderTop: '1px solid #e2e8f0',
            fontSize: '0.8125rem',
            color: '#15803d',
          }}
        >
          ? 6-Tab comprehensive financial model generated with{' '}
          {fullModelResult.total_cells_generated} total cells across{' '}
          {fullModelResult.years.length} fiscal years.
        </div>
      )}

      {generationResult && (
        <div
          style={{
            marginTop: '0.75rem',
            paddingTop: '0.75rem',
            borderTop: '1px solid #e2e8f0',
            fontSize: '0.8125rem',
            color: '#15803d',
          }}
        >
          ? Multi-year workbook generated with{' '}
          {generationResult.total_cells_generated} total cells across{' '}
          {generationResult.years.length} fiscal years.
        </div>
      )}

      {error && (
        <div
          style={{
            marginTop: '0.75rem',
            paddingTop: '0.75rem',
            borderTop: '1px solid #fee2e2',
            fontSize: '0.8125rem',
            color: '#b91c1c',
          }}
          role="alert"
        >
          {error}
        </div>
      )}
    </div>
  )
}
