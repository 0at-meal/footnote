// @vitest-environment jsdom
import '../test/setupDom'
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import JobList from './JobList'
import type { JobRecord } from '../types/job'

describe('Not-found jobs (AUD-007, D2)', () => {
  it('shows the not-found status and reason, with no workbook or review action', () => {
    const job: JobRecord = {
      job_id: 'nf1',
      filename: 'no_bridge_10q.pdf',
      file_size_bytes: 10,
      status: 'not_found',
      target_metric: 'Adjusted EBITDA',
      submitted_at: '2026-10-03T00:00:00Z',
      model_ready: false,
      model_skip_reason: 'Adjusted EBITDA reconciliation not found in this filing',
    }
    render(<JobList stagedFiles={[]} persistedJobs={[job]} onRemove={() => {}} onReview={() => {}} />)
    expect(screen.getByLabelText('Status: Not found')).toBeTruthy()
    expect(screen.getByText('Adjusted EBITDA reconciliation not found in this filing')).toBeTruthy()
    expect(screen.queryByRole('link', { name: /Download Excel/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /^Review /i })).toBeNull()
  })
})
