.PHONY: eval test lint build

eval:
	python -m eval.run_benchmark --split dev --replay

test:
	pytest backend/tests
	npm --prefix frontend test

lint:
	ruff check backend
	mypy backend/app
	npm --prefix frontend run lint

build:
	npm --prefix frontend run build
