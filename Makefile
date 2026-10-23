.PHONY: install test lint typecheck format check gold-verify score score-gate bridge-gate ingest serve export

install:
	pip install -r requirements-dev.txt

test:
	cd backend && pytest

lint:
	ruff check backend
	ruff format --check backend

typecheck:
	mypy

format:
	ruff check backend --fix
	ruff format backend

gold-verify:
	cd backend && python -m tools.gold.fetch_releases --verify
	cd backend && python -m tools.gold.labels --validate --strict

score:
	cd backend && python -m tools.eval.score

score-gate:
	cd backend && python -m tools.eval.score --check ../eval/thresholds.yaml

bridge-gate:
	cd backend && python -m tools.eval.score_bridge --check ../eval/thresholds-bridge.yaml

ingest:
	cd backend && python -m app.pipeline.cli ingest --quarters 8

export:
	cd backend && python -m app.pipeline.cli export

serve:
	cd backend && uvicorn app.api.main:app --port 8000

check: lint typecheck test gold-verify score-gate bridge-gate
