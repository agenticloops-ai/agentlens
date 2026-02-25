"""Async repository classes for sessions, LLM requests, and raw captures."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from agentlens.models.base import (
    LLMRequest,
    Message,
    Session,
    SessionStats,
    TokenUsage,
    ToolDefinition,
)
from agentlens.models.enums import RequestStatus, StopReason
from agentlens.models.raw import RawCapture

from .database import llm_requests_table, raw_captures_table, sessions_table


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dt_to_str(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _str_to_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _json_dumps(obj: Any) -> str:
    """Serialize *obj* to a JSON string, handling Pydantic models."""
    if obj is None:
        return "null"
    if isinstance(obj, list):
        return json.dumps([_prepare(item) for item in obj])
    if hasattr(obj, "model_dump"):
        return json.dumps(obj.model_dump(mode="json"))
    return json.dumps(obj)


def _prepare(item: Any) -> Any:
    """Recursively convert Pydantic models to plain dicts for JSON encoding."""
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    return item


def _deserialize_system_prompt(value: str | None) -> list[str] | str | None:
    """Deserialize system_prompt from DB: JSON list or plain string."""
    if value is None:
        return None
    if value.startswith("["):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
    return value


# ---------------------------------------------------------------------------
# SessionRepository
# ---------------------------------------------------------------------------


class SessionRepository:
    """CRUD operations for the ``sessions`` table."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    # -- helpers --

    @staticmethod
    def _row_to_model(row: Any) -> Session:
        mapping = row._mapping
        return Session(
            id=mapping["id"],
            name=mapping["name"],
            started_at=_str_to_dt(mapping["started_at"]),  # type: ignore[arg-type]
            ended_at=_str_to_dt(mapping["ended_at"]),
            request_count=mapping["request_count"],
            total_tokens=mapping["total_tokens"],
            estimated_cost_usd=mapping["estimated_cost_usd"],
        )

    @staticmethod
    def _model_to_values(session: Session) -> dict[str, Any]:
        return {
            "id": session.id,
            "name": session.name,
            "started_at": _dt_to_str(session.started_at),
            "ended_at": _dt_to_str(session.ended_at),
            "request_count": session.request_count,
            "total_tokens": session.total_tokens,
            "estimated_cost_usd": session.estimated_cost_usd,
        }

    # -- public API --

    async def create(self, session: Session) -> Session:
        values = self._model_to_values(session)
        async with self.engine.begin() as conn:
            await conn.execute(insert(sessions_table).values(**values))
        return session

    async def get(self, session_id: str) -> Session | None:
        async with self.engine.connect() as conn:
            row = (await conn.execute(select(sessions_table).where(sessions_table.c.id == session_id))).first()
        if row is None:
            return None
        return self._row_to_model(row)

    async def list_all(self) -> list[Session]:
        t = sessions_table
        r = llm_requests_table
        # Compute actual request counts from the llm_requests table
        count_subq = (
            select(
                r.c.session_id,
                func.count(r.c.id).label("computed_count"),
            )
            .group_by(r.c.session_id)
            .subquery()
        )
        async with self.engine.connect() as conn:
            rows = (await conn.execute(select(t).order_by(t.c.started_at.desc()))).fetchall()
            count_rows = (await conn.execute(select(count_subq))).fetchall()
        count_map = {cr._mapping["session_id"]: cr._mapping["computed_count"] for cr in count_rows}
        sessions = []
        for row in rows:
            s = self._row_to_model(row)
            s.request_count = count_map.get(s.id, 0)
            sessions.append(s)
        return sessions

    async def update(self, session: Session) -> Session:
        values = self._model_to_values(session)
        session_id = values.pop("id")
        async with self.engine.begin() as conn:
            await conn.execute(update(sessions_table).where(sessions_table.c.id == session_id).values(**values))
        return session

    async def delete(self, session_id: str) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(delete(raw_captures_table).where(raw_captures_table.c.session_id == session_id))
            await conn.execute(delete(llm_requests_table).where(llm_requests_table.c.session_id == session_id))
            await conn.execute(delete(sessions_table).where(sessions_table.c.id == session_id))

    async def end_all_active(self) -> None:
        """Set ``ended_at`` on every session that is still active (``ended_at IS NULL``)."""
        t = sessions_table
        async with self.engine.begin() as conn:
            await conn.execute(
                update(t)
                .where(t.c.ended_at.is_(None))
                .values(ended_at=_dt_to_str(datetime.utcnow()))
            )

    async def increment_stats(
        self,
        session_id: str,
        request_count: int = 0,
        total_tokens: int = 0,
        estimated_cost_usd: float = 0.0,
    ) -> None:
        """Atomically increment session counters using SQL expressions."""
        t = sessions_table
        async with self.engine.begin() as conn:
            await conn.execute(
                update(t)
                .where(t.c.id == session_id)
                .values(
                    request_count=t.c.request_count + request_count,
                    total_tokens=t.c.total_tokens + total_tokens,
                    estimated_cost_usd=t.c.estimated_cost_usd + estimated_cost_usd,
                )
            )

    async def get_stats(self, session_id: str) -> SessionStats:
        t = llm_requests_table
        async with self.engine.connect() as conn:
            # Aggregate numeric stats in a single query.
            agg = (
                await conn.execute(
                    select(
                        func.count(t.c.id).label("total_requests"),
                        func.avg(t.c.duration_ms).label("avg_duration_ms"),
                    ).where(t.c.session_id == session_id)
                )
            ).first()

            # Fetch all usage blobs so we can sum token counts.
            usage_rows = (await conn.execute(select(t.c.usage).where(t.c.session_id == session_id))).fetchall()

            # Distinct models / providers.
            model_rows = (
                await conn.execute(select(func.distinct(t.c.model)).where(t.c.session_id == session_id))
            ).fetchall()
            provider_rows = (
                await conn.execute(select(func.distinct(t.c.provider)).where(t.c.session_id == session_id))
            ).fetchall()

        total_requests = agg._mapping["total_requests"] if agg else 0  # type: ignore[union-attr]
        avg_duration = agg._mapping["avg_duration_ms"] if agg else None  # type: ignore[union-attr]

        total_input = 0
        total_output = 0
        total_tokens = 0
        total_cost = 0.0
        for row in usage_rows:
            usage_data = json.loads(row._mapping["usage"])
            total_input += usage_data.get("input_tokens", 0)
            total_output += usage_data.get("output_tokens", 0)
            total_tokens += usage_data.get("total_tokens", 0)
            total_cost += usage_data.get("estimated_cost_usd", 0) or 0

        avg_tokens = total_tokens / total_requests if total_requests else None

        return SessionStats(
            total_requests=total_requests,
            total_tokens=total_tokens,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            estimated_cost_usd=total_cost,
            avg_duration_ms=avg_duration,
            avg_tokens_per_request=avg_tokens,
            models_used=[r[0] for r in model_rows],
            providers_used=[r[0] for r in provider_rows],
        )


