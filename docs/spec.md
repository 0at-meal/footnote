# spec.md — Feature 1: Multi-File PDF Upload & Job Queueing

**Satisfies:** FR1  
**Phase:** 1 — Ingestion Pipeline  
**Status:** Draft

---

## What This Feature Does

1. Presents a frontend upload zone that accepts multiple PDF files via drag-and-drop or file-picker in a single session.
2. Validates each submitted file server-side (type and size) before a job record is created. A file that fails validation is rejected with a descriptive error message — it is never silently dropped and never partially accepted.
3. Creates a job record for each accepted file. The record carries: `filename`, `file_size_bytes`, `status` (one of `queued` | `extracting` | `done` | `failed`), and a `job_id`. This record is persisted and visible in a job list UI.
4. Exposes a target-metric selector per job, defaulting to **Adjusted EBITDA**. The selection is recorded in the job record before the job is enqueued.
5. On job submission, triggers the extraction pipeline (Feature 2) for each accepted file in queue order.

---

## What This Feature Does NOT Do

- **Does not parse, extract, or analyze PDF content.** Reading the file's financial data is Feature 2's responsibility. Feature 1 only validates that the file is a well-formed PDF within size limits.
- **Does not classify extracted items.** Classification is Feature 3.
- **Does not generate formulas or Excel output.** That is Feature 4.
- **Does not render the PDF for review.** That is Feature 5.
- **Does not support file formats other than PDF.** No `.docx`, `.xlsx`, `.html`, or image files — even if they contain financial statements.
- **Does not authenticate or authorize the uploader.** MVP is single-user, single-session by design (CONSTITUTION §6.10). No login, no role check, no per-user job isolation.
- **Does not allow editing a job record after submission.** Target metric selection is locked once a job moves out of `queued` status.
- **Does not provide a progress indicator for the extraction step itself.** Status transitions (`queued` → `extracting` → `done` / `failed`) are surfaced, but Feature 1 does not implement real-time progress within an active extraction.
- **Does not send file content to any remote service.** File bytes are written to local storage only. Groq API is not touched at this stage (CONSTITUTION §6.5).
- **Does not implement retry logic for failed jobs.** A `failed` job must be re-submitted by the user.

---

## Acceptance Criteria

1. **Multi-file queuing in one session.** A user can select or drag two or more PDF files simultaneously; all are enqueued as separate job records without requiring multiple submission actions.

2. **Invalid file type rejected with a clear error.** Submitting a non-PDF file (e.g., `.docx`, `.png`, `.xlsx`) results in a visible, named error per file (e.g., "resume.docx — unsupported file type"). The invalid file is not added to the job list. Valid files submitted alongside it are not affected.

3. **Oversized file rejected with a clear error.** A PDF exceeding the configured size ceiling (implementation must define a concrete byte limit; a reasonable default is 100 MB per file) is rejected with a message that states the file's actual size and the limit. The rejection does not affect other files in the same submission.

4. **Corrupt or unreadable PDF rejected at validation.** A file with a `.pdf` extension that cannot be parsed as a valid PDF object (e.g., a renamed `.jpg`, a truncated upload) is rejected server-side with a clear error. It is never added to the job list.

5. **Job record persisted with correct initial fields.** Each accepted file produces exactly one job record containing: `job_id` (unique, non-guessable), `filename` (original name as uploaded), `file_size_bytes` (exact), `status: queued`, `target_metric: "Adjusted EBITDA"` (or user-selected value), and `submitted_at` timestamp. No other fields are populated at this stage.

6. **Target metric selection recorded before queuing.** If the user changes the target metric selector before submission, the recorded `target_metric` reflects that selection — not the default. The metric cannot be changed after the job leaves `queued` status.

7. **Job list visible and accurate.** The job list UI shows all jobs from the current session with their current `status`. A page refresh does not lose job records — they survive via backend persistence.

8. **Job submission triggers extraction pipeline.** Each accepted job transitions from `queued` to `extracting` exactly once when the extraction pipeline picks it up. No job is processed twice in the same session without explicit re-submission by the user.

9. **No silent failures.** Any server-side error during file receipt or job creation (e.g., disk write failure, validation exception) surfaces a visible error to the user. The job is not left in an ambiguous half-created state.

10. **Empty submission rejected.** Submitting the upload form with no files selected produces an inline error. No network request is made to the job creation endpoint.

---

## Known Edge Cases

| # | Edge Case | Required Behavior |
|---|---|---|
| EC-1 | User submits the same filename twice in one session. | Two separate job records are created (deduplication is by `job_id`, not filename). Both are queued. |
| EC-2 | User submits a zero-byte PDF. | Rejected server-side as an invalid file. A zero-byte file cannot contain valid PDF content. |
| EC-3 | PDF is valid but password-protected. | Rejected at validation with a specific error: "file is encrypted / password-protected." Feature 1 does not attempt decryption. |
| EC-4 | Network interruption mid-upload. | The partially received file is discarded server-side. No job record is created. The user sees a connection error and must re-submit. |
| EC-5 | User closes the browser tab while jobs are queued. | Already-enqueued jobs continue processing server-side. Their records survive and are visible on reload (see AC-7). Jobs still in `queued` status at the frontend that were never sent to the server are lost — this is acceptable at MVP. |
| EC-6 | All files in a multi-file submission are invalid. | Every file is individually rejected with its own error. No job records are created. The job list is unchanged. |
| EC-7 | Mix of valid and invalid files in one submission. | Valid files produce job records and are queued normally. Invalid files are individually rejected with errors. The valid jobs are not held back. |
| EC-8 | Filename contains special characters or non-ASCII. | The original filename is stored as-is (UTF-8). The `job_id` is system-generated and independent of the filename. Filesystem storage uses the `job_id` as the file key, not the original name. |
| EC-9 | Duplicate upload of a file already in `extracting` or `done` status. | Treated as a new submission (see EC-1). No deduplication against prior-session records. |
| EC-10 | Target metric dropdown left at default and then form submitted. | `target_metric` records as `"Adjusted EBITDA"`. No validation error. This is the expected happy path. |
