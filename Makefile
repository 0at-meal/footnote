.PHONY: install test lint typecheck format check gold-verify score score-gate

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

check: lint typecheck test gold-verify score-gate
