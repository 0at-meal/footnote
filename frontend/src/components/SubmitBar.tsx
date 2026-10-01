import { useState } from 'react'
import { ArrowRight, Loader2 } from 'lucide-react'
import type { StagedFile } from '../types/job'

interface Props {
  stagedFiles: StagedFile[]
  /** Step 3: wired to the real API call in App.tsx. */
  onSubmit: () => void
  /** True while the POST /upload/jobs request is in flight. */
  isSubmitting: boolean
}

function SubmitBar({ stagedFiles, onSubmit, isSubmitting }: Props) {
  const [showEmptyError, setShowEmptyError] = useState(false)

  const count = stagedFiles.length
  const hasFiles = count > 0

  function handleClick() {
    if (!hasFiles) {
      setShowEmptyError(true)
      return
    }
    setShowEmptyError(false)
    onSubmit()
  }

  return (
    <div className="submit-bar">
      {showEmptyError && !hasFiles && (
        <p
          className="submit-bar__error"
          role="alert"
          aria-live="assertive"
        >
          No files selected.
        </p>
      )}
      <button
        id="submit-btn"
        type="button"
        className="fn-btn fn-btn--primary fn-btn--lg submit-bar__btn"
        onClick={handleClick}
        disabled={isSubmitting}
        aria-busy={isSubmitting}
      >
        {isSubmitting ? (
          <>
            <Loader2 size={16} className="fn-spinner" aria-hidden="true" />
            <span>Submitting…</span>
          </>
        ) : (
          <>
            <span>
              {hasFiles
                ? `Submit ${count} file${count > 1 ? 's' : ''} for extraction`
                : 'Submit for extraction'}
            </span>
            <ArrowRight size={16} aria-hidden="true" />
          </>
        )}
      </button>
    </div>
  )
}

export default SubmitBar
