"""Tests for SSE splitting in the AgentLensAddon."""

from agentlens.proxy.addon import AgentLensAddon


class TestSplitSSE:
    def test_split_basic(self):
        """Simple multi-event SSE body with data-only events."""
        body = (
            "data: {\"id\": \"1\"}\n"
            "\n"
            "data: {\"id\": \"2\"}\n"
            "\n"
        )
        events = AgentLensAddon._split_sse(body)
        assert len(events) == 2
        assert events[0]["data"] == {"id": "1"}
        assert events[1]["data"] == {"id": "2"}

    def test_split_openai_style(self):
        """OpenAI-style streaming: data-only events ending with [DONE]."""
        body = (
            "data: {\"choices\": [{\"delta\": {\"content\": \"Hello\"}}]}\n"
            "\n"
            "data: {\"choices\": [{\"delta\": {\"content\": \" world\"}}]}\n"
            "\n"
            "data: [DONE]\n"
            "\n"
        )
        events = AgentLensAddon._split_sse(body)
        assert len(events) == 3
        # First two events should have parsed JSON data
        assert events[0]["data"]["choices"][0]["delta"]["content"] == "Hello"
        assert events[1]["data"]["choices"][0]["delta"]["content"] == " world"
        # [DONE] should remain as string
        assert events[2]["data"] == "[DONE]"

    def test_split_anthropic_style(self):
        """Anthropic-style streaming: events with event: type prefix."""
        body = (
            "event: message_start\n"
            "data: {\"type\": \"message_start\", \"message\": {\"model\": \"claude-sonnet-4-20250514\"}}\n"
            "\n"
            "event: content_block_start\n"
            "data: {\"type\": \"content_block_start\", \"index\": 0, \"content_block\": {\"type\": \"text\", \"text\": \"\"}}\n"
            "\n"
            "event: content_block_delta\n"
            "data: {\"type\": \"content_block_delta\", \"index\": 0, \"delta\": {\"type\": \"text_delta\", \"text\": \"Hello\"}}\n"
            "\n"
            "event: message_stop\n"
            "data: {\"type\": \"message_stop\"}\n"
            "\n"
        )
        events = AgentLensAddon._split_sse(body)
        assert len(events) == 4
        assert events[0]["event"] == "message_start"
        assert events[0]["data"]["message"]["model"] == "claude-sonnet-4-20250514"
        assert events[1]["event"] == "content_block_start"
        assert events[2]["event"] == "content_block_delta"
        assert events[2]["data"]["delta"]["text"] == "Hello"
        assert events[3]["event"] == "message_stop"

    def test_split_empty(self):
        """Empty body returns empty list."""
        events = AgentLensAddon._split_sse("")
        assert events == []

    def test_split_json_parsing(self):
        """Verify JSON data fields are parsed into dicts/lists."""
        body = (
            "data: {\"key\": \"value\", \"nested\": {\"a\": 1}}\n"
            "\n"
        )
        events = AgentLensAddon._split_sse(body)
        assert len(events) == 1
        assert isinstance(events[0]["data"], dict)
        assert events[0]["data"]["key"] == "value"
        assert events[0]["data"]["nested"]["a"] == 1

    def test_split_non_json_data(self):
        """Non-JSON data should remain as a string."""
        body = (
            "data: plain text message\n"
            "\n"
        )
        events = AgentLensAddon._split_sse(body)
        assert len(events) == 1
        assert events[0]["data"] == "plain text message"

    def test_split_multiline_data(self):
        """Data spanning multiple 'data:' lines should be concatenated."""
        body = (
            "data: {\"part1\":\n"
            "data:  \"value1\"}\n"
            "\n"
        )
        events = AgentLensAddon._split_sse(body)
        assert len(events) == 1
        # The two data lines should be concatenated
        assert events[0]["data"] == {"part1": "value1"}

    def test_split_comments_ignored(self):
        """Lines starting with ':' are SSE comments and should be skipped."""
        body = (
            ": this is a comment\n"
            "data: {\"id\": \"1\"}\n"
            "\n"
        )
        events = AgentLensAddon._split_sse(body)
        assert len(events) == 1
        assert events[0]["data"] == {"id": "1"}

    def test_split_no_trailing_newline(self):
        """Handle last event if no trailing newline."""
        body = "data: {\"id\": \"last\"}"
        events = AgentLensAddon._split_sse(body)
        assert len(events) == 1
        assert events[0]["data"] == {"id": "last"}

    def test_split_done_not_parsed_as_json(self):
        """[DONE] sentinel should not be parsed as JSON."""
        body = (
            "data: [DONE]\n"
            "\n"
        )
        events = AgentLensAddon._split_sse(body)
        assert len(events) == 1
        assert events[0]["data"] == "[DONE]"
        assert isinstance(events[0]["data"], str)
