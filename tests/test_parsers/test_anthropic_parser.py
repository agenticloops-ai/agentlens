"""Tests for the Anthropic Messages API parser."""

from tests.conftest import load_fixture

from agentlens.models import (
    LLMRequest,
    RawCapture,
    TextContent,
    ThinkingContent,
    ToolUseContent,
)
from agentlens.models.enums import (
    MessageRole,
    StopReason,
)
from agentlens.providers.anthropic import AnthropicPlugin
from agentlens.models.base import TokenUsage


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
    """Tests for AnthropicPlugin.can_parse."""

    def test_recognizes_anthropic_url(self):
        plugin = AnthropicPlugin()
        raw = RawCapture(request_url="https://api.anthropic.com/v1/messages")
        assert plugin.can_parse(raw) is True

    def test_recognizes_anthropic_api_key_header(self):
        plugin = AnthropicPlugin()
        raw = RawCapture(
            request_url="https://custom-proxy.example.com/v1/messages",
            request_headers={"x-api-key": "sk-ant-api03-xxxxxxxxxxxx"},
        )
        assert plugin.can_parse(raw) is True

    def test_rejects_non_anthropic(self):
        plugin = AnthropicPlugin()
        raw = RawCapture(
            request_url="https://api.openai.com/v1/chat/completions",
            request_headers={"Authorization": "Bearer sk-xxx"},
        )
        assert plugin.can_parse(raw) is False

    def test_rejects_empty_capture(self):
        plugin = AnthropicPlugin()
        raw = RawCapture()
        assert plugin.can_parse(raw) is False


class TestParseMessages:
    """Tests for parsing the non-streaming messages fixture."""

    def setup_method(self):
        self.fixture = load_fixture("anthropic", "messages")
        self.raw = _raw_from_fixture(self.fixture)
        self.plugin = AnthropicPlugin()
        self.result: LLMRequest = self.plugin.parse(self.raw)

    def test_provider(self):
        assert self.result.provider == "anthropic"

    def test_model(self):
        assert self.result.model == "claude-sonnet-4-20250514"

    def test_system_prompt(self):
        assert self.result.system_prompt is not None
        assert "expert software engineer" in self.result.system_prompt

    def test_request_messages(self):
        assert len(self.result.messages) == 1
        msg = self.result.messages[0]
        assert msg.role == MessageRole.USER
        assert len(msg.content) == 1
        assert isinstance(msg.content[0], TextContent)
        assert "context manager" in msg.content[0].text

    def test_response_messages(self):
        assert len(self.result.response_messages) == 1
        resp = self.result.response_messages[0]
        assert resp.role == MessageRole.ASSISTANT
        assert len(resp.content) == 1
        assert isinstance(resp.content[0], TextContent)
        assert "context manager" in resp.content[0].text.lower()

    def test_stop_reason(self):
        assert self.result.stop_reason == StopReason.END_TURN

    def test_usage(self):
        assert self.result.usage.input_tokens == 38
        assert self.result.usage.output_tokens == 296
        assert self.result.usage.total_tokens == 38 + 296

    def test_temperature(self):
        assert self.result.temperature == 0.7

    def test_max_tokens(self):
        assert self.result.max_tokens == 1024

    def test_not_streaming(self):
        assert self.result.is_streaming is False

    def test_api_endpoint(self):
        assert self.result.api_endpoint == "https://api.anthropic.com/v1/messages"


