.PHONY: dev proxy web build generate-types test lint install

install:
	uv sync --extra dev
	cd web && npm install
	$(MAKE) build

dev:
	@echo "Starting proxy and web server..."
	uv run agentlens start

proxy:
	uv run agentlens start --no-open

web:
	cd web && npm run dev

build:
	cd web && npm run build

generate-types:
	uv run python scripts/generate-types.py

test:
	uv run pytest -v

lint:
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/
	cd web && npm run lint
