.PHONY: install test lint typecheck format check

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

check: lint typecheck test
