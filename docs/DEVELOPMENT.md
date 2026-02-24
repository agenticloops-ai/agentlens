# Developing

## How It Works

AgentLens sits between your AI agent and the LLM provider. It intercepts every HTTP request via a local [mitmproxy](https://mitmproxy.org/) instance, parses the provider-specific payloads into a generic data model, stores everything in SQLite, and streams results to a React dashboard over WebSocket.

```
  AI Agent (HTTP_PROXY=localhost:8080)
         │
  ┌──────▼───────────────────────┐
  │  CAPTURE (mitmproxy addon)   │  ← provider-agnostic interception
  └──────┬───────────────────────┘
         │ RawCapture (full HTTP req/res)
  ┌──────▼───────────────────────┐
  │  PROVIDERS (OpenAI, Anthropic)│ ← provider-specific → generic model
  └──────┬───────────────────────┘
         │ LLMRequest (unified format)
  ┌──────▼───────────────────────┐
  │  STORAGE (SQLite via async   │
  │          SQLAlchemy)         │
  │  API    (FastAPI + WebSocket)│
  │  UI     (React + Vite)       │
  └──────────────────────────────┘
```

## Features

- **Transparent proxy** — zero code changes in your agent; just set `HTTP_PROXY`
- **OpenAI + Anthropic** — chat completions, responses API, messages API, streaming (SSE reassembly)
- **Tool call tracing** — tool definitions, tool_use/tool_result blocks with visual flow
- **MCP detection** — automatically identifies MCP-originated tools (`mcp__server__method` pattern)
- **Extended thinking** — Anthropic chain-of-thought blocks rendered in the UI
- **Token usage + cost estimation** — per-request and per-session cost tracking with model-specific pricing
- **Real-time dashboard** — WebSocket-powered live updates as requests flow through
- **Session management** — group profiling runs, compare sessions, view aggregate stats
- **Raw capture** — full HTTP request/response preserved; toggle between parsed and raw views

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Proxy | mitmproxy >= 11.0 |
| Models | Pydantic v2 |
| Storage | SQLite + SQLAlchemy (async) + aiosqlite |
| API | FastAPI + uvicorn |
| CLI | Typer + Rich |
| Frontend | React 19 + Vite + TypeScript + Tailwind CSS |
| Charts | Recharts |
| State | React Query (server) + Zustand (WebSocket) |

## Project Structure

```
agentlens/
├── pyproject.toml                     # Python package config
├── package.json                       # npm workspace root
├── Makefile                           # dev commands
├── scripts/
│   └── generate-types.py             # Pydantic → JSON Schema → TypeScript
├── src/agentlens/
│   ├── cli.py                        # Typer CLI (start, replay, export)
│   ├── models/
│   │   ├── enums.py                  # MessageRole, ContentBlockType, StopReason
│   │   ├── base.py                   # LLMRequest, Message, ContentBlock variants, Session
│   │   └── raw.py                    # RawCapture
│   ├── providers/                    # Plugin-based provider system
│   │   ├── __init__.py               # Auto-discovery + PluginRegistry
│   │   ├── _base.py                  # ProviderPlugin ABC, ProviderMeta, EndpointPattern
│   │   ├── openai/
│   │   │   ├── __init__.py
│   │   │   ├── plugin.py             # OpenAI Responses API plugin
│   │   │   ├── completions.py        # Chat Completions API plugin
│   │   │   └── pricing.py            # OpenAI model pricing
│   │   └── anthropic/
│   │       ├── __init__.py
│   │       ├── plugin.py             # Anthropic Messages API plugin
│   │       └── pricing.py            # Anthropic model pricing
│   ├── proxy/
│   │   ├── addon.py                  # mitmproxy addon (capture + parse + store)
│   │   └── runner.py                 # Programmatic mitmproxy DumpMaster launcher
│   ├── storage/
│   │   ├── database.py               # SQLite schema + async engine
│   │   └── repositories.py           # CRUD + aggregation queries
│   └── server/
│       ├── app.py                    # FastAPI app factory
│       ├── event_bus.py              # In-process async pub/sub
│       ├── dependencies.py           # FastAPI dependency injection
│       └── routes/
│           ├── sessions.py           # Session CRUD endpoints
│           ├── requests.py           # Request listing + detail endpoints
│           ├── providers.py          # Provider metadata endpoint
│           └── events.py             # WebSocket /api/ws/live
├── web/
│   └── src/
│       ├── App.tsx                   # Router setup
│       ├── api/                      # REST client + React Query hooks
│       ├── stores/liveStore.ts       # Zustand WebSocket store
│       ├── types/                    # TypeScript types (generated + manual)
│       ├── pages/
│       │   ├── DashboardPage.tsx     # Session card grid
│       │   ├── SessionDetailPage.tsx # Timeline + stats
│       │   └── RequestDetailPage.tsx # Full conversation view
│       └── components/
│           ├── layout/               # Layout, Sidebar, Header
│           ├── session/              # SessionList, SessionCard
│           ├── request/              # RequestTimeline, RequestSummaryRow
│           ├── conversation/         # ConversationThread, MessageBubble
│           ├── tools/                # ToolCallBlock, ToolResultBlock
│           ├── thinking/             # ThinkingBlock
│           ├── stats/                # TokenUsageChart, LatencyChart, CostSummary
│           └── common/              # JsonViewer, CodeBlock, Badge, CopyButton
└── tests/
    ├── fixtures/                     # Recorded API request/response pairs
    │   ├── openai/                   # chat_completion, streaming, tools
    │   └── anthropic/                # messages, streaming, tool_use, thinking, mcp
    ├── test_storage/                 # Repository + DB tests
    ├── test_parsers/                 # Provider plugin tests
    ├── test_proxy/                   # Provider detection + SSE splitting
    ├── test_server/                  # REST route + WebSocket tests
    └── test_integration/             # End-to-end tests
```

## Provider Plugin Architecture

Each provider is a self-contained plugin under `providers/`. Adding a new provider requires zero changes to common code — just drop a new subpackage into `providers/` and it's auto-discovered at startup.

### The Plugin Interface

```python
class ProviderPlugin(ABC):
    meta: ProviderMeta         # name, display_name, color
    endpoints: list[EndpointPattern]  # host + path patterns for detection
    pricing: dict              # model pricing table

    def can_parse(raw: RawCapture) -> bool     # default: match URL against endpoints
    def parse(raw, duration_ms, ttft_ms) -> LLMRequest
    def estimate_cost(model, usage) -> float | None
```

### Adding a new provider

```
1. Create providers/google/__init__.py
2. Create providers/google/plugin.py:

   class GooglePlugin(ProviderPlugin):
       meta = ProviderMeta(name="google", display_name="Google", color="#4285f4")
       endpoints = [EndpointPattern("generativelanguage.googleapis.com", "/v1beta/models")]
       pricing = {...}
       def parse(self, raw, ...): ...

3. Create providers/google/pricing.py (optional, can inline)
4. Done — auto-discovered at startup
```

No enums to extend. No registry to edit. No detection tables to update.

## Data Model

The core data model normalizes provider-specific formats into a generic representation.

### LLMRequest (central unit)

Each intercepted API call becomes one `LLMRequest`:

| Field | Description |
|-------|-----------|
| `id` | UUID |
| `session_id` | Parent profiling session |
| `timestamp` | When the request was made |
| `duration_ms` | Total round-trip time |
| `time_to_first_token_ms` | TTFT for streaming requests |
| `provider` | `openai`, `anthropic`, or `unknown` |
| `model` | Model name (e.g., `gpt-4o`, `claude-sonnet-4`) |
| `is_streaming` | Whether SSE streaming was used |
| `system_prompt` | Extracted system prompt |
| `messages` | Input message list |
| `tools` | Tool definitions (with MCP metadata) |
| `response_messages` | Output message list |
| `stop_reason` | `end_turn`, `max_tokens`, `tool_use`, etc. |
| `usage` | Token counts + estimated cost |

### Content Blocks (discriminated union)

Messages contain typed content blocks:

- **TextContent** — plain text or markdown
- **ImageContent** — image metadata (raw data stays in RawCapture)
- **ThinkingContent** — Anthropic extended thinking / chain-of-thought
- **ToolUseContent** — tool call with `tool_call_id`, `tool_name`, `tool_input`
- **ToolResultContent** — tool response with `tool_call_id`, `content`, `is_error`

### ToolDefinition

```
name, description, input_schema (JSON Schema)
is_mcp: bool          # Detected as MCP-originated
mcp_server_name: str  # Extracted from mcp__<server>__<method> pattern
```

### Provider Mapping

| Concept | OpenAI | Anthropic | Generic |
|---------|--------|-----------|---------|
| System prompt | `messages[role="system"]` | top-level `system` | `LLMRequest.system_prompt` |
| Tool calls | `assistant.tool_calls[]` | `content type="tool_use"` | `ToolUseContent` |
| Tool results | `message role="tool"` | `content type="tool_result"` | `ToolResultContent` |
| Thinking | N/A | `content type="thinking"` | `ThinkingContent` |
| Streaming | SSE `delta.content` | SSE `content_block_delta` | Reassembled into `Message` |

## Database

### Schema

SQLite with three tables. Uses SQLAlchemy Core (no ORM). Complex fields (messages, tools, headers, SSE events) are stored as JSON-serialized `Text` columns. Booleans are `Integer` (0/1), datetimes are ISO 8601 strings.

```
sessions
├── id              TEXT PRIMARY KEY
├── name            TEXT
├── started_at      TEXT (ISO 8601)
├── ended_at        TEXT (ISO 8601, nullable)
├── request_count   INTEGER
├── total_tokens    INTEGER
└── estimated_cost_usd  REAL

raw_captures
├── id              TEXT PRIMARY KEY
├── session_id      TEXT → sessions.id
├── timestamp       TEXT (ISO 8601)
├── provider        TEXT
├── request_url     TEXT
├── request_method  TEXT
├── request_headers TEXT (JSON)
├── request_body    TEXT (JSON)
├── response_status INTEGER
├── response_headers TEXT (JSON)
├── response_body   TEXT (JSON)
├── is_streaming    INTEGER (0/1)
└── sse_events      TEXT (JSON array)

llm_requests
├── id              TEXT PRIMARY KEY
├── session_id      TEXT → sessions.id
├── raw_capture_id  TEXT → raw_captures.id
├── timestamp       TEXT (ISO 8601)
├── duration_ms     REAL (nullable)
├── time_to_first_token_ms  REAL (nullable)
├── provider        TEXT
├── model           TEXT
├── api_endpoint    TEXT
├── temperature     REAL (nullable)
├── max_tokens      INTEGER (nullable)
├── top_p           REAL (nullable)
├── is_streaming    INTEGER (0/1)
├── tool_choice     TEXT (JSON, nullable)
├── system_prompt   TEXT (nullable)
├── messages        TEXT (JSON array)
├── tools           TEXT (JSON array)
├── response_messages TEXT (JSON array)
├── stop_reason     TEXT (nullable)
├── usage           TEXT (JSON object)
├── status          TEXT
├── request_params  TEXT (JSON object)
└── response_metadata TEXT (JSON object)
```

### Location

Default path: `~/.agentlens/data.db` (configurable via `--db-path`).

### Connecting

```bash
# Open with sqlite3
sqlite3 ~/.agentlens/data.db

# List sessions
SELECT id, name, started_at, request_count, total_tokens FROM sessions ORDER BY started_at DESC;

# List requests for a session
SELECT id, provider, model, duration_ms, is_streaming, status
FROM llm_requests WHERE session_id = '<session-id>' ORDER BY timestamp;

# View token usage as JSON
SELECT id, model, json_extract(usage, '$.input_tokens') AS input_tokens,
       json_extract(usage, '$.output_tokens') AS output_tokens,
       json_extract(usage, '$.estimated_cost_usd') AS cost
FROM llm_requests WHERE session_id = '<session-id>';

# View system prompt for a request
SELECT system_prompt FROM llm_requests WHERE id = '<request-id>';

# Count requests by model across all sessions
SELECT model, COUNT(*) AS count, SUM(json_extract(usage, '$.total_tokens')) AS tokens
FROM llm_requests GROUP BY model ORDER BY count DESC;
```

### Serialization

Repositories (`storage/repositories.py`) handle the Pydantic ↔ SQLite mapping:
- **Write**: `model.model_dump()` → `json.dumps()` for complex fields → SQL INSERT
- **Read**: SQL SELECT → `json.loads()` for JSON columns → Pydantic model construction

## API Endpoints

### Sessions

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/sessions` | List all sessions |
| `GET` | `/api/sessions/:id` | Session detail with aggregate stats |
| `DELETE` | `/api/sessions/:id` | Delete a session |

### Requests

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/sessions/:id/requests` | List requests (supports `provider`, `model`, `has_tools` filters + pagination) |
| `GET` | `/api/requests/:id` | Full LLMRequest detail |
| `GET` | `/api/requests/:id/raw` | Raw HTTP capture |

### WebSocket

| Path | Description |
|------|-------------|
| `/api/ws/live` | Real-time events: `new_request`, `session_updated` |

## Cost Estimation

Pricing tables are built into each provider plugin with per-model rates (per 1M tokens). The Anthropic plugin includes cache token pricing (cache write and cache read rates). Model matching uses prefix lookup, so `gpt-4o-2024-08-06` matches the `gpt-4o` pricing tier.

**Supported models include:**

- OpenAI: gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-4, gpt-3.5-turbo, o1, o1-mini, o3, o3-mini, o4-mini
- Anthropic: claude-sonnet-4, claude-haiku-4, claude-3.5-sonnet, claude-3.5-haiku, claude-3-opus

## Proxy Flow

1. **`requestheaders`** — detect provider via hostname/path using `PluginRegistry`, record start timestamp, skip non-LLM traffic
2. **`responseheaders`** — always stream captured flows through to the client while accumulating chunks (prevents timeouts for SSE endpoints that don't advertise `text/event-stream`), record TTFT for known streaming requests
3. **`response`** — read accumulated buffer, detect SSE from content heuristic if headers missed it, build `RawCapture`, split SSE events if streaming, run provider plugin parser, store parsed `LLMRequest`, publish event to WebSocket bus
4. **`error`** — clean up timing state on connection failures

Non-LLM traffic passes through the proxy transparently without capture.

## Makefile Commands

```bash
make install          # Install Python + npm dependencies
make dev              # Start proxy + web UI
make proxy            # Start proxy only (no browser)
make web              # Start Vite dev server only
make generate-types   # Regenerate TypeScript types from Pydantic models
make test             # Run pytest
make lint             # Run ruff + eslint
```

## Running Tests

```bash
# All tests
pytest -v

# By area
pytest tests/test_storage/ -v
pytest tests/test_parsers/ -v
pytest tests/test_proxy/ -v
pytest tests/test_server/ -v
pytest tests/test_integration/ -v
```

## Type Generation

TypeScript types are generated from Pydantic models via JSON Schema:

```bash
python scripts/generate-types.py
# or
make generate-types
```

This produces `web/src/types/generated.ts` containing TypeScript interfaces matching all Pydantic models.