class TestParseMessagesStreaming:
    """Tests for parsing the streaming messages fixture via SSE reassembly."""

    def setup_method(self):
        self.fixture = load_fixture("anthropic", "messages_streaming")
        self.raw = _raw_from_fixture(self.fixture, streaming=True)
        self.plugin = AnthropicPlugin()
        self.result: LLMRequest = self.plugin.parse(self.raw)

    def test_is_streaming(self):
        assert self.result.is_streaming is True

    def test_model(self):
        assert self.result.model == "claude-sonnet-4-20250514"

    def test_system_prompt(self):
        assert self.result.system_prompt == "You are a helpful assistant."

    def test_response_reassembled(self):
        """Verify SSE text deltas are concatenated into a single text block."""
        assert len(self.result.response_messages) == 1
        resp = self.result.response_messages[0]
        assert resp.role == MessageRole.ASSISTANT
        assert len(resp.content) == 1
        assert isinstance(resp.content[0], TextContent)
        text = resp.content[0].text
        assert "Rust's" in text
        assert "ownership" in text
        assert "compile time." in text

    def test_stop_reason(self):
        assert self.result.stop_reason == StopReason.END_TURN

    def test_usage(self):
        assert self.result.usage.input_tokens == 24
        assert self.result.usage.output_tokens == 89
        assert self.result.usage.total_tokens == 24 + 89

    def test_request_messages(self):
        assert len(self.result.messages) == 1
        msg = self.result.messages[0]
        assert msg.role == MessageRole.USER
        assert "Rust ownership model" in msg.content[0].text


class TestParseMessagesToolUse:
    """Tests for parsing the tool_use fixture."""

    def setup_method(self):
        self.fixture = load_fixture("anthropic", "messages_tool_use")
        self.raw = _raw_from_fixture(self.fixture)
        self.plugin = AnthropicPlugin()
        self.result: LLMRequest = self.plugin.parse(self.raw)

    def test_tool_definitions(self):
        assert len(self.result.tools) == 2
        names = {t.name for t in self.result.tools}
        assert "get_stock_price" in names
        assert "get_company_info" in names

    def test_tool_definitions_not_mcp(self):
        for tool in self.result.tools:
            assert tool.is_mcp is False
            assert tool.mcp_server_name is None

    def test_tool_input_schema(self):
        stock_tool = next(t for t in self.result.tools if t.name == "get_stock_price")
        assert stock_tool.input_schema["type"] == "object"
        assert "symbol" in stock_tool.input_schema["properties"]

    def test_tool_choice(self):
        assert self.result.tool_choice == {"type": "auto"}

    def test_response_has_tool_use_block(self):
        resp = self.result.response_messages[0]
        tool_blocks = [b for b in resp.content if isinstance(b, ToolUseContent)]
        assert len(tool_blocks) == 1
        tb = tool_blocks[0]
        assert tb.tool_name == "get_stock_price"
        assert tb.tool_input == {"symbol": "AAPL", "include_history": False}
        assert tb.tool_call_id == "toolu_01VwXyZaBcDeFgHiJkLmNo"

    def test_response_has_text_block(self):
        resp = self.result.response_messages[0]
        text_blocks = [b for b in resp.content if isinstance(b, TextContent)]
        assert len(text_blocks) == 1
        assert "AAPL" in text_blocks[0].text

    def test_stop_reason_tool_use(self):
        assert self.result.stop_reason == StopReason.TOOL_USE

    def test_usage(self):
        assert self.result.usage.input_tokens == 156
        assert self.result.usage.output_tokens == 72


class TestParseMessagesThinking:
    """Tests for parsing the thinking fixture."""

    def setup_method(self):
        self.fixture = load_fixture("anthropic", "messages_thinking")
        self.raw = _raw_from_fixture(self.fixture)
        self.plugin = AnthropicPlugin()
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
        assert self.result.model == "claude-sonnet-4-20250514"


