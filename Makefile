.PHONY: dev proxy web build generate-types test lint install ci publish review

install:
	mkdir -p web/dist
	uv sync --extra dev
	cd web && npm install
	$(MAKE) build
	ln -sfn $$(pwd)/web/dist src/agentlens/static

ci:
	mkdir -p web/dist
	uv sync --extra dev
	cd web && npm ci

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

publish:
	@test -n "$$UV_PUBLISH_TOKEN" || { echo "Set UV_PUBLISH_TOKEN with a PyPI API token first"; exit 1; }
	cd web && npm install && npm run build
	uv build
	uv publish

review:
	@BASE=$${BASE:-main}; \
	DIFF=$$(git diff $$BASE...HEAD); \
	if [ -z "$$DIFF" ]; then echo "No changes vs $$BASE"; exit 1; fi; \
	echo "$$DIFF" | claude -p \
		"Review this diff against $$BASE. Focus on bugs, security issues, and code quality. Be concise — only flag things worth changing."
