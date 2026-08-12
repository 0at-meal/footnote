import { useState } from 'react'
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

  // Clear the empty-state error as soon as a file is staged.
  if (hasFiles && showEmptyError) {
    setShowEmptyError(false)
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
        className="submit-bar__btn"
        onClick={handleClick}
        disabled={isSubmitting}
        aria-busy={isSubmitting}
      >
        {isSubmitting
          ? 'Submitting…'
          : hasFiles
            ? `Submit ${count} file${count > 1 ? 's' : ''} for extraction`
            : 'Submit for extraction'}
      </button>
    </div>
  )
}

export default SubmitBar