class TestParseMessagesMCP:
    """Tests for parsing the MCP fixture with MCP tools."""

    def setup_method(self):
        self.fixture = load_fixture("anthropic", "messages_mcp")
        self.raw = _raw_from_fixture(self.fixture)
        self.plugin = AnthropicPlugin()
        self.result: LLMRequest = self.plugin.parse(self.raw)

    def test_mcp_tools_detected(self):
        mcp_tools = [t for t in self.result.tools if t.is_mcp]
        assert len(mcp_tools) > 0

    def test_all_tools_are_mcp(self):
        """All tools in this fixture use the mcp__ naming convention."""
        for tool in self.result.tools:
            assert tool.is_mcp is True

    def test_mcp_server_names(self):
        server_names = {t.mcp_server_name for t in self.result.tools}
        assert "filesystem" in server_names
        assert "github" in server_names

    def test_filesystem_tools(self):
        fs_tools = [t for t in self.result.tools if t.mcp_server_name == "filesystem"]
        names = {t.name for t in fs_tools}
        assert "mcp__filesystem__read_file" in names
        assert "mcp__filesystem__write_file" in names
        assert "mcp__filesystem__list_directory" in names

    def test_github_tools(self):
        gh_tools = [t for t in self.result.tools if t.mcp_server_name == "github"]
        names = {t.name for t in gh_tools}
        assert "mcp__github__create_issue" in names
        assert "mcp__github__list_issues" in names

    def test_response_has_tool_use(self):
        resp = self.result.response_messages[0]
        tool_blocks = [b for b in resp.content if isinstance(b, ToolUseContent)]
        assert len(tool_blocks) == 1
        assert tool_blocks[0].tool_name == "mcp__filesystem__read_file"

    def test_stop_reason_tool_use(self):
        assert self.result.stop_reason == StopReason.TOOL_USE

    def test_system_prompt(self):
        assert self.result.system_prompt is not None
        assert "MCP" in self.result.system_prompt


class TestCostEstimation:
    """Tests for cost estimation logic."""

    def test_sonnet_4_cost(self):
        usage = TokenUsage(
            input_tokens=1000,
            output_tokens=500,
            cache_creation_input_tokens=200,
            cache_read_input_tokens=100,
            total_tokens=1500,
        )
        cost = AnthropicPlugin().estimate_cost("claude-sonnet-4-20250514", usage)
        assert cost is not None
        expected = (1000 * 3.00 + 500 * 15.00 + 200 * 3.75 + 100 * 0.30) / 1_000_000
        assert abs(cost - expected) < 1e-10

    def test_opus_cost(self):
        usage = TokenUsage(input_tokens=500, output_tokens=200, total_tokens=700)
        cost = AnthropicPlugin().estimate_cost("claude-opus-4-20250514", usage)
        assert cost is not None
        expected = (500 * 15.00 + 200 * 75.00) / 1_000_000
        assert abs(cost - expected) < 1e-10

    def test_haiku_cost(self):
        usage = TokenUsage(input_tokens=1000, output_tokens=1000, total_tokens=2000)
        cost = AnthropicPlugin().estimate_cost("claude-haiku-3.5-20250514", usage)
        assert cost is not None
        expected = (1000 * 0.80 + 1000 * 4.00) / 1_000_000
        assert abs(cost - expected) < 1e-10

    def test_unknown_model_returns_none(self):
        usage = TokenUsage(input_tokens=100, output_tokens=100, total_tokens=200)
        cost = AnthropicPlugin().estimate_cost("unknown-model-v1", usage)
        assert cost is None

    def test_prefix_matching(self):
        """Model names with date suffixes should match via prefix."""
        usage = TokenUsage(input_tokens=100, output_tokens=100, total_tokens=200)
        cost = AnthropicPlugin().estimate_cost("claude-3.5-sonnet-20241022", usage)
        assert cost is not None

    def test_cost_with_cache_tokens(self):
        """Verify cost calculation includes cache tokens correctly."""
        usage = TokenUsage(
            input_tokens=10000,
            output_tokens=5000,
            cache_creation_input_tokens=50000,
            cache_read_input_tokens=20000,
            total_tokens=15000,
        )
        cost = AnthropicPlugin().estimate_cost("claude-sonnet-4-20250514", usage)
        assert cost is not None
        expected = (10000 * 3.00 + 5000 * 15.00 + 50000 * 3.75 + 20000 * 0.30) / 1_000_000
        assert abs(cost - expected) < 1e-10

    def test_messages_fixture_cost(self):
        """End-to-end: parse the messages fixture and verify cost is populated."""
        fixture = load_fixture("anthropic", "messages")
        raw = _raw_from_fixture(fixture)
        plugin = AnthropicPlugin()
        result = plugin.parse(raw)
        assert result.usage.estimated_cost_usd is not None
        expected = (38 * 3.00 + 296 * 15.00) / 1_000_000
        assert abs(result.usage.estimated_cost_usd - expected) < 1e-10
