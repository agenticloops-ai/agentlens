"""Anthropic Messages API plugin."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from agentlens.models import (
    ImageContent,
    LLMRequest,
    Message,
    RawCapture,
    TextContent,
    ThinkingContent,
    TokenUsage,
    ToolDefinition,
    ToolResultContent,
    ToolUseContent,
)
from agentlens.models.enums import (
    MessageRole,
    StopReason,
)

from .._base import EndpointPattern, ProviderMeta, ProviderPlugin
from .pricing import ANTHROPIC_PRICING

_STOP_REASON_MAP: dict[str, StopReason] = {
    "end_turn": StopReason.END_TURN,
    "max_tokens": StopReason.MAX_TOKENS,
    "tool_use": StopReason.TOOL_USE,
    "stop_sequence": StopReason.STOP_SEQUENCE,
}


def _parse_content_block_request(
    block: dict[str, Any], role: MessageRole
) -> TextContent | ImageContent | ThinkingContent | ToolUseContent | ToolResultContent | None:
    """Parse a single content block from a request message."""
    block_type = block.get("type", "")

    if block_type == "text":
        return TextContent(text=block.get("text", ""))

    if block_type == "image":
        source = block.get("source", {})
        return ImageContent(
            media_type=source.get("media_type", ""),
            source_type=source.get("type", ""),
            has_data=bool(source.get("data")),
        )

    if block_type == "tool_result":
        content_str = ""
        raw_content = block.get("content", "")
        if isinstance(raw_content, str):
            content_str = raw_content
        elif isinstance(raw_content, list):
            text_parts = [b.get("text", "") for b in raw_content if b.get("type") == "text"]
            content_str = "".join(text_parts)
        return ToolResultContent(
            tool_call_id=block.get("tool_use_id", ""),
            content=content_str,
            is_error=block.get("is_error", False),
        )

    if block_type == "tool_use":
        return ToolUseContent(
            tool_call_id=block.get("id", ""),
            tool_name=block.get("name", ""),
            tool_input=block.get("input", {}),
        )

    if block_type == "thinking":
        return ThinkingContent(thinking=block.get("thinking", ""))

    return None


def _parse_content_block_response(block: dict[str, Any]) -> TextContent | ThinkingContent | ToolUseContent | None:
    """Parse a single content block from an assistant response."""
    block_type = block.get("type", "")

    if block_type == "text":
        return TextContent(text=block.get("text", ""))

    if block_type == "tool_use":
        return ToolUseContent(
            tool_call_id=block.get("id", ""),
            tool_name=block.get("name", ""),
            tool_input=block.get("input", {}),
        )

    if block_type == "thinking":
        return ThinkingContent(thinking=block.get("thinking", ""))

    return None


def _parse_messages(raw_messages: list[dict[str, Any]]) -> list[Message]:
    """Convert raw Anthropic messages to generic Message objects."""
    messages: list[Message] = []
    for raw_msg in raw_messages:
        role_str = raw_msg.get("role", "user")
        role = MessageRole(role_str) if role_str in MessageRole.__members__.values() else MessageRole.USER

        raw_content = raw_msg.get("content", "")
        content_blocks = []

        if isinstance(raw_content, str):
            if raw_content:
                content_blocks.append(TextContent(text=raw_content))
        elif isinstance(raw_content, list):
            for block in raw_content:
                parsed = _parse_content_block_request(block, role)
                if parsed is not None:
                    content_blocks.append(parsed)

        messages.append(Message(role=role, content=content_blocks))
    return messages


def _parse_system_prompt(system: Any) -> list[str] | str | None:
    """Extract system prompt from the Anthropic system field.

    Can be a string or an array of content blocks.
    Returns a list[str] when there are multiple blocks, a single str
    when there is one, or None when empty.
    """
    if system is None:
        return None
    if isinstance(system, str):
        return system if system else None
    if isinstance(system, list):
        parts: list[str] = []
        for block in system:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    parts.append(text)
            elif isinstance(block, str) and block:
                parts.append(block)
        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]
        return parts
    return None


def _parse_tool_definitions(raw_tools: list[dict[str, Any]]) -> list[ToolDefinition]:
    """Parse tool definitions, detecting MCP tools."""
    tools: list[ToolDefinition] = []
    for raw_tool in raw_tools:
        name = raw_tool.get("name", "")
        is_mcp = False
        mcp_server_name: str | None = None

        if name.startswith("mcp__"):
            is_mcp = True
            parts = name.split("__")
            if len(parts) >= 2:
                mcp_server_name = parts[1]

        tools.append(
            ToolDefinition(
                name=name,
                description=raw_tool.get("description", ""),
                input_schema=raw_tool.get("input_schema", {}),
                is_mcp=is_mcp,
                mcp_server_name=mcp_server_name,
            )
        )
    return tools


def _reassemble_streaming(sse_events: list[dict[str, Any]]) -> dict[str, Any]:
    """Reassemble SSE events into a single response-like dict.

    Returns a dict with keys:
      - model: str
      - stop_reason: str | None
      - content: list[dict]  (reassembled content blocks)
      - usage: dict with input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens
    """
    model = ""
    stop_reason: str | None = None
    input_tokens = 0
    output_tokens = 0
    cache_creation_input_tokens = 0
    cache_read_input_tokens = 0

    blocks: dict[int, dict[str, Any]] = {}

    for sse in sse_events:
        event_type = sse.get("event", "")
        data_raw = sse.get("data", "{}")

        if isinstance(data_raw, str):
            try:
                data = json.loads(data_raw)
            except json.JSONDecodeError:
                continue
        else:
            data = data_raw

        if event_type == "message_start":
            msg = data.get("message", {})
            model = msg.get("model", model)
            msg_usage = msg.get("usage", {})
            input_tokens = msg_usage.get("input_tokens", input_tokens)
            cache_creation_input_tokens = msg_usage.get("cache_creation_input_tokens", cache_creation_input_tokens)
            cache_read_input_tokens = msg_usage.get("cache_read_input_tokens", cache_read_input_tokens)

        elif event_type == "content_block_start":
            index = data.get("index", 0)
            content_block = data.get("content_block", {})
            block_type = content_block.get("type", "text")
            blocks[index] = {"type": block_type, "text": "", "input_json": "", "thinking": ""}
            if block_type == "tool_use":
                blocks[index]["id"] = content_block.get("id", "")
                blocks[index]["name"] = content_block.get("name", "")

        elif event_type == "content_block_delta":
            index = data.get("index", 0)
            delta = data.get("delta", {})
            delta_type = delta.get("type", "")

            if index not in blocks:
                continue

            if delta_type == "text_delta":
                blocks[index]["text"] += delta.get("text", "")
            elif delta_type == "input_json_delta":
                blocks[index]["input_json"] += delta.get("partial_json", "")
            elif delta_type == "thinking_delta":
                blocks[index]["thinking"] += delta.get("thinking", "")

        elif event_type == "content_block_stop":
            pass

        elif event_type == "message_delta":
            delta = data.get("delta", {})
            stop_reason = delta.get("stop_reason", stop_reason)
            delta_usage = data.get("usage", {})
            output_tokens = delta_usage.get("output_tokens", output_tokens)

        elif event_type == "message_stop":
            pass

    content: list[dict[str, Any]] = []
    for index in sorted(blocks):
        b = blocks[index]
        block_type = b["type"]
        if block_type == "text":
            content.append({"type": "text", "text": b["text"]})
        elif block_type == "tool_use":
            tool_input = {}
            if b["input_json"]:
                try:
                    tool_input = json.loads(b["input_json"])
                except json.JSONDecodeError:
                    tool_input = {}
            content.append(
                {
                    "type": "tool_use",
                    "id": b.get("id", ""),
                    "name": b.get("name", ""),
                    "input": tool_input,
                }
            )
        elif block_type == "thinking":
            content.append({"type": "thinking", "thinking": b["thinking"]})

    return {
        "model": model,
        "stop_reason": stop_reason,
        "content": content,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_creation_input_tokens": cache_creation_input_tokens,
            "cache_read_input_tokens": cache_read_input_tokens,
        },
    }


class AnthropicPlugin(ProviderPlugin):
    """Plugin for the Anthropic Messages API."""

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(name="anthropic", display_name="Anthropic", color="#f97316")

    @property
    def endpoints(self) -> list[EndpointPattern]:
        return [
            EndpointPattern("api.anthropic.com", "/v1/messages"),
        ]

    @property
    def pricing(self) -> dict[str, dict[str, float]]:
        return ANTHROPIC_PRICING

    def can_parse(self, raw: RawCapture) -> bool:
        """Return True if this capture is from the Anthropic API."""
        parsed = urlparse(raw.request_url)
        path = parsed.path
        host = raw.request_headers.get("host", "") or (parsed.hostname or "")
        host = host.lower()
        if host.startswith("a-api.anthropic.com"):
            return False
        if "api.anthropic.com" in host and path == "/v1/messages":
            return True

        # Check for Anthropic API key header pattern
        api_key = raw.request_headers.get("x-api-key", "")
        if api_key.startswith("sk-ant-") and path == "/v1/messages":
            return True

        return False

    def parse(
        self,
        raw: RawCapture,
        duration_ms: float | None = None,
        ttft_ms: float | None = None,
    ) -> LLMRequest:
        """Parse an Anthropic Messages API raw capture into an LLMRequest."""
        request_body = raw.request_body if isinstance(raw.request_body, dict) else {}
        is_streaming = raw.is_streaming or request_body.get("stream", False)

        # --- Request side ---
        model = request_body.get("model", "")
        system_prompt = _parse_system_prompt(request_body.get("system"))
        messages = _parse_messages(request_body.get("messages", []))
        tools = _parse_tool_definitions(request_body.get("tools", []))
        temperature = request_body.get("temperature")
        max_tokens = request_body.get("max_tokens")
        top_p = request_body.get("top_p")
        tool_choice = request_body.get("tool_choice")

        # --- Response side ---
        if is_streaming and raw.sse_events:
            reassembled = _reassemble_streaming(raw.sse_events)
            resp_model = reassembled["model"] or model
            resp_content_blocks = reassembled["content"]
            stop_reason_str = reassembled.get("stop_reason")
            resp_usage = reassembled["usage"]
        else:
            response_body = raw.response_body if isinstance(raw.response_body, dict) else {}
            resp_model = response_body.get("model", model)
            resp_content_blocks = response_body.get("content", [])
            stop_reason_str = response_body.get("stop_reason")
            resp_usage = response_body.get("usage", {})

        model = resp_model or model

        response_content = []
        for block in resp_content_blocks:
            parsed = _parse_content_block_response(block)
            if parsed is not None:
                response_content.append(parsed)

        response_messages = []
        if response_content:
            response_messages.append(Message(role=MessageRole.ASSISTANT, content=response_content))

        stop_reason = _STOP_REASON_MAP.get(stop_reason_str, StopReason.UNKNOWN) if stop_reason_str else None

        input_tokens = resp_usage.get("input_tokens", 0)
        output_tokens = resp_usage.get("output_tokens", 0)
        cache_creation = resp_usage.get("cache_creation_input_tokens", 0)
        cache_read = resp_usage.get("cache_read_input_tokens", 0)

        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=cache_creation,
            cache_read_input_tokens=cache_read,
            total_tokens=input_tokens + output_tokens,
        )

        usage.estimated_cost_usd = self.estimate_cost(model, usage)

        return LLMRequest(
            raw_capture_id=raw.id,
            session_id=raw.session_id,
            capture_mode=raw.capture_mode,
            capture_label=raw.capture_label,
            capture_metadata=dict(raw.capture_metadata),
            timestamp=raw.timestamp,
            duration_ms=duration_ms,
            time_to_first_token_ms=ttft_ms,
            provider=self.meta.name,
            model=model,
            api_endpoint=raw.request_url,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            is_streaming=is_streaming,
            tool_choice=tool_choice,
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
            response_messages=response_messages,
            stop_reason=stop_reason,
            usage=usage,
        )
