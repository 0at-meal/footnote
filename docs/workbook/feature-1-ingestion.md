# Engineering Workbook — Feature 1: Multi-File PDF Upload & Job Queueing

**Module:** Ingestion Pipeline (`backend/app/ingestion/`, `frontend/src/`)  
**Phase:** 1 — Ingestion & Foundation  
**Status:** Completed & Audited  
**Author:** Antigravity Engineering  

---

## 1. Purpose

Footnote processes corporate financial statements (PDF 10-Ks) to extract structured financial metrics and construct dynamic financial models. Before Feature 1, the codebase possessed no entry mechanism to receive, validate, persist, or track PDF uploads.

Feature 1 establishes the **Ingestion Pipeline**: the resilient front door for the system. It enables financial analysts to upload multiple PDF 10-K filings in a single session, select target metrics per filing (such as *Adjusted EBITDA* or *Net Income*), validates that uploaded files are authentic, uncorrupted, unencrypted PDFs under 100 MB, persists file bytes atomically to local disk storage, assigns unique job identifiers, and enqueues them for background extraction with real-time UI status synchronization (`queued` → `extracting` → `done` / `failed`).

---

## 2. Scope of Change

### Backend Domain Module (`backend/app/ingestion/`)
*Encapsulates upload receipt, validation rules, persistence, and background task dispatch. Isolated per CONSTITUTION §3.8.*

- **`models.py`**: Data contracts defining `FileValidationResult`, `ValidationResponse`, `JobStatus` enum, `JobRecord`, `SubmitResponse`, `GetJobsResponse`, and `ALLOWED_TARGET_METRICS` whitelist.
- **`validation.py`**: Pure 5-layer server-side PDF validation engine (zero-byte, size ceiling, magic header bytes, PyMuPDF structural parse, password check).
- **`repository.py`**: Storage manager handling atomic PDF disk writes (`backend/data/uploads/<job_id>.pdf`) and JSON metadata tracking (`backend/data/jobs.json`).
- **`pipeline.py`**: Background task orchestrator executing job status transitions (`queued` → `extracting` → `done` / `failed`).
- **`router.py`**: FastAPI route handlers for `/upload/validate`, `POST /upload/jobs`, and `GET /upload/jobs`.

### Backend Application Root (`backend/app/`)
- **`main.py`**: Application entry point registering the ingestion router, configuring CORS for `localhost:5173`, and patching OpenAPI schemas for file array pickers.

### Frontend Application (`frontend/src/`)
- **`types/job.ts`**: TypeScript type definitions matching backend models (`JobRecord`, `JobStatus`, `StagedFile`, `TargetMetric`).
- **`lib/validation.ts`**: Pre-flight client-side MIME/extension checker for instant drag-and-drop user feedback.
- **`components/UploadZone.tsx`**: Accessible drag-and-drop and file-picker upload container.
- **`components/JobList.tsx`**: Queue table rendering staged pending uploads (metric select, remove button) and persisted jobs (locked metrics, status badges).
- **`components/SubmitBar.tsx`**: Action bar with file counters, loading states, and empty-state error warnings.
- **`App.tsx`**: App layout root managing state restoration on mount, multipart submission, staged queue clearing, and 3-second active job status auto-polling.
- **`App.css`**: Design tokens and styles for table layouts, status badges, error banners, and dropzone interactions.

### Test Suite (`backend/tests/ingestion/`)
- **`test_validation.py`**: 15 unit tests covering all 5 validation tiers and boundary conditions.
- **`test_router.py`**: 10 integration tests for `/upload/validate`.
- **`test_repository.py`**: 11 unit tests for atomic storage, JSON persistence, non-ASCII handling, UUID generation, and status updates.
- **`test_jobs_router.py`**: 11 integration tests for `POST /upload/jobs` and `GET /upload/jobs`.
- **`test_pipeline.py`**: 2 unit tests for background task execution and failure transitions.

