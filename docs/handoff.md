# Development Agent Handoff — Footnote: Feature 1

---

## HANDOFF TO: Development Agent 2

---

## CONTEXT: What has been done so far

### Feature 1, Step 1 — Frontend Upload Zone (DONE ✅)

**Commit:** `1b22975 feat(upload): drag-and-drop upload zone with pdf ingestion`

**What was built:**
A complete drag-and-drop frontend upload interface using React 19 + TypeScript. Files are selected, client-side validated, and held in local React state as a staged queue. **No network request is made yet** — `handleSubmit()` in `App.tsx` is an intentional `console.log` stub.

**Key files:**

| File | What it does |
|---|---|
| `frontend/src/types/job.ts` | Domain types: `StagedFile`, `RejectedFile`, `TargetMetric`, `TARGET_METRICS`, `DEFAULT_METRIC` |
| `frontend/src/lib/validation.ts` | `isPdf(file): boolean` — MIME check with extension fallback for drag-and-drop |
| `frontend/src/components/UploadZone.tsx` | Drag-and-drop + file picker component. Calls `onFilesAdded(files: File[])` on parent |
| `frontend/src/components/JobList.tsx` | Staged file table: per-row `TargetMetric` dropdown + remove button |
| `frontend/src/components/SubmitBar.tsx` | Total size/count display + submit button; guards against empty submission |
| `frontend/src/App.tsx` | Orchestrator: owns `stagedFiles: StagedFile[]` state; `handleSubmit()` is a stub |

**Critical `StagedFile` shape** (frozen field names per CONSTITUTION §2.3):
```ts
type StagedFile = {
  id: string             // crypto.randomUUID() — client-only, NOT the backend job_id
  file: File             // raw browser File object
  filename: string       // original filename, UTF-8
  file_size_bytes: number
  target_metric: TargetMetric  // default: 'Adjusted EBITDA'
}
```

---

### Feature 1, Step 2 — Server-Side PDF Validation (DONE ✅)

**Commits:**
- `6c198fa feat(ingestion): server-side pdf validation before job acceptance`
- `fabb134 fix(ingestion): add format binary to openapi schema for swagger ui file picker`

**What was built:**
A FastAPI backend app (`backend/app/`) with a single `POST /upload/validate` endpoint. It receives multipart-uploaded files, runs 5-layer byte-level validation per file, and returns per-file results. **No job records are created, no files are stored to disk.**

**Backend package structure:**
```
backend/
  app/
    main.py                   ← FastAPI app, OpenAPI schema override
    ingestion/
      __init__.py
      models.py               ← Pydantic: FileValidationResult, ValidationResponse
      validation.py           ← validate_pdf_bytes(filename, content) → FileValidationResult
      router.py               ← POST /upload/validate
    extraction/               ← empty stubs (Feature 2)
    classification/           ← empty stubs (Feature 3)
    formula_engine/           ← empty stubs (Feature 4)
    excel_export/             ← empty stubs (Feature 4)
    audit_report/             ← empty stubs (Feature 8)
  tests/
    ingestion/
      test_validation.py      ← 15 unit tests
      test_router.py          ← 11 integration tests
  pytest.ini                  ← pythonpath = . (run from backend/)
```

**`validate_pdf_bytes` check order** (fast → slow):
1. `len(content) == 0` → rejected: "file is empty"
2. `len(content) > 104_857_600` → rejected: "file size X.X MB exceeds the 100 MB limit"
3. `content[:4] != b'%PDF'` → rejected: "unsupported file type — only PDF is accepted"
4. `pymupdf.open()` raises `FileDataError` → rejected: "corrupted or truncated"
5. `doc.needs_pass == True` → rejected: "file is encrypted / password-protected"
6. All pass → `accepted=True, error_message=None`

**API contract** (live at `http://localhost:8000` when uvicorn is running):
```
POST /upload/validate
Content-Type: multipart/form-data
Body field: files  (list[UploadFile], required)

Response 200:
{
  "results": [
    { "filename": "annual.pdf", "accepted": true,  "error_message": null },
    { "filename": "bad.docx",   "accepted": false, "error_message": "unsupported file type — only PDF is accepted" }
  ]
}

Response 422: when 'files' field is missing entirely.
```

