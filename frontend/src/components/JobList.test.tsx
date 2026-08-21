import { describe, it, expect, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import JobList from './JobList'
import type { JobRecord } from '../types/job'

describe('JobList Component', () => {
  it('renders Model Ready badge and Excel download link for completed jobs when model_ready is true', () => {
    const persistedJobs: JobRecord[] = [
      {
        job_id: 'job-abc-123',
        filename: 'sample_report.pdf',
        file_size_bytes: 2048,
        target_metric: 'Adjusted EBITDA',
        status: 'done',
        submitted_at: '2026-01-01T00:00:00Z',
        model_ready: true,
      },
    ]

    const html = renderToStaticMarkup(
      <JobList
        stagedFiles={[]}
        persistedJobs={persistedJobs}
        apiBase="http://localhost:8000"
        onMetricChange={vi.fn()}
        onRemove={vi.fn()}
      />
    )

    expect(html).toContain('Model Ready')
    expect(html).toContain('status-badge--model-ready')
    expect(html).toContain('href="http://localhost:8000/models/job-abc-123/download"')
    expect(html).toContain('download="job-abc-123_model.xlsx"')
    expect(html).toContain('Excel (.xlsx)')
    expect(html).toContain('Download Excel model for sample_report.pdf')
  })

  it('renders Awaiting Review badge and omits Excel download link when model_ready is false', () => {
    const persistedJobs: JobRecord[] = [
      {
        job_id: 'job-review-123',
        filename: 'complex_filing.pdf',
        file_size_bytes: 2048,
        target_metric: 'Adjusted EBITDA',
        status: 'done',
        submitted_at: '2026-01-01T00:00:00Z',
        model_ready: false,
      },
    ]

    const html = renderToStaticMarkup(
      <JobList
        stagedFiles={[]}
        persistedJobs={persistedJobs}
        apiBase="http://localhost:8000"
        onMetricChange={vi.fn()}
        onRemove={vi.fn()}
        onReview={vi.fn()}
      />
    )

    expect(html).toContain('Awaiting Review')
    expect(html).toContain('status-badge--awaiting-review')
    expect(html).toContain('Review')
    expect(html).not.toContain('/models/job-review-123/download')
    expect(html).not.toContain('Excel (.xlsx)')
  })

  it('does not render Excel download link for queued or extracting jobs', () => {
    const persistedJobs: JobRecord[] = [
      {
        job_id: 'job-queued-456',
        filename: 'queued_filing.pdf',
        file_size_bytes: 4096,
        target_metric: 'Free Cash Flow',
        status: 'queued',
        submitted_at: '2026-01-01T00:00:00Z',
      },
      {
        job_id: 'job-extracting-789',
        filename: 'extracting_filing.pdf',
        file_size_bytes: 8192,
        target_metric: 'Non-GAAP Net Income',
        status: 'extracting',
        submitted_at: '2026-01-01T00:00:00Z',
      },
    ]

    const html = renderToStaticMarkup(
      <JobList
        stagedFiles={[]}
        persistedJobs={persistedJobs}
        apiBase="http://localhost:8000"
        onMetricChange={vi.fn()}
        onRemove={vi.fn()}
      />
    )

    expect(html).not.toContain('/models/job-queued-456/download')
    expect(html).not.toContain('/models/job-extracting-789/download')
  })
})

