import { useState, useRef } from 'react'
import type { DragEvent, ChangeEvent } from 'react'
import type { RejectedFile } from '../types/job'
import { isPdf } from '../lib/validation'

interface Props {
  onFilesAdded: (files: File[]) => void
}


function UploadZone({ onFilesAdded }: Props) {
  const [isDragOver, setIsDragOver] = useState(false)
  const [rejections, setRejections] = useState<RejectedFile[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  function processFiles(fileList: FileList | File[]) {
    const files = Array.from(fileList)
    const accepted: File[] = []
    const rejected: RejectedFile[] = []

    for (const file of files) {
      if (isPdf(file)) {
        accepted.push(file)
      } else {
        rejected.push({ filename: file.name, reason: 'unsupported file type' })
      }
    }

    setRejections(rejected)
    if (accepted.length > 0) {
      onFilesAdded(accepted)
    }
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setIsDragOver(false)
    processFiles(e.dataTransfer.files)
  }

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setIsDragOver(true)
  }

  function handleDragEnter(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setIsDragOver(true)
  }

  function handleDragLeave(e: DragEvent<HTMLDivElement>) {
    // Only clear when leaving the zone itself, not its children.
    // instanceof guard avoids a bare type assertion on relatedTarget.
    const leaving = e.relatedTarget
    if (leaving instanceof Node && e.currentTarget.contains(leaving)) return
    setIsDragOver(false)
  }

  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    if (e.target.files && e.target.files.length > 0) {
      processFiles(e.target.files)
      // Reset so the same file can be re-added after removal
      e.target.value = ''
    }
  }

  function handleBrowseClick() {
    inputRef.current?.click()
  }

  return (
    <div
      className={`upload-zone${isDragOver ? ' upload-zone--drag-over' : ''}`}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      aria-label="PDF upload area"
    >
      <svg
        className="upload-zone__icon"
        width="48"
        height="48"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M12 15V3m0 0L8.5 6.5M12 3l3.5 3.5" />
        <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3" />
      </svg>

      <p className="upload-zone__headline">
        {isDragOver ? 'Release to add files' : 'Drag & drop PDF files here'}
      </p>
      <p className="upload-zone__sub">or</p>

      <button
        type="button"
        className="upload-zone__browse-btn"
        onClick={handleBrowseClick}
      >
        Browse files
      </button>

      <input
        ref={inputRef}
        id="file-input"
        type="file"
        accept=".pdf,application/pdf"
        multiple
        onChange={handleChange}
        style={{ display: 'none' }}
        aria-label="Select PDF files"
      />

      <p className="upload-zone__hint">PDF only · Max 100 MB per file</p>

      {rejections.length > 0 && (
        <ul
          className="upload-zone__rejections"
          role="alert"
          aria-live="assertive"
        >
          {rejections.map((r, i) => (
            <li key={i} className="upload-zone__rejection-item">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 8v4m0 4h.01" />
              </svg>
              <span>
                <strong>{r.filename}</strong> — {r.reason}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default UploadZone
