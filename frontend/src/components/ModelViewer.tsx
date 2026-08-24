import { useState } from 'react'
import './ModelViewer.css'

export type ModelTab =
  | 'executive_summary'
  | 'income_statement'
  | 'ebitda_bridge'
  | 'cash_flow'
  | 'balance_sheet'
  | 'audit_trail'

interface Props {
  jobId: string
  companyName?: string
  apiBase?: string
  onBack: () => void
}

const TABS: { id: ModelTab; label: string }[] = [
  { id: 'executive_summary', label: 'Executive Summary' },
  { id: 'income_statement', label: 'Income Statement' },
  { id: 'ebitda_bridge', label: 'EBITDA Bridge' },
  { id: 'cash_flow', label: 'Cash Flow' },
  { id: 'balance_sheet', label: 'Balance Sheet' },
  { id: 'audit_trail', label: 'Audit Trail' },
]

export default function ModelViewer({
  jobId,
  companyName = 'Financial Model',
  apiBase = 'http://localhost:8000',
  onBack,
}: Props) {
  const [activeTab, setActiveTab] = useState<ModelTab>('executive_summary')

  return (
    <div className="model-viewer" aria-label="Financial Model Viewer">
      <header className="model-viewer__header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <button
            type="button"
            className="review-header__back-btn"
            onClick={onBack}
            aria-label="Back"
          >
            ? Back
          </button>
          <h1 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 600, color: 'var(--text-h)' }}>
            {companyName} ? 6-Tab Financial Model
          </h1>
        </div>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <a
            href={`${apiBase}/models/${jobId}/download`}
            className="review-btn--generate"
            style={{
              textDecoration: 'none',
              display: 'inline-flex',
              alignItems: 'center',
              borderRadius: '6px',
            }}
            download={`${jobId}_model.xlsx`}
            aria-label="Download Excel Model"
          >
            Download .xlsx
          </a>
        </div>
      </header>

      <nav className="model-viewer__tabs" role="tablist" aria-label="Statement Tabs">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            className={`model-viewer__tab ${activeTab === tab.id ? 'model-viewer__tab--active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <main className="model-viewer__content">
        <div style={{ padding: '12px', background: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
          <h2 style={{ fontSize: '1rem', fontWeight: 600, color: '#1e293b', marginTop: 0, marginBottom: '12px' }}>
            {TABS.find((t) => t.id === activeTab)?.label}
          </h2>
          <p style={{ color: '#64748b', fontSize: '0.875rem' }}>
            Interactive 6-tab financial statement model preview with live Excel formulas and provenance.
          </p>
          <div style={{ display: 'flex', gap: '16px', fontSize: '0.75rem', marginTop: '12px', padding: '8px 12px', background: '#f8fafc', borderRadius: '6px' }}>
            <span style={{ color: '#0000ff', fontWeight: 600 }}>? Blue: Hardcoded Input</span>
            <span style={{ color: '#15803d', fontWeight: 600 }}>? Green: Cross-Sheet Link</span>
            <span style={{ color: '#000000', fontWeight: 600 }}>? Black: Excel Formula</span>
          </div>
        </div>
      </main>
    </div>
  )
}
