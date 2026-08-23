import { describe, it, expect, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import CompanySelector from './CompanySelector'

describe('CompanySelector Component', () => {
  it('renders label and text input with datalist', () => {
    const html = renderToStaticMarkup(
      <CompanySelector
        selectedCompany=""
        onCompanyChange={vi.fn()}
        apiBase="http://localhost:8000"
      />
    )

    expect(html).toContain('Assign to Company (Optional)')
    expect(html).toContain('id="company-select-input"')
    expect(html).toContain('list="company-datalist"')
    expect(html).toContain('placeholder="Select existing or type new name..."')
    expect(html).not.toContain('Clear')
  })

  it('renders input with selected value and displays Clear button', () => {
    const html = renderToStaticMarkup(
      <CompanySelector
        selectedCompany="Acme Corporation"
        onCompanyChange={vi.fn()}
        apiBase="http://localhost:8000"
      />
    )

    expect(html).toContain('value="Acme Corporation"')
    expect(html).toContain('Clear')
    expect(html).toContain('Clear company selection')
  })
})
