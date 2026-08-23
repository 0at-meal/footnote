import { useEffect, useState } from 'react'
import type { CompanyRecord } from '../types/job'

interface Props {
  selectedCompany: string
  onCompanyChange: (name: string) => void
  apiBase?: string
}

export default function CompanySelector({
  selectedCompany,
  onCompanyChange,
  apiBase = 'http://localhost:8000',
}: Props) {
  const [companies, setCompanies] = useState<CompanyRecord[]>([])

  useEffect(() => {
    fetch(`${apiBase}/companies`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then((data: CompanyRecord[]) => {
        if (Array.isArray(data)) {
          setCompanies(data)
        }
      })
      .catch(() => {
        // Non-fatal if backend is offline or no companies exist yet
      })
  }, [apiBase])

  return (
    <div className="company-selector" style={{ marginBottom: '1.25rem' }}>
      <label
        htmlFor="company-select-input"
        className="company-selector__label"
        style={{
          display: 'block',
          fontSize: '0.8125rem',
          fontWeight: 600,
          color: '#374151',
          marginBottom: '0.375rem',
        }}
      >
        Assign to Company (Optional)
      </label>
      <div
        className="company-selector__control"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          maxWidth: '400px',
        }}
      >
        <input
          id="company-select-input"
          list="company-datalist"
          type="text"
          value={selectedCompany}
          onChange={(e) => onCompanyChange(e.target.value)}
          placeholder="Select existing or type new name..."
          className="company-selector__input"
          style={{
            flex: 1,
            padding: '0.5rem 0.75rem',
            fontSize: '0.875rem',
            borderRadius: '0.375rem',
            border: '1px solid #d1d5db',
            backgroundColor: '#ffffff',
            color: '#111827',
            outline: 'none',
          }}
          aria-label="Assign to Company"
        />
        <datalist id="company-datalist">
          {companies.map((c) => (
            <option key={c.company_id} value={c.name}>
              {c.ticker ? `${c.name} (${c.ticker})` : c.name}
            </option>
          ))}
        </datalist>
        {selectedCompany.trim().length > 0 && (
          <button
            type="button"
            onClick={() => onCompanyChange('')}
            className="company-selector__clear-btn"
            style={{
              padding: '0.4rem 0.6rem',
              fontSize: '0.75rem',
              color: '#6b7280',
              backgroundColor: '#f3f4f6',
              border: '1px solid #d1d5db',
              borderRadius: '0.375rem',
              cursor: 'pointer',
            }}
            aria-label="Clear company selection"
          >
            Clear
          </button>
        )}
      </div>
    </div>
  )
}
