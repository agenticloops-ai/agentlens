"""Tests for the OpenAI chat completions parser."""

import pytest

from agentlens.models import (
    MessageRole,
    RawCapture,
    StopReason,
    TextContent,
    ToolResultContent,
    ToolUseContent,
)
from agentlens.providers.openai import OpenAICompletionsPlugin
from tests.conftest import load_fixture


@pytest.fixture
def plugin() -> OpenAICompletionsPlugin:
    return OpenAICompletionsPlugin()


def _raw_from_fixture(fixture: dict, is_streaming: bool = False) -> RawCapture:
    """Build a RawCapture from a fixture dict."""
    return RawCapture(
        request_url=fixture["request_url"],
        request_headers=fixture.get("request_headers", {}),
        request_body=fixture["request_body"],
        response_status=fixture.get("response_status", 200),
        response_headers=fixture.get("response_headers", {}),
        response_body=fixture.get("response_body", ""),
        is_streaming=is_streaming,
        sse_events=fixture.get("sse_events", []),
    )


# ---------------------------------------------------------------------------
# can_parse
# ---------------------------------------------------------------------------


class TestCanParse:
    def test_openai_url(self, plugin: OpenAICompletionsPlugin) -> None:
        raw = RawCapture(request_url="https://api.openai.com/v1/chat/completions")
        assert plugin.can_parse(raw) is True

    def test_generic_v1_chat_completions_path(self, plugin: OpenAICompletionsPlugin) -> None:
        raw = RawCapture(request_url="http://localhost:8080/v1/chat/completions")
        assert plugin.can_parse(raw) is True

    def test_unrelated_url(self, plugin: OpenAICompletionsPlugin) -> None:
        raw = RawCapture(request_url="https://api.anthropic.com/v1/messages")
        assert plugin.can_parse(raw) is False

    def test_openai_subdomain(self, plugin: OpenAICompletionsPlugin) -> None:
        raw = RawCapture(request_url="https://custom.api.openai.com/v1/chat/completions")
        assert plugin.can_parse(raw) is True


# ---------------------------------------------------------------------------
# Non-streaming chat completion
# ---------------------------------------------------------------------------


class TestParseChatCompletion:
    @pytest.fixture
    def fixture(self) -> dict:
        return load_fixture("openai", "chat_completion")

    @pytest.fixture
    def result(self, plugin: OpenAICompletionsPlugin, fixture: dict):
        raw = _raw_from_fixture(fixture)
        return plugin.parse(raw, duration_ms=1842.0)

    def test_provider(self, result) -> None:
        assert result.provider == "openai"

    def test_model(self, result) -> None:
        assert result.model == "gpt-4o"

    def test_system_prompt(self, result) -> None:
        assert result.system_prompt == "You are a helpful assistant that provides concise, well-structured answers."

    def test_messages_count(self, result) -> None:
        # Only user message (system is extracted separately)
        assert len(result.messages) == 1
        assert result.messages[0].role == MessageRole.USER

    def test_user_message_content(self, result) -> None:
        msg = result.messages[0]
        assert len(msg.content) == 1
        assert isinstance(msg.content[0], TextContent)
        assert "TCP" in msg.content[0].text

    def test_temperature(self, result) -> None:
        assert result.temperature == 0.7

    def test_max_tokens(self, result) -> None:
        assert result.max_tokens == 1024

    def test_top_p(self, result) -> None:
        assert result.top_p == 1.0

    def test_is_not_streaming(self, result) -> None:
        assert result.is_streaming is False

    def test_stop_reason(self, result) -> None:
        assert result.stop_reason == StopReason.END_TURN

    def test_response_text(self, result) -> None:
        assert len(result.response_messages) == 1
        resp = result.response_messages[0]
        assert resp.role == MessageRole.ASSISTANT
        assert len(resp.content) >= 1
        assert isinstance(resp.content[0], TextContent)
        assert "TCP" in resp.content[0].text
        assert "UDP" in resp.content[0].text

    def test_usage(self, result) -> None:
        assert result.usage.input_tokens == 34
        assert result.usage.output_tokens == 187
        assert result.usage.total_tokens == 221

    def test_duration(self, result) -> None:
        assert result.duration_ms == 1842.0

    def test_api_endpoint(self, result) -> None:
        assert result.api_endpoint == "https://api.openai.com/v1/chat/completions"


# ---------------------------------------------------------------------------
# Streaming chat completion
# ---------------------------------------------------------------------------