### Workspace Configuration
- **`.gitignore`**: Added `backend/data/` to prevent uploaded PDFs and runtime `jobs.json` from entering version control.

---

## 3. Core Abstractions

### 1. `JobRepository` (`backend/app/ingestion/repository.py`)
- **Responsibility**: Encapsulates all filesystem interaction for raw PDF storage and JSON record persistence.
- **Inputs/Outputs**: Takes raw PDF bytes, original filenames, and target metrics; returns persisted `JobRecord` objects.
- **Rationale**: Keeps disk mechanics (atomic `.tmp` writes, `os.replace`, JSON read-modify-write) isolated from HTTP handlers. Injected via FastAPI's `Depends(get_repository)` to enable zero-side-effect test overrides using `pytest`'s `tmp_path`.

### 2. `validate_pdf_bytes` (`backend/app/ingestion/validation.py`)
- **Responsibility**: Pure validation function implementing a 5-tier fail-fast evaluation hierarchy.
- **Inputs/Outputs**: `(filename: str, content: bytes) -> FileValidationResult`
- **Rationale**: Completely decoupled from web frameworks and disk I/O. Used for validation-only pre-flight requests (`/upload/validate`) or batch job submissions (`/upload/jobs`).

### 3. `process_queued_job` (`backend/app/ingestion/pipeline.py`)
- **Responsibility**: Background worker function executing state transitions (`queued` → `extracting` → `done` / `failed`).
- **Inputs/Outputs**: `(job_id: str, repo: JobRepository) -> None`
- **Rationale**: Adheres strictly to **CONSTITUTION §3.8 Isolation Rule** (`ingestion/` must not import from downstream modules `extraction/` or `classification/`). Establishes an asynchronous execution bridge.

### 4. Dual-Queue State Model (`App.tsx` & `JobList.tsx`)
- **Responsibility**: Separates local client state awaiting submission (`StagedFile` with client-generated `crypto.randomUUID()`) from server-confirmed records (`JobRecord` with server-assigned `job_id`).
- **Rationale**: Allows analysts to adjust metrics or remove staged files locally without firing premature API requests or leaving orphan records on the server.

---

## 4. Interfaces & Contracts

### REST Endpoints

#### 1. `POST /upload/jobs`
- **Authentication**: None (MVP single-user local context, CONSTITUTION §6.10).
- **Request Format**: `multipart/form-data`
  - `files`: `list[UploadFile]` (PDF byte streams)
  - `target_metrics`: `list[str]` (parallel-indexed target metrics)
- **Validation**: `len(files) == len(target_metrics)` (HTTP 422 if mismatched); `metric in ALLOWED_TARGET_METRICS` (HTTP 422 if invalid).
- **Response Format (`200 OK`)**:
  ```json
  {
    "created_jobs": [
      {
        "job_id": "c9b7e3f2-1a4d-4e9e-8b6f-2d3e4f5a6b7c",
        "filename": "annual_report.pdf",
        "file_size_bytes": 1048576,
        "status": "queued",
        "target_metric": "Adjusted EBITDA",
        "submitted_at": "2026-08-12T01:00:00Z"
      }
    ],
    "rejections": [
      {
        "filename": "resume.docx",
        "accepted": false,
        "error_message": "unsupported file type — only PDF is accepted"
      }
    ]
  }
  ```

#### 2. `GET /upload/jobs`
- **Authentication**: None.
- **Response Format (`200 OK`)**:
  ```json
  {
    "jobs": [ /* array of JobRecord objects */ ]
  }
  ```

#### 3. `POST /upload/validate`
- **Request Format**: `multipart/form-data` (`files`: `list[UploadFile]`)
- **Response Format (`200 OK`)**: `{"results": [ /* array of FileValidationResult */ ]}`

