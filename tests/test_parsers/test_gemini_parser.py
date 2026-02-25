"""Tests for the Gemini (Google Generative Language) API parser."""

from tests.conftest import load_fixture

from agentlens.models import (
    LLMRequest,
    RawCapture,
    TextContent,
    ThinkingContent,
    ToolUseContent,
)
from agentlens.models.base import TokenUsage
from agentlens.models.enums import (
    MessageRole,
    StopReason,
)
from agentlens.providers.gemini import GeminiPlugin
from agentlens.providers.gemini.plugin import _extract_model_from_url


def _raw_from_fixture(fixture: dict, streaming: bool = False) -> RawCapture:
    """Build a RawCapture from a fixture dict."""
    return RawCapture(
        request_url=fixture["request_url"],
        request_headers=fixture.get("request_headers", {}),
        request_body=fixture.get("request_body", {}),
        response_status=fixture.get("response_status", 200),
        response_headers=fixture.get("response_headers", {}),
        response_body=fixture.get("response_body", ""),
        is_streaming=streaming,
        sse_events=fixture.get("sse_events", []),
    )


class TestCanParse:
    """Tests for GeminiPlugin.can_parse."""

    def test_recognizes_generate_content_url(self):
        plugin = GeminiPlugin()
        raw = RawCapture(
            request_url="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
        )
        assert plugin.can_parse(raw) is True

    def test_recognizes_stream_generate_content_url(self):
        plugin = GeminiPlugin()
        raw = RawCapture(
            request_url="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:streamGenerateContent?alt=sse"
        )
        assert plugin.can_parse(raw) is True

    def test_rejects_non_gemini(self):
        plugin = GeminiPlugin()
        raw = RawCapture(
            request_url="https://api.openai.com/v1/chat/completions",
        )
        assert plugin.can_parse(raw) is False

    def test_rejects_empty_capture(self):
        plugin = GeminiPlugin()
        raw = RawCapture()
        assert plugin.can_parse(raw) is False


class TestModelExtraction:
    """Tests for extracting model name from URL."""

    def test_generate_content(self):
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
        assert _extract_model_from_url(url) == "gemini-2.5-flash"

    def test_stream_generate_content(self):
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:streamGenerateContent?alt=sse"
        assert _extract_model_from_url(url) == "gemini-2.5-pro"

    def test_v1_path(self):
        url = "https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent"
        assert _extract_model_from_url(url) == "gemini-1.5-flash"

    def test_no_model_in_url(self):
        url = "https://example.com/v1/generate"
        assert _extract_model_from_url(url) == ""


class TestParseGenerateContent:
    """Tests for parsing a non-streaming generateContent response."""

    def setup_method(self):
        self.fixture = load_fixture("gemini", "generate_content")
        self.raw = _raw_from_fixture(self.fixture)
        self.plugin = GeminiPlugin()
        self.result: LLMRequest = self.plugin.parse(self.raw)

    def test_provider(self):
        assert self.result.provider == "google"

    def test_model(self):
        assert self.result.model == "gemini-2.5-flash"

    def test_system_prompt(self):
        assert self.result.system_prompt is not None
        assert "helpful coding assistant" in self.result.system_prompt

    def test_request_messages(self):
        assert len(self.result.messages) == 1
        msg = self.result.messages[0]
        assert msg.role == MessageRole.USER
        assert len(msg.content) == 1
        assert isinstance(msg.content[0], TextContent)
        assert "decorator" in msg.content[0].text

    def test_response_messages(self):
        assert len(self.result.response_messages) == 1
        resp = self.result.response_messages[0]
        assert resp.role == MessageRole.ASSISTANT
        assert len(resp.content) == 1
        assert isinstance(resp.content[0], TextContent)
        assert "decorator" in resp.content[0].text.lower()

    def test_stop_reason(self):
        assert self.result.stop_reason == StopReason.END_TURN

    def test_usage(self):
        assert self.result.usage.input_tokens == 42
        assert self.result.usage.output_tokens == 210
        assert self.result.usage.total_tokens == 42 + 210

    def test_temperature(self):
        assert self.result.temperature == 0.7

    def test_max_tokens(self):
        assert self.result.max_tokens == 1024

    def test_top_p(self):
        assert self.result.top_p == 0.95

    def test_not_streaming(self):
        assert self.result.is_streaming is False

    def test_api_endpoint(self):
        assert "generateContent" in self.result.api_endpoint
        assert "generativelanguage.googleapis.com" in self.result.api_endpoint


class TestParseGenerateContentStreaming:
    """Tests for parsing a streaming SSE response via reassembly."""

    def setup_method(self):
        self.fixture = load_fixture("gemini", "generate_content_streaming")
        self.raw = _raw_from_fixture(self.fixture, streaming=True)
        self.plugin = GeminiPlugin()
        self.result: LLMRequest = self.plugin.parse(self.raw)

    def test_is_streaming(self):
        assert self.result.is_streaming is True

    def test_model(self):
        assert self.result.model == "gemini-2.5-flash"

    def test_system_prompt(self):
        assert self.result.system_prompt == "You are a helpful assistant."

    def test_response_reassembled(self):
        """Verify SSE text chunks are concatenated into a single text block."""
        assert len(self.result.response_messages) == 1
        resp = self.result.response_messages[0]
        assert resp.role == MessageRole.ASSISTANT
        assert len(resp.content) == 1
        assert isinstance(resp.content[0], TextContent)
        text = resp.content[0].text
        assert "Rust's" in text
        assert "ownership" in text
        assert "garbage collector" in text

    def test_stop_reason(self):
        assert self.result.stop_reason == StopReason.END_TURN

    def test_usage(self):
        assert self.result.usage.input_tokens == 28
        assert self.result.usage.output_tokens == 75
        assert self.result.usage.total_tokens == 28 + 75

    def test_request_messages(self):
        assert len(self.result.messages) == 1
        msg = self.result.messages[0]
        assert msg.role == MessageRole.USER
        assert "Rust" in msg.content[0].text


