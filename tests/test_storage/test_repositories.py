"""Tests for the storage repositories using an in-memory SQLite database."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from agentlens.models.base import (
    LLMRequest,
    Message,
    Session,
    TextContent,
    TokenUsage,
    ToolDefinition,
    ToolUseContent,
)
from agentlens.models.enums import (
    MessageRole,
    RequestStatus,
    StopReason,
)
from agentlens.models.raw import RawCapture
from agentlens.storage.database import init_db
from agentlens.storage.repositories import (
    RawCaptureRepository,
    RequestRepository,
    SessionRepository,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine() -> AsyncEngine:
    """Create an in-memory SQLite database and return the engine."""
    return await init_db("")


@pytest.fixture
def session_repo(engine: AsyncEngine) -> SessionRepository:
    return SessionRepository(engine)


@pytest.fixture
def request_repo(engine: AsyncEngine) -> RequestRepository:
    return RequestRepository(engine)


@pytest.fixture
def raw_capture_repo(engine: AsyncEngine) -> RawCaptureRepository:
    return RawCaptureRepository(engine)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(
    *,
    name: str = "test-session",
    started_at: datetime | None = None,
) -> Session:
    return Session(
        name=name,
        started_at=started_at or datetime(2025, 1, 15, 10, 0, 0),
    )


def _make_llm_request(
    session_id: str,
    *,
    model: str = "claude-3-opus",
    provider: str = "anthropic",
    duration_ms: float = 500.0,
    input_tokens: int = 100,
    output_tokens: int = 50,
    cost: float = 0.01,
    with_tools: bool = False,
    timestamp: datetime | None = None,
) -> LLMRequest:
    messages = [
        Message(
            role=MessageRole.USER,
            content=[TextContent(text="Hello, world!")],
        ),
    ]
    response_messages = [
        Message(
            role=MessageRole.ASSISTANT,
            content=[TextContent(text="Hi there!")],
        ),
    ]
    tools: list[ToolDefinition] = []
    if with_tools:
        tools = [
            ToolDefinition(
                name="get_weather",
                description="Get the current weather",
                input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
            ),
        ]
        response_messages = [
            Message(
                role=MessageRole.ASSISTANT,
                content=[
                    ToolUseContent(
                        tool_call_id="call_123",
                        tool_name="get_weather",
                        tool_input={"city": "London"},
                    ),
                ],
            ),
        ]

    return LLMRequest(
        session_id=session_id,
        timestamp=timestamp or datetime(2025, 1, 15, 10, 0, 1),
        duration_ms=duration_ms,
        provider=provider,
        model=model,
        api_endpoint="/v1/messages",
        temperature=0.7,
        max_tokens=1024,
        is_streaming=True,
        system_prompt="You are a helpful assistant.",
        messages=messages,
        tools=tools,
        response_messages=response_messages,
        stop_reason=StopReason.END_TURN,
        usage=TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            estimated_cost_usd=cost,
        ),
        status=RequestStatus.SUCCESS,
        tool_choice={"type": "auto"} if with_tools else None,
        request_params={"extra": "value"},
        response_metadata={"request_id": "req_abc123"},
    )


def _make_raw_capture(session_id: str) -> RawCapture:
    return RawCapture(
        session_id=session_id,
        timestamp=datetime(2025, 1, 15, 10, 0, 0),
        provider="anthropic",
        request_url="https://api.anthropic.com/v1/messages",
        request_method="POST",
        request_headers={"content-type": "application/json", "x-api-key": "sk-***"},
        request_body={"model": "claude-3-opus", "messages": [{"role": "user", "content": "Hi"}]},
        response_status=200,
        response_headers={"content-type": "application/json"},
        response_body={"id": "msg_123", "content": [{"type": "text", "text": "Hello!"}]},
        is_streaming=False,
        sse_events=[],
    )


# ---------------------------------------------------------------------------
# Session tests
# ---------------------------------------------------------------------------


class TestSessionRepository:
    async def test_create_and_get(self, session_repo: SessionRepository) -> None:
        session = _make_session()
        created = await session_repo.create(session)

        assert created.id == session.id

        fetched = await session_repo.get(session.id)
        assert fetched is not None
        assert fetched.id == session.id
        assert fetched.name == "test-session"
        assert fetched.started_at == datetime(2025, 1, 15, 10, 0, 0)
        assert fetched.ended_at is None
        assert fetched.request_count == 0

    async def test_get_nonexistent(self, session_repo: SessionRepository) -> None:
        result = await session_repo.get("does-not-exist")
        assert result is None

    async def test_list_all_ordered_by_started_at_desc(self, session_repo: SessionRepository) -> None:
        s1 = _make_session(name="first", started_at=datetime(2025, 1, 1))
        s2 = _make_session(name="second", started_at=datetime(2025, 1, 2))
        s3 = _make_session(name="third", started_at=datetime(2025, 1, 3))

        await session_repo.create(s1)
        await session_repo.create(s2)
        await session_repo.create(s3)

        all_sessions = await session_repo.list_all()
        assert len(all_sessions) == 3
        assert all_sessions[0].name == "third"
        assert all_sessions[1].name == "second"
        assert all_sessions[2].name == "first"

    async def test_update(self, session_repo: SessionRepository) -> None:
        session = _make_session()
        await session_repo.create(session)

        session.name = "updated-name"
        session.ended_at = datetime(2025, 1, 15, 12, 0, 0)
        session.request_count = 42
        session.total_tokens = 10_000
        session.estimated_cost_usd = 1.23

        await session_repo.update(session)

        fetched = await session_repo.get(session.id)
        assert fetched is not None
        assert fetched.name == "updated-name"
        assert fetched.ended_at == datetime(2025, 1, 15, 12, 0, 0)
        assert fetched.request_count == 42
        assert fetched.total_tokens == 10_000
        assert fetched.estimated_cost_usd == pytest.approx(1.23)

    async def test_delete(self, session_repo: SessionRepository) -> None:
        session = _make_session()
        await session_repo.create(session)

        await session_repo.delete(session.id)

        fetched = await session_repo.get(session.id)
        assert fetched is None

    async def test_delete_nonexistent_does_not_raise(self, session_repo: SessionRepository) -> None:
        # Should not raise even if the session doesn't exist.
        await session_repo.delete("nonexistent-id")


# ---------------------------------------------------------------------------
# LLMRequest tests
# ---------------------------------------------------------------------------


class TestRequestRepository:
    async def test_create_and_get_full_content(
        self,
        session_repo: SessionRepository,
        request_repo: RequestRepository,
    ) -> None:
        session = _make_session()
        await session_repo.create(session)

        req = _make_llm_request(session.id, with_tools=True)
        await request_repo.create(req)

        fetched = await request_repo.get(req.id)
        assert fetched is not None
        assert fetched.id == req.id
        assert fetched.session_id == session.id
        assert fetched.provider == "anthropic"
        assert fetched.model == "claude-3-opus"
        assert fetched.temperature == pytest.approx(0.7)
        assert fetched.max_tokens == 1024
        assert fetched.is_streaming is True
        assert fetched.system_prompt == "You are a helpful assistant."
        assert fetched.stop_reason == StopReason.END_TURN
        assert fetched.status == RequestStatus.SUCCESS

        # Messages round-trip
        assert len(fetched.messages) == 1
        assert fetched.messages[0].role == MessageRole.USER
        assert fetched.messages[0].content[0].text == "Hello, world!"  # type: ignore[union-attr]

        # Tools round-trip
        assert len(fetched.tools) == 1
        assert fetched.tools[0].name == "get_weather"
        assert fetched.tools[0].input_schema["properties"]["city"]["type"] == "string"

        # Response messages with tool use round-trip
        assert len(fetched.response_messages) == 1
        resp_block = fetched.response_messages[0].content[0]
        assert resp_block.type == "tool_use"
        assert resp_block.tool_name == "get_weather"  # type: ignore[union-attr]

        # Usage round-trip
        assert fetched.usage.input_tokens == 100
        assert fetched.usage.output_tokens == 50
        assert fetched.usage.total_tokens == 150
        assert fetched.usage.estimated_cost_usd == pytest.approx(0.01)

        # tool_choice round-trip
        assert fetched.tool_choice == {"type": "auto"}

        # Extras round-trip
        assert fetched.request_params == {"extra": "value"}
        assert fetched.response_metadata == {"request_id": "req_abc123"}

    async def test_get_nonexistent(self, request_repo: RequestRepository) -> None:
        result = await request_repo.get("no-such-id")
        assert result is None

    async def test_list_by_session_basic(
        self,
        session_repo: SessionRepository,
        request_repo: RequestRepository,
    ) -> None:
        session = _make_session()
        await session_repo.create(session)

        # Create 3 requests at different times
        for i in range(3):
            req = _make_llm_request(
                session.id,
                timestamp=datetime(2025, 1, 15, 10, 0, i),
            )
            await request_repo.create(req)

        results = await request_repo.list_by_session(session.id)
        assert len(results) == 3
        # Should be ordered by timestamp ascending
        for i in range(len(results) - 1):
            assert results[i].timestamp <= results[i + 1].timestamp

    async def test_list_by_session_filter_provider(
        self,
        session_repo: SessionRepository,
        request_repo: RequestRepository,
    ) -> None:
        session = _make_session()
        await session_repo.create(session)

        await request_repo.create(_make_llm_request(session.id, provider="anthropic"))
        await request_repo.create(_make_llm_request(session.id, provider="openai", model="gpt-4"))

        anthropic_only = await request_repo.list_by_session(session.id, provider="anthropic")
        assert len(anthropic_only) == 1
        assert anthropic_only[0].provider == "anthropic"

    async def test_list_by_session_filter_model(
        self,
        session_repo: SessionRepository,
        request_repo: RequestRepository,
    ) -> None:
        session = _make_session()
        await session_repo.create(session)

        await request_repo.create(_make_llm_request(session.id, model="claude-3-opus"))
        await request_repo.create(_make_llm_request(session.id, model="gpt-4", provider="openai"))

        opus_only = await request_repo.list_by_session(session.id, model="claude-3-opus")
        assert len(opus_only) == 1
        assert opus_only[0].model == "claude-3-opus"

    async def test_list_by_session_filter_has_tools(
        self,
        session_repo: SessionRepository,
        request_repo: RequestRepository,
    ) -> None:
        session = _make_session()
        await session_repo.create(session)

        await request_repo.create(_make_llm_request(session.id, with_tools=True))
        await request_repo.create(_make_llm_request(session.id, with_tools=False))

        with_tools = await request_repo.list_by_session(session.id, has_tools=True)
        assert len(with_tools) == 1
        assert len(with_tools[0].tools) > 0

        without_tools = await request_repo.list_by_session(session.id, has_tools=False)
        assert len(without_tools) == 1
        assert len(without_tools[0].tools) == 0

    async def test_list_by_session_offset_and_limit(
        self,
        session_repo: SessionRepository,
        request_repo: RequestRepository,
    ) -> None:
        session = _make_session()
        await session_repo.create(session)

        for i in range(5):
            await request_repo.create(
                _make_llm_request(
                    session.id,
                    timestamp=datetime(2025, 1, 15, 10, 0, i),
                )
            )

        page = await request_repo.list_by_session(session.id, offset=2, limit=2)
        assert len(page) == 2

    async def test_count_by_session(
        self,
        session_repo: SessionRepository,
        request_repo: RequestRepository,
    ) -> None:
        session = _make_session()
        await session_repo.create(session)

        for i in range(3):
            await request_repo.create(
                _make_llm_request(
                    session.id,
                    timestamp=datetime(2025, 1, 15, 10, 0, i),
                )
            )

        count = await request_repo.count_by_session(session.id)
        assert count == 3

    async def test_count_by_session_empty(self, request_repo: RequestRepository) -> None:
        count = await request_repo.count_by_session("nonexistent")
        assert count == 0


# ---------------------------------------------------------------------------
# Session stats tests
# ---------------------------------------------------------------------------


class TestSessionStats:
    async def test_get_stats_aggregation(
        self,
        session_repo: SessionRepository,
        request_repo: RequestRepository,
    ) -> None:
        session = _make_session()
        await session_repo.create(session)

        await request_repo.create(
            _make_llm_request(
                session.id,
                model="claude-3-opus",
                provider="anthropic",
                duration_ms=400.0,
                input_tokens=100,
                output_tokens=50,
                cost=0.01,
                timestamp=datetime(2025, 1, 15, 10, 0, 0),
            )
        )
        await request_repo.create(
            _make_llm_request(
                session.id,
                model="gpt-4",
                provider="openai",
                duration_ms=600.0,
                input_tokens=200,
                output_tokens=100,
                cost=0.02,
                timestamp=datetime(2025, 1, 15, 10, 0, 1),
            )
        )

        stats = await session_repo.get_stats(session.id)

        assert stats.total_requests == 2
        assert stats.total_input_tokens == 300
        assert stats.total_output_tokens == 150
        assert stats.total_tokens == 450
        assert stats.estimated_cost_usd == pytest.approx(0.03)
        assert stats.avg_duration_ms == pytest.approx(500.0)
        assert stats.avg_tokens_per_request == pytest.approx(225.0)
        assert set(stats.models_used) == {"claude-3-opus", "gpt-4"}
        assert set(stats.providers_used) == {"anthropic", "openai"}

    async def test_get_stats_empty_session(self, session_repo: SessionRepository) -> None:
        session = _make_session()
        await session_repo.create(session)

        stats = await session_repo.get_stats(session.id)
        assert stats.total_requests == 0
        assert stats.total_tokens == 0
        assert stats.estimated_cost_usd == 0.0
        assert stats.avg_duration_ms is None
        assert stats.avg_tokens_per_request is None
        assert stats.models_used == []
        assert stats.providers_used == []


# ---------------------------------------------------------------------------
# RawCapture tests
# ---------------------------------------------------------------------------


class TestRawCaptureRepository:
    async def test_create_and_get(
        self,
        session_repo: SessionRepository,
        raw_capture_repo: RawCaptureRepository,
    ) -> None:
        session = _make_session()
        await session_repo.create(session)

        capture = _make_raw_capture(session.id)
        await raw_capture_repo.create(capture)

        fetched = await raw_capture_repo.get(capture.id)
        assert fetched is not None
        assert fetched.id == capture.id
        assert fetched.session_id == session.id
        assert fetched.provider == "anthropic"
        assert fetched.request_url == "https://api.anthropic.com/v1/messages"
        assert fetched.request_method == "POST"
        assert fetched.request_headers["content-type"] == "application/json"
        assert fetched.request_body["model"] == "claude-3-opus"  # type: ignore[index]
        assert fetched.response_status == 200
        assert fetched.response_body["id"] == "msg_123"  # type: ignore[index]
        assert fetched.is_streaming is False
        assert fetched.sse_events == []

    async def test_get_nonexistent(self, raw_capture_repo: RawCaptureRepository) -> None:
        result = await raw_capture_repo.get("no-such-capture")
        assert result is None

    async def test_create_with_sse_events(
        self,
        session_repo: SessionRepository,
        raw_capture_repo: RawCaptureRepository,
    ) -> None:
        session = _make_session()
        await session_repo.create(session)

        capture = RawCapture(
            session_id=session.id,
            timestamp=datetime(2025, 1, 15, 10, 0, 0),
            provider="anthropic",
            request_url="https://api.anthropic.com/v1/messages",
            is_streaming=True,
            sse_events=[
                {"type": "message_start", "message": {"id": "msg_1"}},
                {"type": "content_block_delta", "delta": {"text": "Hello"}},
                {"type": "message_stop"},
            ],
        )
        await raw_capture_repo.create(capture)

        fetched = await raw_capture_repo.get(capture.id)
        assert fetched is not None
        assert fetched.is_streaming is True
        assert len(fetched.sse_events) == 3
        assert fetched.sse_events[0]["type"] == "message_start"
        assert fetched.sse_events[1]["delta"]["text"] == "Hello"
