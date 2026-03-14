"""SQLite database schema and engine management using SQLAlchemy async."""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Float,
    Integer,
    MetaData,
    text,
    String,
    Table,
    Text,
)
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

metadata = MetaData()

sessions_table = Table(
    "sessions",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False, default=""),
    Column("started_at", String, nullable=False),
    Column("ended_at", String, nullable=True),
    Column("request_count", Integer, nullable=False, default=0),
    Column("total_tokens", Integer, nullable=False, default=0),
    Column("estimated_cost_usd", Float, nullable=False, default=0.0),
)

raw_captures_table = Table(
    "raw_captures",
    metadata,
    Column("id", String, primary_key=True),
    Column("session_id", String, nullable=False),
    Column("timestamp", String, nullable=False),
    Column("capture_mode", String, nullable=False, default="explicit_proxy"),
    Column("capture_label", String, nullable=True),
    Column("capture_metadata", Text, nullable=False, default="{}"),
    Column("provider", String, nullable=False, default="unknown"),
    Column("request_url", String, nullable=False, default=""),
    Column("request_method", String, nullable=False, default="POST"),
    Column("request_headers", Text, nullable=False, default="{}"),
    Column("request_body", Text, nullable=False, default="{}"),
    Column("response_status", Integer, nullable=False, default=0),
    Column("response_headers", Text, nullable=False, default="{}"),
    Column("response_body", Text, nullable=False, default="{}"),
    Column("is_streaming", Integer, nullable=False, default=0),
    Column("sse_events", Text, nullable=False, default="[]"),
)

llm_requests_table = Table(
    "llm_requests",
    metadata,
    Column("id", String, primary_key=True),
    Column("session_id", String, nullable=False),
    Column("raw_capture_id", String, nullable=False, default=""),
    Column("capture_mode", String, nullable=False, default="explicit_proxy"),
    Column("capture_label", String, nullable=True),
    Column("capture_metadata", Text, nullable=False, default="{}"),
    Column("timestamp", String, nullable=False),
    Column("duration_ms", Float, nullable=True),
    Column("time_to_first_token_ms", Float, nullable=True),
    Column("provider", String, nullable=False, default="unknown"),
    Column("model", String, nullable=False, default=""),
    Column("api_endpoint", String, nullable=False, default=""),
    Column("temperature", Float, nullable=True),
    Column("max_tokens", Integer, nullable=True),
    Column("top_p", Float, nullable=True),
    Column("is_streaming", Integer, nullable=False, default=0),
    Column("tool_choice", Text, nullable=True),
    Column("system_prompt", Text, nullable=True),
    Column("messages", Text, nullable=False, default="[]"),
    Column("tools", Text, nullable=False, default="[]"),
    Column("response_messages", Text, nullable=False, default="[]"),
    Column("stop_reason", String, nullable=True),
    Column("usage", Text, nullable=False, default="{}"),
    Column("status", String, nullable=False, default="success"),
    Column("request_params", Text, nullable=False, default="{}"),
    Column("response_metadata", Text, nullable=False, default="{}"),
)

# Cache engines by db_path to allow reuse.
_engines: dict[str, AsyncEngine] = {}


_COLUMN_MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    "raw_captures": [
        ("capture_mode", "TEXT NOT NULL DEFAULT 'explicit_proxy'"),
        ("capture_label", "TEXT"),
        ("capture_metadata", "TEXT NOT NULL DEFAULT '{}'"),
    ],
    "llm_requests": [
        ("capture_mode", "TEXT NOT NULL DEFAULT 'explicit_proxy'"),
        ("capture_label", "TEXT"),
        ("capture_metadata", "TEXT NOT NULL DEFAULT '{}'"),
    ],
}


async def _apply_additive_migrations(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        for table_name, columns in _COLUMN_MIGRATIONS.items():
            rows = await conn.execute(text(f"PRAGMA table_info({table_name})"))
            existing = {row[1] for row in rows.fetchall()}
            for column_name, definition in columns:
                if column_name in existing:
                    continue
                await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))


async def init_db(db_path: str) -> AsyncEngine:
    """Create an async engine, create all tables, and return the engine.

    Parameters
    ----------
    db_path:
        Filesystem path for the SQLite database.
        Pass an empty string to use an in-memory database.
    """
    if db_path:
        url = f"sqlite+aiosqlite:///{db_path}"
    else:
        url = "sqlite+aiosqlite://"

    engine = create_async_engine(url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    await _apply_additive_migrations(engine)

    _engines[db_path] = engine
    return engine


async def get_engine(db_path: str) -> AsyncEngine:
    """Return a cached engine for *db_path*, creating it if needed."""
    if db_path not in _engines:
        return await init_db(db_path)
    return _engines[db_path]
