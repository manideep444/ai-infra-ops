.PHONY: setup test lint check demo demo-fixture kind-up kind-down scan build observe

setup:
	uv sync --frozen
	@test -f .state/identities.json || uv run airp init-demo

test:
	uv run pytest -m 'not kind' --cov=airp --cov-report=term-missing

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

check: lint test

demo-fixture:
	AIRP_PROVIDER=mock AIRP_BACKEND=fixture uv run airp demo

demo: kind-up
	AIRP_PROVIDER=mock AIRP_BACKEND=kubernetes uv run airp demo

kind-up:
	bash scripts/kind-up.sh

kind-down:
	kind delete cluster --name airp

scan:
	uv run pip-audit --local --skip-editable

build:
	uv build

observe:
	docker compose -f observability/compose.yaml up -d