class TestParseGenerateContentToolUse:
    """Tests for parsing a function-calling response."""

    def setup_method(self):
        self.fixture = load_fixture("gemini", "generate_content_tool_use")
        self.raw = _raw_from_fixture(self.fixture)
        self.plugin = GeminiPlugin()
        self.result: LLMRequest = self.plugin.parse(self.raw)

    def test_tool_definitions(self):
        assert len(self.result.tools) == 2
        names = {t.name for t in self.result.tools}
        assert "get_weather" in names
        assert "get_forecast" in names

    def test_tool_input_schema(self):
        weather_tool = next(t for t in self.result.tools if t.name == "get_weather")
        assert weather_tool.input_schema["type"] == "object"
        assert "location" in weather_tool.input_schema["properties"]

    def test_tool_choice(self):
        assert self.result.tool_choice == "auto"

    def test_response_has_tool_use_block(self):
        resp = self.result.response_messages[0]
        tool_blocks = [b for b in resp.content if isinstance(b, ToolUseContent)]
        assert len(tool_blocks) == 1
        tb = tool_blocks[0]
        assert tb.tool_name == "get_weather"
        assert tb.tool_input == {"location": "San Francisco, CA", "unit": "fahrenheit"}

    def test_response_has_text_block(self):
        resp = self.result.response_messages[0]
        text_blocks = [b for b in resp.content if isinstance(b, TextContent)]
        assert len(text_blocks) == 1
        assert "San Francisco" in text_blocks[0].text

    def test_stop_reason(self):
        assert self.result.stop_reason == StopReason.END_TURN

    def test_usage(self):
        assert self.result.usage.input_tokens == 98
        assert self.result.usage.output_tokens == 45


class TestParseGenerateContentThinking:
    """Tests for parsing a thinking model response."""

    def setup_method(self):
        self.fixture = load_fixture("gemini", "generate_content_thinking")
        self.raw = _raw_from_fixture(self.fixture)
        self.plugin = GeminiPlugin()
        self.result: LLMRequest = self.plugin.parse(self.raw)

    def test_thinking_block_exists(self):
        resp = self.result.response_messages[0]
        thinking_blocks = [b for b in resp.content if isinstance(b, ThinkingContent)]
        assert len(thinking_blocks) == 1

    def test_thinking_content(self):
        resp = self.result.response_messages[0]
        thinking = next(b for b in resp.content if isinstance(b, ThinkingContent))
        assert "strawberry" in thinking.thinking
        assert "3" in thinking.thinking

    def test_text_response_also_present(self):
        resp = self.result.response_messages[0]
        text_blocks = [b for b in resp.content if isinstance(b, TextContent)]
        assert len(text_blocks) == 1
        assert "3" in text_blocks[0].text

    def test_stop_reason(self):
        assert self.result.stop_reason == StopReason.END_TURN

    def test_model(self):
        assert self.result.model == "gemini-2.5-flash"


class TestCostEstimation:
    """Tests for cost estimation logic."""

    def test_flash_25_cost(self):
        usage = TokenUsage(
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
        )
        cost = GeminiPlugin().estimate_cost("gemini-2.5-flash", usage)
        assert cost is not None
        expected = (1000 * 0.15 + 500 * 0.60) / 1_000_000
        assert abs(cost - expected) < 1e-10

    def test_pro_25_cost(self):
        usage = TokenUsage(input_tokens=500, output_tokens=200, total_tokens=700)
        cost = GeminiPlugin().estimate_cost("gemini-2.5-pro", usage)
        assert cost is not None
        expected = (500 * 1.25 + 200 * 10.00) / 1_000_000
        assert abs(cost - expected) < 1e-10

    def test_flash_20_cost(self):
        usage = TokenUsage(input_tokens=1000, output_tokens=1000, total_tokens=2000)
        cost = GeminiPlugin().estimate_cost("gemini-2.0-flash", usage)
        assert cost is not None
        expected = (1000 * 0.10 + 1000 * 0.40) / 1_000_000
        assert abs(cost - expected) < 1e-10

    def test_unknown_model_returns_none(self):
        usage = TokenUsage(input_tokens=100, output_tokens=100, total_tokens=200)
        cost = GeminiPlugin().estimate_cost("unknown-model-v1", usage)
        assert cost is None

    def test_prefix_matching(self):
        """Model names with date suffixes should match via prefix."""
        usage = TokenUsage(input_tokens=100, output_tokens=100, total_tokens=200)
        cost = GeminiPlugin().estimate_cost("gemini-2.5-flash-preview-05-20", usage)
        assert cost is not None

    def test_cost_with_cache_tokens(self):
        usage = TokenUsage(
            input_tokens=10000,
            output_tokens=5000,
            cache_read_input_tokens=20000,
            total_tokens=15000,
        )
        cost = GeminiPlugin().estimate_cost("gemini-2.5-flash", usage)
        assert cost is not None
        expected = (10000 * 0.15 + 5000 * 0.60 + 20000 * 0.03) / 1_000_000
        assert abs(cost - expected) < 1e-10

    def test_fixture_cost(self):
        """End-to-end: parse the fixture and verify cost is populated."""
        fixture = load_fixture("gemini", "generate_content")
        raw = _raw_from_fixture(fixture)
        plugin = GeminiPlugin()
        result = plugin.parse(raw)
        assert result.usage.estimated_cost_usd is not None
        expected = (42 * 0.15 + 210 * 0.60) / 1_000_000
        assert abs(result.usage.estimated_cost_usd - expected) < 1e-10
