# AgentLens

LLM API traffic profiler — Python MITM proxy + React web UI.

## Commands

Always use `uv run` to run Python — never bare `python` or `pytest`.

```bash
make install          # uv sync --extra dev, npm install, build frontend, symlink static
make dev              # uv run agentlens start (proxy :8080 + web UI :8081)
make proxy            # uv run agentlens start --no-open
make web              # cd web && npm run dev (vite dev server)
make build            # cd web && npm run build
make generate-types   # uv run python scripts/generate-types.py
make test             # uv run pytest -v
make lint             # uv run ruff check + format --check, npm run lint
make publish          # build frontend + uv build + uv publish
make review           # claude reviews current branch diff vs main (BASE=branch to override)
```

## Project Structure

```
src/agentlens/
  cli.py              # Typer CLI entry point
  models/             # Pydantic models (LLMRequest, Session, enums)
  providers/          # Auto-discovered provider plugins (anthropic/, openai/)
    _base.py          # Abstract ProviderPlugin + PluginRegistry
  proxy/              # mitmproxy addon + async runner
  server/             # FastAPI app, routes/, event_bus
  storage/            # SQLAlchemy async + repositories (CRUD)
web/                  # React 19 + Vite + TypeScript + Tailwind
tests/                # pytest + fixtures/ (JSON API responses)
```

## Architecture

Data flow: HTTP traffic → mitmproxy addon → PluginRegistry dispatches to provider → parsed into LLMRequest → stored in SQLite → served via FastAPI → WebSocket pushes to React UI.

Provider plugins are auto-discovered from `providers/` subdirs. Each declares `endpoints` (host + path patterns) and implements `parse(RawCapture) → LLMRequest`.

Database uses SQLAlchemy Core (not ORM) with async aiosqlite. Datetimes stored as ISO strings.

## Code Style

### Python
- `from __future__ import annotations` at top of every module
- Type hints on all public functions
- Line length: 120 (ruff)
- Private helpers prefixed with `_`
- Async-first: `async def` routes, `async with engine.begin()` for transactions
- Early returns over deep nesting
- Catch specific exceptions, not bare `except`

### TypeScript/React
- Functional components with hooks only
- TanStack Query for server state, Zustand for client state
- Tailwind utility classes for styling
- Props interfaces suffixed with `Props`

## Testing

- pytest with pytest-asyncio (auto mode)
- Fixtures in `tests/fixtures/` loaded via `load_fixture("provider", "endpoint")`
- Server tests use `httpx.AsyncClient` with `ASGITransport`
- Database tests use in-memory SQLite
- Arrange-Act-Assert pattern, test classes group related cases

## Dependencies

- Python ≥3.11, Node ≥18
- Backend: FastAPI, mitmproxy, SQLAlchemy[asyncio], aiosqlite, Pydantic 2, Typer, Rich
- Frontend: React 19, Vite 6, Tailwind 4, React Router 7, TanStack Query 5, Zustand 5, Recharts