# ---------------------------------------------------------------------------
# RequestRepository
# ---------------------------------------------------------------------------


class RequestRepository:
    """CRUD + filtering for the ``llm_requests`` table."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    # -- helpers --

    @staticmethod
    def _row_to_model(row: Any) -> LLMRequest:
        m = row._mapping
        messages_raw = json.loads(m["messages"])
        tools_raw = json.loads(m["tools"])
        response_messages_raw = json.loads(m["response_messages"])
        usage_raw = json.loads(m["usage"])
        tool_choice_raw = json.loads(m["tool_choice"]) if m["tool_choice"] else None

        return LLMRequest(
            id=m["id"],
            session_id=m["session_id"],
            raw_capture_id=m["raw_capture_id"],
            timestamp=_str_to_dt(m["timestamp"]),  # type: ignore[arg-type]
            duration_ms=m["duration_ms"],
            time_to_first_token_ms=m["time_to_first_token_ms"],
            provider=m["provider"],
            model=m["model"],
            api_endpoint=m["api_endpoint"],
            temperature=m["temperature"],
            max_tokens=m["max_tokens"],
            top_p=m["top_p"],
            is_streaming=bool(m["is_streaming"]),
            tool_choice=tool_choice_raw,
            system_prompt=_deserialize_system_prompt(m["system_prompt"]),
            messages=[Message.model_validate(msg) for msg in messages_raw],
            tools=[ToolDefinition.model_validate(t) for t in tools_raw],
            response_messages=[Message.model_validate(msg) for msg in response_messages_raw],
            stop_reason=StopReason(m["stop_reason"]) if m["stop_reason"] else None,
            usage=TokenUsage.model_validate(usage_raw),
            status=RequestStatus(m["status"]),
            request_params=json.loads(m["request_params"]),
            response_metadata=json.loads(m["response_metadata"]),
        )

    @staticmethod
    def _model_to_values(request: LLMRequest) -> dict[str, Any]:
        return {
            "id": request.id,
            "session_id": request.session_id,
            "raw_capture_id": request.raw_capture_id,
            "timestamp": _dt_to_str(request.timestamp),
            "duration_ms": request.duration_ms,
            "time_to_first_token_ms": request.time_to_first_token_ms,
            "provider": str(request.provider),
            "model": request.model,
            "api_endpoint": request.api_endpoint,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p,
            "is_streaming": int(request.is_streaming),
            "tool_choice": _json_dumps(request.tool_choice),
            "system_prompt": json.dumps(request.system_prompt)
            if isinstance(request.system_prompt, list)
            else request.system_prompt,
            "messages": _json_dumps(request.messages),
            "tools": _json_dumps(request.tools),
            "response_messages": _json_dumps(request.response_messages),
            "stop_reason": str(request.stop_reason) if request.stop_reason else None,
            "usage": _json_dumps(request.usage),
            "status": str(request.status),
            "request_params": json.dumps(request.request_params),
            "response_metadata": json.dumps(request.response_metadata),
        }

    # -- public API --

    async def create(self, request: LLMRequest) -> LLMRequest:
        values = self._model_to_values(request)
        async with self.engine.begin() as conn:
            await conn.execute(insert(llm_requests_table).values(**values))
        return request

    async def get(self, request_id: str) -> LLMRequest | None:
        async with self.engine.connect() as conn:
            row = (await conn.execute(select(llm_requests_table).where(llm_requests_table.c.id == request_id))).first()
        if row is None:
            return None
        return self._row_to_model(row)

    async def list_by_session(
        self,
        session_id: str,
        provider: str | None = None,
        model: str | None = None,
        has_tools: bool | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[LLMRequest]:
        t = llm_requests_table
        stmt = select(t).where(t.c.session_id == session_id)

        if provider is not None:
            stmt = stmt.where(t.c.provider == provider)
        if model is not None:
            stmt = stmt.where(t.c.model == model)
        if has_tools is True:
            stmt = stmt.where(t.c.tools != "[]")
        elif has_tools is False:
            stmt = stmt.where(t.c.tools == "[]")

        stmt = stmt.order_by(t.c.timestamp.asc()).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)

        async with self.engine.connect() as conn:
            rows = (await conn.execute(stmt)).fetchall()
        return [self._row_to_model(r) for r in rows]

    async def count_by_session(self, session_id: str) -> int:
        t = llm_requests_table
        async with self.engine.connect() as conn:
            result = (await conn.execute(select(func.count(t.c.id)).where(t.c.session_id == session_id))).scalar()
        return result or 0


# ---------------------------------------------------------------------------
# RawCaptureRepository
# ---------------------------------------------------------------------------


class RawCaptureRepository:
    """CRUD operations for the ``raw_captures`` table."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    # -- helpers --

    @staticmethod
    def _row_to_model(row: Any) -> RawCapture:
        m = row._mapping
        return RawCapture(
            id=m["id"],
            session_id=m["session_id"],
            timestamp=_str_to_dt(m["timestamp"]),  # type: ignore[arg-type]
            provider=m["provider"],
            request_url=m["request_url"],
            request_method=m["request_method"],
            request_headers=json.loads(m["request_headers"]),
            request_body=json.loads(m["request_body"]),
            response_status=m["response_status"],
            response_headers=json.loads(m["response_headers"]),
            response_body=json.loads(m["response_body"]),
            is_streaming=bool(m["is_streaming"]),
            sse_events=json.loads(m["sse_events"]),
        )

    @staticmethod
    def _model_to_values(capture: RawCapture) -> dict[str, Any]:
        return {
            "id": capture.id,
            "session_id": capture.session_id,
            "timestamp": _dt_to_str(capture.timestamp),
            "provider": str(capture.provider),
            "request_url": capture.request_url,
            "request_method": capture.request_method,
            "request_headers": json.dumps(capture.request_headers),
            "request_body": json.dumps(
                capture.request_body if isinstance(capture.request_body, dict) else capture.request_body
            ),
            "response_status": capture.response_status,
            "response_headers": json.dumps(capture.response_headers),
            "response_body": json.dumps(
                capture.response_body if isinstance(capture.response_body, dict) else capture.response_body
            ),
            "is_streaming": int(capture.is_streaming),
            "sse_events": json.dumps([e if isinstance(e, dict) else e for e in capture.sse_events]),
        }

    # -- public API --

    async def create(self, capture: RawCapture) -> RawCapture:
        values = self._model_to_values(capture)
        async with self.engine.begin() as conn:
            await conn.execute(insert(raw_captures_table).values(**values))
        return capture

    async def get(self, capture_id: str) -> RawCapture | None:
        async with self.engine.connect() as conn:
            row = (await conn.execute(select(raw_captures_table).where(raw_captures_table.c.id == capture_id))).first()
        if row is None:
            return None
        return self._row_to_model(row)
