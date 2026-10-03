.PHONY: eval test lint build run-backend run-frontend check-backend

# Always use the project virtualenv (D1 / AUD-003): a system Python without Docling
# silently degrades extraction.
ifeq ($(OS),Windows_NT)
PY := .venv/Scripts/python.exe
else
PY := .venv/bin/python
endif

run-backend:
	$(PY) tools/run_backend.py

check-backend:
	$(PY) tools/run_backend.py --check

run-frontend:
	npm --prefix frontend run dev

eval:
	$(PY) -m eval.run_benchmark --split dev --replay

test:
	cd backend && ../$(PY) -m pytest
	npm --prefix frontend test

lint:
	$(PY) -m ruff check backend
	$(PY) -m mypy backend/app
	npm --prefix frontend run lint

build:
	npm --prefix frontend run build
