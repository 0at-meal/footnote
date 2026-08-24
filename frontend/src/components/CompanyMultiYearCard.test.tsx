import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import CompanyMultiYearCard from './CompanyMultiYearCard'
import type { CompanyWithJobs } from '../types/job'

describe('CompanyMultiYearCard Component', () => {
  it('does not render if 0 completed jobs exist for the company', () => {
    const company: CompanyWithJobs = {
      company_id: 'comp-1',
      name: 'Queued Corp',
      ticker: 'QC',
      created_at: '2026-01-01T00:00:00Z',
      job_ids: ['job-1'],
      jobs: [
        {
          job_id: 'job-1',
          filename: 'report_2023.pdf',
          file_size_bytes: 1024,
          status: 'queued',
          target_metric: 'Adjusted EBITDA',
          submitted_at: '2026-01-01T00:00:00Z',
          filing_year: 2023,
          company_id: 'comp-1',
        },
      ],
    }

    const html = renderToStaticMarkup(
      <CompanyMultiYearCard company={company} apiBase="http://localhost:8000" />
    )

    expect(html).toBe('')
  })

  it('renders 6-Tab Model button when 1 completed job exists', () => {
    const company: CompanyWithJobs = {
      company_id: 'comp-1',
      name: 'Single Filing Corp',
      ticker: 'SFC',
      created_at: '2026-01-01T00:00:00Z',
      job_ids: ['job-1'],
      jobs: [
        {
          job_id: 'job-1',
          filename: 'report_2023.pdf',
          file_size_bytes: 1024,
          status: 'done',
          target_metric: 'Adjusted EBITDA',
          submitted_at: '2026-01-01T00:00:00Z',
          filing_year: 2023,
          company_id: 'comp-1',
        },
      ],
    }

    const html = renderToStaticMarkup(
      <CompanyMultiYearCard company={company} apiBase="http://localhost:8000" />
    )

    expect(html).toContain('Company Financial Models: Single Filing Corp (SFC)')
    expect(html).toContain('1 Filings Ready')
    expect(html).toContain('Generate 6-Tab Model')
  })

  it('renders Multi-Year card with both 6-Tab and Multi-Year buttons when >= 2 jobs are completed', () => {
    const company: CompanyWithJobs = {
      company_id: 'comp-multi',
      name: 'Acme Holdings',
      ticker: 'ACME',
      created_at: '2026-01-01T00:00:00Z',
      job_ids: ['job-1', 'job-2', 'job-3'],
      jobs: [
        {
          job_id: 'job-1',
          filename: 'report_2021.pdf',
          file_size_bytes: 1024,
          status: 'done',
          target_metric: 'Adjusted EBITDA',
          submitted_at: '2026-01-01T00:00:00Z',
          filing_year: 2021,
          company_id: 'comp-multi',
        },
        {
          job_id: 'job-2',
          filename: 'report_2022.pdf',
          file_size_bytes: 2048,
          status: 'done',
          target_metric: 'Adjusted EBITDA',
          submitted_at: '2026-01-02T00:00:00Z',
          filing_year: 2022,
          company_id: 'comp-multi',
        },
        {
          job_id: 'job-3',
          filename: 'report_2023.pdf',
          file_size_bytes: 4096,
          status: 'done',
          target_metric: 'Adjusted EBITDA',
          submitted_at: '2026-01-03T00:00:00Z',
          filing_year: 2023,
          company_id: 'comp-multi',
        },
      ],
    }

    const html = renderToStaticMarkup(
      <CompanyMultiYearCard company={company} apiBase="http://localhost:8000" />
    )

    expect(html).toContain('Company Financial Models: Acme Holdings (ACME)')
    expect(html).toContain('3 Filings Ready')
    expect(html).toContain('Includes FY2021, FY2022, FY2023')
    expect(html).toContain('Generate 6-Tab Model')
    expect(html).toContain('Build Multi-Year Model')
  })
})
