import type { StagedFile, TargetMetric } from '../types/job'
import { TARGET_METRICS } from '../types/job'

interface Props {
  stagedFiles: StagedFile[]
  onMetricChange: (id: string, metric: TargetMetric) => void
  onRemove: (id: string) => void
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function JobList({ stagedFiles, onMetricChange, onRemove }: Props) {
  if (stagedFiles.length === 0) {
    return (
      <div className="job-list job-list--empty">
        <svg
          width="32"
          height="32"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <path d="M14 2v6h6M12 18v-6M9 15h6" />
        </svg>
        <p>No files staged. Add PDFs above to get started.</p>
      </div>
    )
  }

  return (
    <div className="job-list">
      <table className="job-table" aria-label="Staged files">
        <thead>
          <tr>
            <th scope="col">File</th>
            <th scope="col">Size</th>
            <th scope="col">Target Metric</th>
            <th scope="col">
              <span className="sr-only">Remove</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {stagedFiles.map((sf) => (
            <tr key={sf.id} className="job-table__row">
              <td className="job-table__filename">
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                  className="job-table__pdf-icon"
                >
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <path d="M14 2v6h6" />
                </svg>
                <span title={sf.filename}>{sf.filename}</span>
              </td>
              <td className="job-table__size">{formatBytes(sf.file_size_bytes)}</td>
              <td className="job-table__metric">
                <select
                  id={`metric-${sf.id}`}
                  value={sf.target_metric}
                  onChange={(e) => onMetricChange(sf.id, e.target.value as TargetMetric)}
                  aria-label={`Target metric for ${sf.filename}`}
                >
                  {TARGET_METRICS.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </td>
              <td className="job-table__remove">
                <button
                  type="button"
                  className="job-table__remove-btn"
                  onClick={() => onRemove(sf.id)}
                  aria-label={`Remove ${sf.filename}`}
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    aria-hidden="true"
                  >
                    <path d="M18 6 6 18M6 6l12 12" />
                  </svg>
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default JobList