**Per-file rejection is NOT an HTTP error** — always returns 200 with per-file booleans.

**Pydantic models** (in `backend/app/ingestion/models.py`):
```python
class FileValidationResult(BaseModel):
    filename: str
    accepted: bool
    error_message: str | None = None

class ValidationResponse(BaseModel):
    results: list[FileValidationResult]
```

---

## CURRENT STATE: Where things stand right now

- **Git branch:** `main`, fully pushed to `https://github.com/0at-meal/footnote.git`
- **Latest commit:** `fabb134` — all 3 feature commits ahead of original scaffold
- **Working tree:** clean (nothing uncommitted)
- **Tests:** 26/26 backend pytest pass; 15/15 frontend Vitest pass
- **Type checkers:** mypy strict 0 errors; tsc --noEmit 0 errors; ruff 0 warnings; eslint 0 warnings

**What does NOT exist yet (Step 3's responsibility):**
- No `JobRecord` model (no `job_id`, `status`, `submitted_at` fields)
- No file persistence to disk (no `data/uploads/` directory)
- No `jobs.json` or equivalent storage
- No `GET /upload/jobs` endpoint
- No `POST /upload/jobs` endpoint (Step 3 upgrades the flow: validate → save → create record)
- No frontend API calls (frontend `handleSubmit` is a `console.log` stub)
- No job list persistence across page refresh

---

## NEXT STEPS: Feature 1, Step 3 — Job Metadata Persistence & Visible Job List

**From the spec (`docs/spec.md` AC-5, AC-7, AC-8, EC-1, EC-8):**

The step must deliver:

1. **`POST /upload/jobs`** — new endpoint that replaces `/upload/validate` in the submission flow:
   - Validate each file (reuse `validate_pdf_bytes`).
   - For accepted files: write bytes to `data/uploads/<job_id>.pdf` (filename is `job_id`, not original name — EC-8).
   - Create a `JobRecord` with `job_id` (UUIDv4), `filename`, `file_size_bytes`, `status: "queued"`, `target_metric`, `submitted_at` (ISO UTC).
   - Persist all records to `data/jobs.json`.
   - Return: `{ created_jobs: JobRecord[], rejections: FileValidationResult[] }`.

2. **`GET /upload/jobs`** — returns all persisted `JobRecord`s so the frontend can sync on page load.

3. **`JobRecord` Pydantic model** — add to `backend/app/ingestion/models.py`:
   ```python
   class JobStatus(str, Enum):
       queued = "queued"
       extracting = "extracting"
       done = "done"
       failed = "failed"

   class JobRecord(BaseModel):
       job_id: str            # UUIDv4
       filename: str          # original name, UTF-8
       file_size_bytes: int
       status: JobStatus      # always 'queued' at creation
       target_metric: str
       submitted_at: str      # ISO 8601 UTC
   ```

4. **`JobRepository`** — new `backend/app/ingestion/repository.py`:
   - `save_job(filename, content, target_metric) → JobRecord`
   - `list_jobs() → list[JobRecord]`
   - Storage: `data/uploads/<job_id>.pdf` + `data/jobs.json`

5. **Frontend wiring** in `App.tsx`:
   - `useEffect` on mount: `GET /upload/jobs` → populate a `persistedJobs: JobRecord[]` state.
   - `handleSubmit`: send `FormData` to `POST /upload/jobs` (include `files` + per-file `target_metric` list), update local state with response.
   - Add `JobRecord` TypeScript type in `frontend/src/types/job.ts`.

6. **`JobList.tsx`** update:
   - Render both `stagedFiles` (pending, not submitted) and `persistedJobs` (backend-confirmed, with status badge).

---

## RESOURCES: Conventions, Constraints & Reference Files

### Development Loop (7 Steps — Mandatory)
```
1. Explore   → Read spec, code, constitution. No writing.
2. Plan      → Short written plan. Wait for green light.
3. Implement → Only the current step. No extra improvements.
4. Verify    → Run it, confirm it works. State manual verification steps.
5. Review    → Security, error handling, type safety, CONSTITUTION compliance.
6. Test      → Unit + integration tests (decided at Plan time, not after).
7. Commit    → git add + git commit only when all gates pass.
```

### Run Commands
```powershell
# Frontend (from c:\footnote\frontend)
npm run dev       # Vite dev server, port 5173
npm test          # Vitest unit tests

# Backend (from c:\footnote\backend)
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
..\.venv\Scripts\python.exe -m pytest tests/ -v
..\.venv\Scripts\python.exe -m mypy app/ingestion/ app/main.py --ignore-missing-imports
..\.venv\Scripts\python.exe -m ruff check app/

# TypeScript (from c:\footnote\frontend)
npx tsc --noEmit
npx eslint src/
```

### Load-Bearing Documents (read before touching anything)
| Document | Where | Purpose |
|---|---|---|
| CONSTITUTION | `c:\footnote\docs\CONSTITUTION.md` | Hard rules. On conflict with plan, CONSTITUTION wins. |
| Plan | `c:\footnote\docs\plan.md` | Feature definitions, phased delivery, tech stack |
| Spec | `c:\footnote\docs\spec.md` | Feature 1 acceptance criteria and edge cases |

### Key CONSTITUTION Rules for Step 3
- **§1.1**: `mypy --strict` required on all `ingestion/` modules before commit.
- **§1.3**: No `dict`/`Any` crossing a pipeline-stage boundary — use Pydantic.
- **§1.9**: Do not swallow exceptions in `ingestion/` — surface them.
- **§2.2**: Module named after pipeline stage (`repository.py`, not `utils.py`).
- **§3.4**: Tests mirror source structure exactly (`tests/ingestion/test_repository.py`).
- **§6.10**: MVP is single-user/single-session — no auth, no multi-tenancy.

### CONSTITUTION §3.8 Isolation Rule (already established)
`ingestion/` must NOT import from `extraction/`, `classification/`, `formula_engine/`, `excel_export/`, or `audit_report/`. Only `main.py` may import from `ingestion/`.

### mypy.ini override (already in place at `c:\footnote\mypy.ini`)
```ini
[mypy-pymupdf]
ignore_missing_imports = True
disallow_untyped_calls = False

[mypy-app.ingestion.validation]
disallow_untyped_calls = False
```
If new modules call pymupdf, add them here — never use `# type: ignore` inline.

### test_validation.py pattern for size tests
```python
# Never allocate 100MB in tests. Patch the constant instead:
with patch("app.ingestion.validation.MAX_FILE_SIZE_BYTES", 100):
    result = validate_pdf_bytes("big.pdf", b"x" * 101)
```

### Spec Edge Cases to Handle in Step 3
| EC | Behaviour Required |
|---|---|
| EC-1 | Same filename submitted twice → two separate `JobRecord`s (dedup by `job_id`, not filename) |
| EC-8 | Non-ASCII filenames stored as-is (UTF-8). File on disk uses `job_id` as key, never filename. |
| AC-9 | Disk write failure → visible error surfaced. No half-created job records. |

### `target_metric` field on the `POST /upload/jobs` request
The frontend sends one `target_metric` string per file. Since multipart forms cannot attach metadata to individual file parts directly, the recommended approach is a parallel list field:
```
files[0] = <binary>    target_metrics[0] = "Adjusted EBITDA"
files[1] = <binary>    target_metrics[1] = "EBITDA"
```
Zip them by index in the router. Validate that `len(files) == len(target_metrics)`.

### What NOT to do in Step 3
- Do **not** implement extraction pipeline triggering (Step 5).
- Do **not** implement job status polling or WebSocket updates.
- Do **not** implement retry logic for failed jobs.
- Do **not** change `validate_pdf_bytes` — it is complete and tested.
- Do **not** change `POST /upload/validate` — it stays as a standalone validation-only endpoint.
  `POST /upload/jobs` is a **new** endpoint that adds persistence on top.
