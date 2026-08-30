import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import DriftFlagCard from './DriftFlagCard'

describe('DriftFlagCard', () => {
  it('renders relabeled components with similarity score', () => {
    const html = renderToStaticMarkup(
      <DriftFlagCard
        flag={{
          flag_id: 'flag-1',
          job_id: 'job-1',
          entity: 'AAPL',
          target_metric: 'Adjusted EBITDA',
          filing_year: 2024,
          added_labels: [],
          removed_labels: [],
          relabeled_components: [
            {
              old_label: 'Stock-based comp expense',
              new_label: 'Share-based compensation expense',
              similarity_score: 0.88,
              is_confirmed: false,
            },
          ],
          prior_node_id: 'node-2023',
          created_at: '2026-08-30T00:00:00Z',
        }}
        apiBase="http://localhost:8000"
      />,
    )
    expect(html).toContain('Historical Drift Detected')
    expect(html).toContain('Cosmetic Relabelings')
    expect(html).toContain('Stock-based comp expense')
    expect(html).toContain('Share-based compensation expense')
    expect(html).toContain('88% match')
  })
})
