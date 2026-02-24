"""Tests for the FastAPI server routes using httpx AsyncClient."""

from __future__ import annotations

from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient

from agentlens.models.base import (
    LLMRequest,
    Message,
    Session,
    TextContent,
    ThinkingContent,
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
from agentlens.server.app import create_app
from agentlens.storage.database import init_db
from agentlens.storage.repositories import (
    RawCaptureRepository,
    RequestRepository,
    SessionRepository,
)


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
    with_thinking: bool = False,
    timestamp: datetime | None = None,
    raw_capture_id: str = "",
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

    if with_thinking:
        response_messages = [
            Message(
                role=MessageRole.ASSISTANT,
                content=[
                    ThinkingContent(thinking="Let me think about this..."),
                    TextContent(text="Here is my answer."),
                ],
            ),
        ]

    return LLMRequest(
        session_id=session_id,
        raw_capture_id=raw_capture_id,
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


def _make_raw_capture(session_id: str, capture_id: str | None = None) -> RawCapture:
    capture = RawCapture(
        session_id=session_id,
        timestamp=datetime(2025, 1, 15, 10, 0, 0),
        provider="anthropic",
        request_url="https://api.anthropic.com/v1/messages",
        request_method="POST",
        request_headers={"content-type": "application/json"},
        request_body={"model": "claude-3-opus", "messages": [{"role": "user", "content": "Hi"}]},
        response_status=200,
        response_headers={"content-type": "application/json"},
        response_body={"id": "msg_123", "content": [{"type": "text", "text": "Hello!"}]},
        is_streaming=False,
        sse_events=[],
    )
    if capture_id:
        capture.id = capture_id
    return capture


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def app():
    """Create a FastAPI app wired to an in-memory SQLite database."""
    application = create_app()

    # Override lifespan state with in-memory DB.
    engine = await init_db("")

    application.state.engine = engine
    application.state.session_repo = SessionRepository(engine)
    application.state.request_repo = RequestRepository(engine)
    application.state.raw_capture_repo = RawCaptureRepository(engine)

    from agentlens.server.event_bus import EventBus

    application.state.event_bus = EventBus()

    return application


@pytest.fixture
async def client(app) -> AsyncClient:
    """Return an httpx AsyncClient bound to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def session_repo(app) -> SessionRepository:
    return app.state.session_repo


@pytest.fixture
def request_repo(app) -> RequestRepository:
    return app.state.request_repo


@pytest.fixture
def raw_capture_repo(app) -> RawCaptureRepository:
    return app.state.raw_capture_repo


# ---------------------------------------------------------------------------
# Session route tests
# ---------------------------------------------------------------------------


class TestSessionRoutes:
    async def test_list_sessions_empty(self, client: AsyncClient) -> None:
        resp = await client.get("/api/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_sessions_with_data(
        self,
        client: AsyncClient,
        session_repo: SessionRepository,
    ) -> None:
        s1 = _make_session(name="session-alpha", started_at=datetime(2025, 1, 1))
        s2 = _make_session(name="session-beta", started_at=datetime(2025, 1, 2))
        await session_repo.create(s1)
        await session_repo.create(s2)

        resp = await client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # Ordered by started_at desc.
        assert data[0]["name"] == "session-beta"
        assert data[1]["name"] == "session-alpha"

    async def test_get_session_with_stats(
        self,
        client: AsyncClient,
        session_repo: SessionRepository,
        request_repo: RequestRepository,
    ) -> None:
        session = _make_session()
        await session_repo.create(session)

        req = _make_llm_request(
            session.id,
            input_tokens=100,
            output_tokens=50,
            cost=0.01,
        )
        await request_repo.create(req)

        resp = await client.get(f"/api/sessions/{session.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == session.id
        assert data["name"] == "test-session"
        assert "stats" in data
        assert data["stats"]["total_requests"] == 1
        assert data["stats"]["total_tokens"] == 150
        assert data["stats"]["estimated_cost_usd"] == pytest.approx(0.01)

    async def test_get_session_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/sessions/nonexistent")
        assert resp.status_code == 404

    async def test_delete_session(
        self,
        client: AsyncClient,
        session_repo: SessionRepository,
    ) -> None:
        session = _make_session()
        await session_repo.create(session)

        resp = await client.delete(f"/api/sessions/{session.id}")
        assert resp.status_code == 204

        # Verify it was deleted.
        fetched = await session_repo.get(session.id)
        assert fetched is None

    async def test_delete_session_not_found(self, client: AsyncClient) -> None:
        resp = await client.delete("/api/sessions/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Request route tests
# ---------------------------------------------------------------------------


class TestRequestRoutes:
    async def test_list_requests_basic(
        self,
        client: AsyncClient,
        session_repo: SessionRepository,
        request_repo: RequestRepository,
    ) -> None:
        session = _make_session()
        await session_repo.create(session)

        for i in range(3):
            req = _make_llm_request(
                session.id,
                timestamp=datetime(2025, 1, 15, 10, 0, i),
            )
            await request_repo.create(req)

        resp = await client.get(f"/api/sessions/{session.id}/requests")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

        # Check summary shape.
        item = data[0]
        assert "id" in item
        assert "session_id" in item
        assert "timestamp" in item
        assert "provider" in item
        assert "model" in item
        assert "duration_ms" in item
        assert "is_streaming" in item
        assert "status" in item
        assert "stop_reason" in item
        assert "usage" in item
        assert "preview_text" in item
        assert "has_tools" in item
        assert "has_thinking" in item

    async def test_list_requests_filter_provider(
        self,
        client: AsyncClient,
        session_repo: SessionRepository,
        request_repo: RequestRepository,
    ) -> None:
        session = _make_session()
        await session_repo.create(session)

        await request_repo.create(
            _make_llm_request(session.id, provider="anthropic")
        )
        await request_repo.create(
            _make_llm_request(
                session.id, provider="openai", model="gpt-4"
            )
        )

        resp = await client.get(
            f"/api/sessions/{session.id}/requests",
            params={"provider": "anthropic"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["provider"] == "anthropic"

    async def test_list_requests_filter_model(
        self,
        client: AsyncClient,
        session_repo: SessionRepository,
        request_repo: RequestRepository,
    ) -> None:
        session = _make_session()
        await session_repo.create(session)

        await request_repo.create(
            _make_llm_request(session.id, model="claude-3-opus")
        )
        await request_repo.create(
            _make_llm_request(
                session.id, model="gpt-4", provider="openai"
            )
        )

        resp = await client.get(
            f"/api/sessions/{session.id}/requests",
            params={"model": "claude-3-opus"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["model"] == "claude-3-opus"

    async def test_list_requests_filter_has_tools(
        self,
        client: AsyncClient,
        session_repo: SessionRepository,
        request_repo: RequestRepository,
    ) -> None:
        session = _make_session()
        await session_repo.create(session)

        await request_repo.create(
            _make_llm_request(session.id, with_tools=True)
        )
        await request_repo.create(
            _make_llm_request(session.id, with_tools=False)
        )

        resp = await client.get(
            f"/api/sessions/{session.id}/requests",
            params={"has_tools": "true"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["has_tools"] is True

    async def test_list_requests_preview_text(
        self,
        client: AsyncClient,
        session_repo: SessionRepository,
        request_repo: RequestRepository,
    ) -> None:
        session = _make_session()
        await session_repo.create(session)

        req = _make_llm_request(session.id)
        await request_repo.create(req)

        resp = await client.get(f"/api/sessions/{session.id}/requests")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["preview_text"] == "Hello, world!"

    async def test_list_requests_has_thinking(
        self,
        client: AsyncClient,
        session_repo: SessionRepository,
        request_repo: RequestRepository,
    ) -> None:
        session = _make_session()
        await session_repo.create(session)

        req = _make_llm_request(session.id, with_thinking=True)
        await request_repo.create(req)

        resp = await client.get(f"/api/sessions/{session.id}/requests")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["has_thinking"] is True

    async def test_list_requests_offset_and_limit(
        self,
        client: AsyncClient,
        session_repo: SessionRepository,
        request_repo: RequestRepository,
    ) -> None:
        session = _make_session()
        await session_repo.create(session)

        for i in range(5):
            req = _make_llm_request(
                session.id,
                timestamp=datetime(2025, 1, 15, 10, 0, i),
            )
            await request_repo.create(req)

        resp = await client.get(
            f"/api/sessions/{session.id}/requests",
            params={"offset": 2, "limit": 2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_get_request_full_detail(
        self,
        client: AsyncClient,
        session_repo: SessionRepository,
        request_repo: RequestRepository,
    ) -> None:
        session = _make_session()
        await session_repo.create(session)

        req = _make_llm_request(session.id, with_tools=True)
        await request_repo.create(req)

        resp = await client.get(f"/api/requests/{req.id}")
        assert resp.status_code == 200
        data = resp.json()

        assert data["id"] == req.id
        assert data["session_id"] == session.id
        assert data["provider"] == "anthropic"
        assert data["model"] == "claude-3-opus"
        assert data["is_streaming"] is True
        assert data["status"] == "success"
        assert data["stop_reason"] == "end_turn"

        # Full messages present.
        assert len(data["messages"]) == 1
        assert data["messages"][0]["role"] == "user"

        # Tools present.
        assert len(data["tools"]) == 1
        assert data["tools"][0]["name"] == "get_weather"

        # Usage present.
        assert data["usage"]["input_tokens"] == 100
        assert data["usage"]["output_tokens"] == 50

    async def test_get_request_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/requests/nonexistent")
        assert resp.status_code == 404

    async def test_get_request_raw(
        self,
        client: AsyncClient,
        session_repo: SessionRepository,
        request_repo: RequestRepository,
        raw_capture_repo: RawCaptureRepository,
    ) -> None:
        session = _make_session()
        await session_repo.create(session)

        capture = _make_raw_capture(session.id)
        await raw_capture_repo.create(capture)

        req = _make_llm_request(session.id, raw_capture_id=capture.id)
        await request_repo.create(req)

        resp = await client.get(f"/api/requests/{req.id}/raw")
        assert resp.status_code == 200
        data = resp.json()

        assert data["id"] == capture.id
        assert data["session_id"] == session.id
        assert data["provider"] == "anthropic"
        assert data["request_url"] == "https://api.anthropic.com/v1/messages"
        assert data["response_status"] == 200

    async def test_get_request_raw_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/requests/nonexistent/raw")
        assert resp.status_code == 404

    async def test_get_request_raw_no_capture(
        self,
        client: AsyncClient,
        session_repo: SessionRepository,
        request_repo: RequestRepository,
    ) -> None:
        session = _make_session()
        await session_repo.create(session)

        req = _make_llm_request(session.id, raw_capture_id="")
        await request_repo.create(req)

        resp = await client.get(f"/api/requests/{req.id}/raw")
        assert resp.status_code == 404
