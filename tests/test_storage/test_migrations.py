from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agentlens.storage.database import init_db


@pytest.mark.asyncio
async def test_init_db_adds_capture_columns_to_existing_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "agentlens.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL,
                ended_at TEXT,
                request_count INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                estimated_cost_usd FLOAT NOT NULL DEFAULT 0.0
            );
            CREATE TABLE raw_captures (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'unknown',
                request_url TEXT NOT NULL DEFAULT '',
                request_method TEXT NOT NULL DEFAULT 'POST',
                request_headers TEXT NOT NULL DEFAULT '{}',
                request_body TEXT NOT NULL DEFAULT '{}',
                response_status INTEGER NOT NULL DEFAULT 0,
                response_headers TEXT NOT NULL DEFAULT '{}',
                response_body TEXT NOT NULL DEFAULT '{}',
                is_streaming INTEGER NOT NULL DEFAULT 0,
                sse_events TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE llm_requests (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                raw_capture_id TEXT NOT NULL DEFAULT '',
                timestamp TEXT NOT NULL,
                duration_ms FLOAT,
                time_to_first_token_ms FLOAT,
                provider TEXT NOT NULL DEFAULT 'unknown',
                model TEXT NOT NULL DEFAULT '',
                api_endpoint TEXT NOT NULL DEFAULT '',
                temperature FLOAT,
                max_tokens INTEGER,
                top_p FLOAT,
                is_streaming INTEGER NOT NULL DEFAULT 0,
                tool_choice TEXT,
                system_prompt TEXT,
                messages TEXT NOT NULL DEFAULT '[]',
                tools TEXT NOT NULL DEFAULT '[]',
                response_messages TEXT NOT NULL DEFAULT '[]',
                stop_reason TEXT,
                usage TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'success',
                request_params TEXT NOT NULL DEFAULT '{}',
                response_metadata TEXT NOT NULL DEFAULT '{}'
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

    engine = await init_db(str(db_path))
    await engine.dispose()

    check = sqlite3.connect(db_path)
    try:
        raw_columns = {row[1] for row in check.execute("PRAGMA table_info(raw_captures)")}
        req_columns = {row[1] for row in check.execute("PRAGMA table_info(llm_requests)")}
    finally:
        check.close()

    assert {"capture_mode", "capture_label", "capture_metadata"} <= raw_columns
    assert {"capture_mode", "capture_label", "capture_metadata"} <= req_columns