class TestParseChatCompletionStreaming:
    @pytest.fixture
    def fixture(self) -> dict:
        return load_fixture("openai", "chat_completion_streaming")

    @pytest.fixture
    def result(self, plugin: OpenAICompletionsPlugin, fixture: dict):
        raw = _raw_from_fixture(fixture, is_streaming=True)
        return plugin.parse(raw, duration_ms=95.0, ttft_ms=15.0)

    def test_is_streaming(self, result) -> None:
        assert result.is_streaming is True

    def test_model(self, result) -> None:
        assert result.model == "gpt-4o"

    def test_system_prompt(self, result) -> None:
        assert result.system_prompt == "You are a helpful assistant that provides concise, well-structured answers."

    def test_sse_reassembly_produces_text(self, result) -> None:
        assert len(result.response_messages) == 1
        resp = result.response_messages[0]
        assert resp.role == MessageRole.ASSISTANT
        assert len(resp.content) >= 1
        assert isinstance(resp.content[0], TextContent)
        text = resp.content[0].text
        assert "Paris" in text

    def test_reassembled_text_content(self, result) -> None:
        text = result.response_messages[0].content[0].text
        expected = "The capital of France is **Paris**. It is the largest city in the country and a major European center for art, culture, and commerce."
        assert text == expected

    def test_stop_reason(self, result) -> None:
        assert result.stop_reason == StopReason.END_TURN

    def test_usage_from_stream(self, result) -> None:
        assert result.usage.input_tokens == 30
        assert result.usage.output_tokens == 32
        assert result.usage.total_tokens == 62

    def test_timing(self, result) -> None:
        assert result.duration_ms == 95.0
        assert result.time_to_first_token_ms == 15.0


# ---------------------------------------------------------------------------
# Tool-use chat completion
# ---------------------------------------------------------------------------


class TestParseChatCompletionTools:
    @pytest.fixture
    def fixture(self) -> dict:
        return load_fixture("openai", "chat_completion_tools")

    @pytest.fixture
    def result(self, plugin: OpenAICompletionsPlugin, fixture: dict):
        raw = _raw_from_fixture(fixture)
        return plugin.parse(raw)

    def test_tool_definitions(self, result) -> None:
        assert len(result.tools) == 1
        tool = result.tools[0]
        assert tool.name == "get_weather"
        assert "weather" in tool.description.lower()
        assert "properties" in tool.input_schema
        assert tool.is_mcp is False
        assert tool.mcp_server_name is None

    def test_tool_choice(self, result) -> None:
        assert result.tool_choice == "auto"

    def test_messages_include_tool_call(self, result) -> None:
        # Messages: user, assistant (with tool_call), tool (result)
        assert len(result.messages) == 3

        # First message is user
        assert result.messages[0].role == MessageRole.USER

        # Second message is assistant with tool use
        assistant_msg = result.messages[1]
        assert assistant_msg.role == MessageRole.ASSISTANT
        tool_use_blocks = [b for b in assistant_msg.content if isinstance(b, ToolUseContent)]
        assert len(tool_use_blocks) == 1
        assert tool_use_blocks[0].tool_name == "get_weather"
        assert tool_use_blocks[0].tool_call_id == "call_vp3J8k2Lm9Nq1Rs4Tu6Wxy"
        assert tool_use_blocks[0].tool_input["location"] == "San Francisco, CA"

        # Third message is tool result
        tool_msg = result.messages[2]
        assert tool_msg.role == MessageRole.TOOL
        assert len(tool_msg.content) == 1
        assert isinstance(tool_msg.content[0], ToolResultContent)
        assert tool_msg.content[0].tool_call_id == "call_vp3J8k2Lm9Nq1Rs4Tu6Wxy"
        assert "62" in tool_msg.content[0].content

    def test_response_has_text(self, result) -> None:
        assert len(result.response_messages) == 1
        resp = result.response_messages[0]
        assert resp.role == MessageRole.ASSISTANT
        text_blocks = [b for b in resp.content if isinstance(b, TextContent)]
        assert len(text_blocks) == 1
        assert "62" in text_blocks[0].text

    def test_usage(self, result) -> None:
        assert result.usage.input_tokens == 152
        assert result.usage.output_tokens == 78
        assert result.usage.total_tokens == 230

    def test_stop_reason(self, result) -> None:
        assert result.stop_reason == StopReason.END_TURN


# ---------------------------------------------------------------------------
# MCP detection
# ---------------------------------------------------------------------------


