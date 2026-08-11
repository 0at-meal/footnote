import { useState } from 'react'
import type { StagedFile } from '../types/job'

interface Props {
  stagedFiles: StagedFile[]
  /** Step 3 will wire the actual API call; this is a stub at Step 1. */
  onSubmit: () => void
}

function SubmitBar({ stagedFiles, onSubmit }: Props) {
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
        className="submit-bar__btn"
        onClick={handleClick}
      >
        {hasFiles
          ? `Submit ${count} file${count > 1 ? 's' : ''} for extraction`
          : 'Submit for extraction'}
      </button>
    </div>
  )
}

export default SubmitBar
