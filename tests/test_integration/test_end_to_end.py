"""End-to-end integration tests for the agentlens pipeline.

These tests verify the full flow: raw capture -> parsing -> storage -> API retrieval.
They do NOT start mitmproxy; instead they simulate the pipeline by loading fixtures,
creating RawCapture objects, parsing them, storing the results, and then verifying
everything is retrievable via the FastAPI REST API.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from agentlens.models import RawCapture, Session
from agentlens.providers import PluginRegistry
from agentlens.server.app import create_app
from agentlens.server.event_bus import EventBus
from agentlens.storage.database import init_db
from agentlens.storage.repositories import (
    RawCaptureRepository,
    RequestRepository,
    SessionRepository,
)
from tests.conftest import load_fixture


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest.fixture
async def integration_env():
    """Set up full integration environment with in-memory DB."""
    engine = await init_db(":memory:")
    session_repo = SessionRepository(engine)
    request_repo = RequestRepository(engine)
    raw_repo = RawCaptureRepository(engine)
    event_bus = EventBus()
    plugin_registry = PluginRegistry.default()

    # Create a session
    session = Session(name="Integration Test")
    await session_repo.create(session)

    # Create FastAPI app
    app = create_app(skip_lifespan=True)
    app.state.engine = engine
    app.state.session_repo = session_repo
    app.state.request_repo = request_repo
    app.state.raw_capture_repo = raw_repo
    app.state.event_bus = event_bus

    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    yield {
        "engine": engine,
        "session": session,
        "session_repo": session_repo,
        "request_repo": request_repo,
        "raw_repo": raw_repo,
        "event_bus": event_bus,
        "plugin_registry": plugin_registry,
        "client": client,
    }

    await client.aclose()
    await engine.dispose()


_PROVIDER_MAP = {
    "openai": "openai",
    "anthropic": "anthropic",
}


async def process_fixture(env, provider_name: str, fixture_name: str):
    """Load fixture, create RawCapture, parse, store, return request ID."""
    fixture = load_fixture(provider_name, fixture_name)

    provider = _PROVIDER_MAP.get(provider_name, "unknown")
    is_streaming = bool(fixture.get("sse_events"))

    raw = RawCapture(
        session_id=env["session"].id,
        provider=provider,
        request_url=fixture["request_url"],
        request_method="POST",
        request_headers=fixture["request_headers"],
        request_body=fixture["request_body"],
        response_status=fixture["response_status"],
        response_headers=fixture["response_headers"],
        response_body=fixture["response_body"],
        is_streaming=is_streaming,
        sse_events=fixture.get("sse_events", []),
    )
    await env["raw_repo"].create(raw)

    plugin = env["plugin_registry"].get_plugin(raw)
    assert plugin is not None, f"No plugin found for {provider_name}/{fixture_name}"

    llm_request = plugin.parse(raw, duration_ms=1500.0, ttft_ms=200.0 if is_streaming else None)
    llm_request.session_id = env["session"].id
    llm_request.raw_capture_id = raw.id
    await env["request_repo"].create(llm_request)

    return llm_request.id, raw.id


# ---------------------------------------------------------------------------
# Test 1: OpenAI non-streaming end-to-end
# ---------------------------------------------------------------------------


class TestOpenAINonStreamingE2E:
    async def test_openai_non_streaming_e2e(self, integration_env):
        env = integration_env
        req_id, raw_id = await process_fixture(env, "openai", "chat_completion")

        # Verify via list API
        resp = await env["client"].get(f"/api/sessions/{env['session'].id}/requests")
        assert resp.status_code == 200
        requests = resp.json()
        assert len(requests) == 1
        assert requests[0]["provider"] == "openai"
        assert requests[0]["model"].startswith("gpt-4o")

        # Get full detail
        resp = await env["client"].get(f"/api/requests/{req_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["system_prompt"] is not None
        assert len(detail["messages"]) > 0
        assert len(detail["response_messages"]) > 0
        assert detail["usage"]["total_tokens"] > 0
        assert detail["stop_reason"] == "end_turn"
        assert detail["is_streaming"] is False

        # Get raw capture
        resp = await env["client"].get(f"/api/requests/{req_id}/raw")
        assert resp.status_code == 200
        raw_data = resp.json()
        assert "api.openai.com" in raw_data["request_url"]


# ---------------------------------------------------------------------------
# Test 2: OpenAI streaming end-to-end
# ---------------------------------------------------------------------------


class TestOpenAIStreamingE2E:
    async def test_openai_streaming_e2e(self, integration_env):
        env = integration_env
        req_id, raw_id = await process_fixture(env, "openai", "chat_completion_streaming")

        # Verify via list API
        resp = await env["client"].get(f"/api/sessions/{env['session'].id}/requests")
        assert resp.status_code == 200
        requests = resp.json()
        assert len(requests) == 1
        assert requests[0]["is_streaming"] is True

        # Get full detail
        resp = await env["client"].get(f"/api/requests/{req_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["is_streaming"] is True

        # Verify SSE chunks were reassembled into response text
        assert len(detail["response_messages"]) > 0
        resp_msg = detail["response_messages"][0]
        assert len(resp_msg["content"]) > 0
        text_block = resp_msg["content"][0]
        assert text_block["type"] == "text"
        assert "Paris" in text_block["text"]

        # Verify usage is populated (from stream_options include_usage)
        assert detail["usage"]["total_tokens"] > 0
        assert detail["usage"]["input_tokens"] > 0
        assert detail["usage"]["output_tokens"] > 0


# ---------------------------------------------------------------------------
# Test 3: Anthropic non-streaming end-to-end
# ---------------------------------------------------------------------------


class TestAnthropicNonStreamingE2E:
    async def test_anthropic_non_streaming_e2e(self, integration_env):
        env = integration_env
        req_id, raw_id = await process_fixture(env, "anthropic", "messages")

        # Verify via list API
        resp = await env["client"].get(f"/api/sessions/{env['session'].id}/requests")
        assert resp.status_code == 200
        requests = resp.json()
        assert len(requests) == 1
        assert requests[0]["provider"] == "anthropic"
        assert requests[0]["model"].startswith("claude")

        # Get full detail
        resp = await env["client"].get(f"/api/requests/{req_id}")
        assert resp.status_code == 200
        detail = resp.json()

        # Verify system_prompt extracted from top-level system field
        assert detail["system_prompt"] is not None
        assert "software engineer" in detail["system_prompt"].lower()

        # Verify response has text content
        assert len(detail["response_messages"]) > 0
        resp_msg = detail["response_messages"][0]
        assert len(resp_msg["content"]) > 0
        text_block = resp_msg["content"][0]
        assert text_block["type"] == "text"
        assert len(text_block["text"]) > 0


# ---------------------------------------------------------------------------
# Test 4: Anthropic streaming end-to-end
# ---------------------------------------------------------------------------


class TestAnthropicStreamingE2E:
    async def test_anthropic_streaming_e2e(self, integration_env):
        env = integration_env
        req_id, raw_id = await process_fixture(env, "anthropic", "messages_streaming")

        # Verify via list API
        resp = await env["client"].get(f"/api/sessions/{env['session'].id}/requests")
        assert resp.status_code == 200
        requests = resp.json()
        assert len(requests) == 1
        assert requests[0]["is_streaming"] is True

        # Get full detail
        resp = await env["client"].get(f"/api/requests/{req_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["is_streaming"] is True

        # Verify SSE reassembly produces text
        assert len(detail["response_messages"]) > 0
        resp_msg = detail["response_messages"][0]
        assert len(resp_msg["content"]) > 0
        text_block = resp_msg["content"][0]
        assert text_block["type"] == "text"
        # The reassembled text should contain content about Rust ownership
        assert "ownership" in text_block["text"].lower()


# ---------------------------------------------------------------------------
# Test 5: Tool calling end-to-end (OpenAI)
# ---------------------------------------------------------------------------


class TestOpenAIToolCallingE2E:
    async def test_openai_tool_calling_e2e(self, integration_env):
        env = integration_env
        req_id, raw_id = await process_fixture(env, "openai", "chat_completion_tools")

        # Get full detail
        resp = await env["client"].get(f"/api/requests/{req_id}")
        assert resp.status_code == 200
        detail = resp.json()

        # Verify tools list is populated
        assert len(detail["tools"]) > 0
        tool = detail["tools"][0]
        assert tool["name"] == "get_weather"
        assert tool["description"] != ""
        assert "properties" in tool["input_schema"]

        # Verify messages contain tool-related content (assistant with tool_calls
        # and tool result messages in the conversation history)
        has_tool_use = False
        has_tool_result = False
        for msg in detail["messages"]:
            for block in msg["content"]:
                if block["type"] == "tool_use":
                    has_tool_use = True
                if block["type"] == "tool_result":
                    has_tool_result = True
        assert has_tool_use, "Expected ToolUseContent in request messages"
        assert has_tool_result, "Expected ToolResultContent in request messages"

        # Verify the summary shows has_tools=True
        resp = await env["client"].get(f"/api/sessions/{env['session'].id}/requests")
        assert resp.status_code == 200
        summaries = resp.json()
        assert summaries[0]["has_tools"] is True


# ---------------------------------------------------------------------------
# Test 6: Tool calling end-to-end (Anthropic)
# ---------------------------------------------------------------------------


class TestAnthropicToolCallingE2E:
    async def test_anthropic_tool_calling_e2e(self, integration_env):
        env = integration_env
        req_id, raw_id = await process_fixture(env, "anthropic", "messages_tool_use")

        # Get full detail
        resp = await env["client"].get(f"/api/requests/{req_id}")
        assert resp.status_code == 200
        detail = resp.json()

        # Verify tools list is populated
        assert len(detail["tools"]) >= 2
        tool_names = [t["name"] for t in detail["tools"]]
        assert "get_stock_price" in tool_names
        assert "get_company_info" in tool_names

        # Verify tool definitions have proper structure
        for tool in detail["tools"]:
            assert tool["name"] != ""
            assert tool["description"] != ""
            assert "properties" in tool["input_schema"]

        # Verify tool_use content block in response
        assert len(detail["response_messages"]) > 0
        resp_msg = detail["response_messages"][0]
        has_tool_use = any(block["type"] == "tool_use" for block in resp_msg["content"])
        assert has_tool_use, "Expected tool_use content block in response"

        # Verify stop_reason is tool_use
        assert detail["stop_reason"] == "tool_use"


# ---------------------------------------------------------------------------
# Test 7: Thinking blocks end-to-end
# ---------------------------------------------------------------------------


class TestThinkingBlocksE2E:
    async def test_thinking_blocks_e2e(self, integration_env):
        env = integration_env
        req_id, raw_id = await process_fixture(env, "anthropic", "messages_thinking")

        # Get full detail
        resp = await env["client"].get(f"/api/requests/{req_id}")
        assert resp.status_code == 200
        detail = resp.json()

        # Verify ThinkingContent block exists in response_messages
        assert len(detail["response_messages"]) > 0
        resp_msg = detail["response_messages"][0]
        thinking_blocks = [block for block in resp_msg["content"] if block["type"] == "thinking"]
        assert len(thinking_blocks) > 0, "Expected ThinkingContent block in response"

        # Verify thinking text is populated
        thinking_block = thinking_blocks[0]
        assert len(thinking_block["thinking"]) > 0
        assert "strawberry" in thinking_block["thinking"].lower()

        # Verify GET /api/sessions/{id}/requests shows has_thinking=True in summary
        resp = await env["client"].get(f"/api/sessions/{env['session'].id}/requests")
        assert resp.status_code == 200
        summaries = resp.json()
        assert len(summaries) == 1
        assert summaries[0]["has_thinking"] is True


# ---------------------------------------------------------------------------
# Test 8: MCP tools end-to-end
# ---------------------------------------------------------------------------


class TestMCPToolsE2E:
    async def test_mcp_tools_e2e(self, integration_env):
        env = integration_env
        req_id, raw_id = await process_fixture(env, "anthropic", "messages_mcp")

        # Get full detail
        resp = await env["client"].get(f"/api/requests/{req_id}")
        assert resp.status_code == 200
        detail = resp.json()

        # Verify tools are present and contain MCP tools
        assert len(detail["tools"]) > 0

        mcp_tools = [t for t in detail["tools"] if t["is_mcp"] is True]
        assert len(mcp_tools) > 0, "Expected at least one MCP tool"

        # Verify mcp_server_name is populated
        mcp_server_names = {t["mcp_server_name"] for t in mcp_tools}
        assert "filesystem" in mcp_server_names, "Expected 'filesystem' MCP server"
        assert "github" in mcp_server_names, "Expected 'github' MCP server"

        # Verify specific MCP tool names follow the mcp__<server>__<name> pattern
        mcp_tool_names = [t["name"] for t in mcp_tools]
        assert any("mcp__filesystem__" in name for name in mcp_tool_names)
        assert any("mcp__github__" in name for name in mcp_tool_names)


# ---------------------------------------------------------------------------
# Test 9: Session listing and stats
# ---------------------------------------------------------------------------


class TestSessionListingAndStats:
    async def test_session_listing_and_stats(self, integration_env):
        env = integration_env

        # Process multiple fixtures (OpenAI + Anthropic)
        await process_fixture(env, "openai", "chat_completion")
        await process_fixture(env, "anthropic", "messages")

        # Verify GET /api/sessions returns the session
        resp = await env["client"].get("/api/sessions")
        assert resp.status_code == 200
        sessions = resp.json()
        assert len(sessions) >= 1
        session_ids = [s["id"] for s in sessions]
        assert env["session"].id in session_ids

        # Verify GET /api/sessions/{id} returns stats with correct aggregation
        resp = await env["client"].get(f"/api/sessions/{env['session'].id}")
        assert resp.status_code == 200
        session_detail = resp.json()
        assert session_detail["id"] == env["session"].id
        assert "stats" in session_detail

        stats = session_detail["stats"]
        # Verify request_count matches number of processed requests
        assert stats["total_requests"] == 2
        assert stats["total_tokens"] > 0
        assert stats["total_input_tokens"] > 0
        assert stats["total_output_tokens"] > 0

        # Verify models and providers are tracked
        assert len(stats["models_used"]) == 2
        assert len(stats["providers_used"]) == 2
        assert "openai" in stats["providers_used"]
        assert "anthropic" in stats["providers_used"]


# ---------------------------------------------------------------------------
# Test 10: Non-LLM traffic is not captured
# ---------------------------------------------------------------------------


class TestNonLLMTraffic:
    async def test_non_llm_traffic_not_captured(self, integration_env):
        env = integration_env

        # Create a RawCapture with a non-LLM URL
        raw = RawCapture(
            session_id=env["session"].id,
            provider="unknown",
            request_url="https://example.com/api/data",
            request_method="GET",
            request_headers={"content-type": "application/json"},
            request_body={},
            response_status=200,
            response_headers={"content-type": "application/json"},
            response_body={"result": "some data"},
            is_streaming=False,
            sse_events=[],
        )

        # Verify no plugin can handle it
        plugin = env["plugin_registry"].get_plugin(raw)
        assert plugin is None, f"Expected no plugin to handle non-LLM traffic, but got {type(plugin).__name__}"