class TestMCPDetection:
    def test_mcp_tool_detected(self, plugin: OpenAICompletionsPlugin) -> None:
        fixture = {
            "request_url": "https://api.openai.com/v1/chat/completions",
            "request_body": {
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Read the file."}],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "mcp__filesystem__read_file",
                            "description": "Read a file from the filesystem.",
                            "parameters": {
                                "type": "object",
                                "properties": {"path": {"type": "string"}},
                            },
                        },
                    }
                ],
            },
            "response_status": 200,
            "response_body": {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1740268800,
                "model": "gpt-4o-2024-08-06",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "I'll read that file for you.",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                    "total_tokens": 30,
                },
            },
        }
        raw = _raw_from_fixture(fixture)
        result = plugin.parse(raw)

        assert len(result.tools) == 1
        tool = result.tools[0]
        assert tool.is_mcp is True
        assert tool.mcp_server_name == "filesystem"
        assert tool.name == "mcp__filesystem__read_file"

    def test_non_mcp_tool(self, plugin: OpenAICompletionsPlugin) -> None:
        fixture = {
            "request_url": "https://api.openai.com/v1/chat/completions",
            "request_body": {
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hi"}],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "description": "Get weather",
                            "parameters": {},
                        },
                    }
                ],
            },
            "response_status": 200,
            "response_body": {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1740268800,
                "model": "gpt-4o-2024-08-06",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Hello"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        }
        raw = _raw_from_fixture(fixture)
        result = plugin.parse(raw)
        assert result.tools[0].is_mcp is False
        assert result.tools[0].mcp_server_name is None


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------


class TestCostEstimation:
    def test_gpt4o_cost(self, plugin: OpenAICompletionsPlugin) -> None:
        """Verify cost for gpt-4o: 34 input, 187 output tokens."""
        fixture = load_fixture("openai", "chat_completion")
        raw = _raw_from_fixture(fixture)
        result = plugin.parse(raw)

        # gpt-4o: input=$2.50/1M, output=$10.00/1M
        expected_cost = (34 * 2.50 + 187 * 10.00) / 1_000_000
        assert result.usage.estimated_cost_usd is not None
        assert abs(result.usage.estimated_cost_usd - expected_cost) < 1e-10

    def test_gpt4o_streaming_cost(self, plugin: OpenAICompletionsPlugin) -> None:
        """Verify cost for gpt-4o streaming: 30 input, 32 output tokens."""
        fixture = load_fixture("openai", "chat_completion_streaming")
        raw = _raw_from_fixture(fixture, is_streaming=True)
        result = plugin.parse(raw)

        expected_cost = (30 * 2.50 + 32 * 10.00) / 1_000_000
        assert result.usage.estimated_cost_usd is not None
        assert abs(result.usage.estimated_cost_usd - expected_cost) < 1e-10

    def test_gpt4o_tools_cost(self, plugin: OpenAICompletionsPlugin) -> None:
        """Verify cost for gpt-4o tools: 152 input, 78 output tokens."""
        fixture = load_fixture("openai", "chat_completion_tools")
        raw = _raw_from_fixture(fixture)
        result = plugin.parse(raw)

        expected_cost = (152 * 2.50 + 78 * 10.00) / 1_000_000
        assert result.usage.estimated_cost_usd is not None
        assert abs(result.usage.estimated_cost_usd - expected_cost) < 1e-10

    def test_prefix_matching(self, plugin: OpenAICompletionsPlugin) -> None:
        """Model 'gpt-4o-2024-08-06' should match 'gpt-4o' pricing."""
        fixture = {
            "request_url": "https://api.openai.com/v1/chat/completions",
            "request_body": {
                "model": "gpt-4o-2024-08-06",
                "messages": [{"role": "user", "content": "Hi"}],
            },
            "response_status": 200,
            "response_body": {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1740268800,
                "model": "gpt-4o-2024-08-06",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Hello"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            },
        }
        raw = _raw_from_fixture(fixture)
        result = plugin.parse(raw)

        expected = (100 * 2.50 + 50 * 10.00) / 1_000_000
        assert result.usage.estimated_cost_usd is not None
        assert abs(result.usage.estimated_cost_usd - expected) < 1e-10

    def test_unknown_model_returns_none(self, plugin: OpenAICompletionsPlugin) -> None:
        """An unknown model should yield None for estimated cost."""
        fixture = {
            "request_url": "https://api.openai.com/v1/chat/completions",
            "request_body": {
                "model": "some-unknown-model",
                "messages": [{"role": "user", "content": "Hi"}],
            },
            "response_status": 200,
            "response_body": {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1740268800,
                "model": "some-unknown-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Hello"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        }
        raw = _raw_from_fixture(fixture)
        result = plugin.parse(raw)
        assert result.usage.estimated_cost_usd is None

    def test_gpt4o_mini_not_confused_with_gpt4o(self, plugin: OpenAICompletionsPlugin) -> None:
        """gpt-4o-mini should match its own pricing, not gpt-4o."""
        fixture = {
            "request_url": "https://api.openai.com/v1/chat/completions",
            "request_body": {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Hi"}],
            },
            "response_status": 200,
            "response_body": {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1740268800,
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Hello"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            },
        }
        raw = _raw_from_fixture(fixture)
        result = plugin.parse(raw)

        # gpt-4o-mini: input=$0.15/1M, output=$0.60/1M
        expected = (100 * 0.15 + 50 * 0.60) / 1_000_000
        assert result.usage.estimated_cost_usd is not None
        assert abs(result.usage.estimated_cost_usd - expected) < 1e-10