### On-Disk Storage Layout (`backend/data/`)
- `backend/data/uploads/<job_id>.pdf`: Raw PDF byte stream keyed strictly by UUIDv4 `job_id`.
- `backend/data/jobs.json`: UTF-8 JSON array containing all persisted `JobRecord` dictionaries.

---

## 5. Control Flow — The Happy Path

```
 [User] Drag & Drop PDFs ──> [UploadZone.tsx] (isPdf check) ──> Staged Queue (State)
                                                                       │
 [Submit Button Click] ◄── [SubmitBar.tsx] ◄── Select Target Metric ───┘
          │
          ▼
 [App.tsx] handleSubmit() ──> POST /upload/jobs (multipart/form-data)
                                    │
                                    ▼
                          [FastAPI router.py]
                           1. Check length parity & metric whitelist (422 on error)
                           2. Loop through files & run validate_pdf_bytes()
                                    │
                                    ▼
                         [validation.py (5 Tiers)]
                          - Zero-byte check
                          - 100 MB size ceiling
                          - %PDF magic bytes check
                          - PyMuPDF structural parse
                          - Encrypted/password check
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                   (If Accepted)         (If Rejected)
                         │                     │
                [repository.py]          Append to rejections list
                 - Write .pdf.tmp              │
                 - Atomic os.replace           ▼
                 - Append to jobs.json   Return SubmitResponse (200 OK)
                         │                     │
                         ▼                     ▼
                [BackgroundTasks]       [App.tsx] Show Error Banner
                 Schedule task                 │
                         │                     ▼
                         ▼              [JobList.tsx] Render Jobs
            [process_queued_job]         - Lock enqueued metrics
             1. Set 'extracting'         - Auto-poll status every 3s
             2. Run processing           - Update badge: Queued → Extracting → Done
             3. Set 'done'
```

1. **File Selection**: The user drops `fy23.pdf` and `fy24.pdf` into `UploadZone.tsx`.
2. **Client Pre-flight**: `isPdf()` validates extensions/MIME types. Files enter React `stagedFiles` state with default metric `"Adjusted EBITDA"`.
3. **Metric Selection**: User changes `fy24.pdf` target metric to `"Net Income"`.
4. **Form Dispatch**: User clicks `SubmitBar.tsx`. `handleSubmit()` builds `FormData` containing files and metrics arrays.
5. **Backend Receipt**: `POST /upload/jobs` receives the payload. `router.py` verifies metric whitelist membership and length equality.
6. **Server-Side Validation**: `validate_pdf_bytes()` executes all 5 validation tiers.
7. **Atomic Disk Persistence**:
   - `save_job()` writes bytes to `uploads/<job_id>.pdf.tmp`, then executes atomic `os.replace` to `uploads/<job_id>.pdf`.
   - Appends a new `JobRecord` (`status="queued"`, ISO 8601 UTC `submitted_at`) to `data/jobs.json`.
8. **Worker Scheduling**: `BackgroundTasks.add_task(process_queued_job, job_id, repo)` queues background processing.
9. **UI Refresh**: `App.tsx` appends created jobs to `persistedJobs` state and removes accepted entries from `stagedFiles` array.
10. **Background Execution & Status Sync**:
    - `process_queued_job` updates job status in `jobs.json` to `"extracting"`.
    - `App.tsx` active-job polling effect triggers `GET /upload/jobs` every 3 seconds while active jobs exist.
    - `JobList.tsx` renders an amber **Extracting** badge.
    - Worker completes processing and updates status to `"done"`. Next poll updates badge to green **Done**.

---

## 6. Business Rules & Edge Cases

- **EC-1 (Duplicate Filenames)**: Uploading two identical filenames in one session creates two distinct `JobRecord` entries with unique UUIDv4 `job_id`s. Staged queue removal iterates the full `created_jobs` array to ensure both staged instances are removed.
- **EC-2 (Zero-Byte File)**: Rejected immediately: `"file is empty — cannot contain valid PDF content"`.
- **EC-3 (Password Protection)**: PyMuPDF checks `doc.needs_pass`. Rejection: `"file is encrypted / password-protected"`.
- **EC-7 (Mixed Submissions)**: When valid and invalid files are uploaded together, valid files are enqueued normally while invalid files return in `rejections` and render in a dismissible error banner.
- **EC-8 (Non-ASCII Filenames)**: Filenames containing non-ASCII characters (e.g., `財務報告書_2024.pdf`) are stored as-is in UTF-8. Disk storage keys files by `job_id.pdf` to avoid filesystem encoding bugs.
- **EC-10 (Default Metric)**: Omitting metric selection records `"Adjusted EBITDA"` without validation errors.

---

## 7. Key Decisions & Trade-offs

1. **FastAPI Dependency Injection (`Depends(get_repository)`)**
   - *Decision*: Injected `JobRepository` via FastAPI dependency injection.
   - *Rationale*: Allows pytest suites to override the dependency with a `tmp_path`-backed repository without mocking filesystem calls or writing files to production paths.

2. **Atomic Temp-and-Rename Writes (`os.replace`)**
   - *Decision*: Write PDF bytes to `<job_id>.pdf.tmp` before atomically renaming to `<job_id>.pdf`.
   - *Rationale*: Prevents partial disk writes (due to process interrupts or disk full errors) from leaving corrupt PDFs that could crash downstream extraction tasks.

3. **Single-User MVP Storage (CONSTITUTION §6.10)**
   - *Decision*: `jobs.json` uses in-memory read-modify-write persistence without file locking.
   - *Trade-off*: Concurrent HTTP writes could result in race conditions. Acceptable because Footnote MVP is explicitly single-user and single-session; avoids introducing database overhead during Phase 1.

4. **Condition-Gated Auto-Polling vs. WebSockets**
   - *Decision*: Implemented 3-second interval polling gated on `hasActiveJobs`.
   - *Rationale*: Delivers real-time status updates without the operational complexity of WebSocket or Server-Sent Events (SSE) connections.

---

## 8. Dependencies Introduced

- **PyMuPDF (`pymupdf`)**: Selected for fast, local PDF header inspection, structural parsing, and encryption detection without external API calls (CONSTITUTION §6.5).
- **FastAPI (`fastapi`, `pydantic`)**: Handles OpenAPI endpoint generation, request validation, and asynchronous background worker execution.

---

## 9. What Was Verified

### Automated Test Suite (50/50 Pytest Pass)
- **Validation Rules**: Verified zero-byte handling, size limits (>100 MB), magic bytes, truncated streams, and password checks.
- **Repository Logic**: Tested UUIDv4 generation, atomic `.tmp` file replacement, UTF-8 character preservation, and `jobs.json` updates.
- **HTTP Endpoint Contracts**: Tested 200 OK split responses, 422 length mismatches, and 422 metric whitelist enforcement.
- **Background Pipeline**: Tested `queued` → `extracting` → `done` state transitions and error propagation to `failed`.
- **Static Analysis**: Enforced zero issues in `mypy --strict` (7 source files), clean `ruff` linting, 0 errors in `npx tsc --noEmit`, clean `eslint`, and 15/15 passing Vitest tests.

### Manual Verification
- Verified drag-and-drop handling and multi-file batch uploads on `http://localhost:5173`.
- Verified Network tab polling behavior and automatic status badge transitions from **Queued** → **Extracting** → **Done**.

---

## 10. Open Risks & Follow-ups

1. **Extraction Worker Integration (Feature 2 Bridge)**: `pipeline.py` currently uses a `time.sleep(1.0)` placeholder. Feature 2 will replace this stub with Docling structural parsing and PyMuPDF layout extraction.
2. **JSON Storage Scalability**: `jobs.json` rewrites the full record array on every status update. If session job volume increases significantly, this should be migrated to SQLite when graph persistence is introduced (CONSTITUTION §4.5).
