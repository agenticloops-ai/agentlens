"""OpenAI Chat Completions API plugin."""

from __future__ import annotations

import json
from typing import Any

from agentlens.models import (
    LLMRequest,
    Message,
    RawCapture,
    StopReason,
    TextContent,
    TokenUsage,
    ToolDefinition,
    ToolResultContent,
    ToolUseContent,
)
from agentlens.models.enums import MessageRole

from .._base import EndpointPattern, ProviderMeta, ProviderPlugin
from .pricing import OPENAI_PRICING

FINISH_REASON_MAP: dict[str, StopReason] = {
    "stop": StopReason.END_TURN,
    "length": StopReason.MAX_TOKENS,
    "tool_calls": StopReason.TOOL_USE,
    "content_filter": StopReason.STOP_SEQUENCE,
}


def _detect_mcp(tool_name: str) -> tuple[bool, str | None]:
    """Detect if a tool name follows the MCP pattern ``mcp__<server>__<name>``."""
    parts = tool_name.split("__")
    if len(parts) >= 3 and parts[0] == "mcp":
        return True, parts[1]
    return False, None


def _convert_messages(raw_messages: list[dict[str, Any]]) -> tuple[str | None, list[Message]]:
    """Convert OpenAI message dicts to generic Message objects.

    Returns (system_prompt, messages) where system messages are extracted
    into the system_prompt string.
    """
    system_prompt: str | None = None
    messages: list[Message] = []

    for msg in raw_messages:
        role = msg.get("role", "")

        if role == "system":
            content = msg.get("content", "")
            system_prompt = content if isinstance(content, str) else str(content)
            continue

        if role == "user":
            content = msg.get("content", "")
            text = content if isinstance(content, str) else str(content)
            messages.append(
                Message(
                    role=MessageRole.USER,
                    content=[TextContent(text=text)],
                )
            )

        elif role == "assistant":
            blocks: list[Any] = []
            text_content = msg.get("content")
            if text_content:
                blocks.append(TextContent(text=text_content))

            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                for tc in tool_calls:
                    func = tc.get("function", {})
                    raw_args = func.get("arguments", "{}")
                    try:
                        tool_input = json.loads(raw_args)
                    except (json.JSONDecodeError, TypeError):
                        tool_input = {"_raw": raw_args}

                    blocks.append(
                        ToolUseContent(
                            tool_call_id=tc.get("id", ""),
                            tool_name=func.get("name", ""),
                            tool_input=tool_input,
                        )
                    )

            messages.append(Message(role=MessageRole.ASSISTANT, content=blocks))

        elif role == "tool":
            tool_content = msg.get("content", "")
            messages.append(
                Message(
                    role=MessageRole.TOOL,
                    content=[
                        ToolResultContent(
                            tool_call_id=msg.get("tool_call_id", ""),
                            content=tool_content if isinstance(tool_content, str) else str(tool_content),
                        )
                    ],
                )
            )

    return system_prompt, messages


def _convert_tools(raw_tools: list[dict[str, Any]]) -> list[ToolDefinition]:
    """Convert OpenAI tool definitions to generic ToolDefinition objects."""
    tools: list[ToolDefinition] = []
    for tool in raw_tools:
        func = tool.get("function", {})
        name = func.get("name", "")
        is_mcp, mcp_server = _detect_mcp(name)
        tools.append(
            ToolDefinition(
                name=name,
                description=func.get("description", ""),
                input_schema=func.get("parameters", {}),
                is_mcp=is_mcp,
                mcp_server_name=mcp_server,
            )
        )
    return tools


def _parse_response_message(msg_data: dict[str, Any]) -> Message:
    """Parse an OpenAI response message dict into a generic Message."""
    blocks: list[Any] = []
    text_content = msg_data.get("content")
    if text_content:
        blocks.append(TextContent(text=text_content))

    tool_calls = msg_data.get("tool_calls", [])
    if tool_calls:
        for tc in tool_calls:
            func = tc.get("function", {})
            raw_args = func.get("arguments", "{}")
            try:
                tool_input = json.loads(raw_args)
            except (json.JSONDecodeError, TypeError):
                tool_input = {"_raw": raw_args}
            blocks.append(
                ToolUseContent(
                    tool_call_id=tc.get("id", ""),
                    tool_name=func.get("name", ""),
                    tool_input=tool_input,
                )
            )

    return Message(role=MessageRole.ASSISTANT, content=blocks)


def _reassemble_streaming(sse_events: list[dict[str, Any]]) -> tuple[Message, StopReason | None, TokenUsage]:
    """Reassemble SSE streaming events into a single response message.

    Returns (response_message, stop_reason, usage).
    """
    content_parts: list[str] = []
    tool_calls_by_index: dict[int, dict[str, Any]] = {}
    finish_reason: str | None = None
    usage = TokenUsage()

    for event in sse_events:
        data = event.get("data", "")

        if isinstance(data, str):
            if data == "[DONE]":
                continue
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                continue

        if not isinstance(data, dict):
            continue

        chunk = data

        # Extract usage from chunks that have it
        chunk_usage = chunk.get("usage")
        if chunk_usage:
            usage = TokenUsage(
                input_tokens=chunk_usage.get("prompt_tokens", 0),
                output_tokens=chunk_usage.get("completion_tokens", 0),
                total_tokens=chunk_usage.get("total_tokens", 0),
            )

        choices = chunk.get("choices", [])
        if not choices:
            continue

        choice = choices[0]
        delta = choice.get("delta", {})

        # Accumulate text content
        delta_content = delta.get("content")
        if delta_content is not None:
            content_parts.append(delta_content)

        # Accumulate tool calls by index
        delta_tool_calls = delta.get("tool_calls", [])
        for tc in delta_tool_calls:
            idx = tc.get("index", 0)
            if idx not in tool_calls_by_index:
                tool_calls_by_index[idx] = {
                    "id": tc.get("id", ""),
                    "function": {"name": "", "arguments": ""},
                }

            existing = tool_calls_by_index[idx]
            if tc.get("id"):
                existing["id"] = tc["id"]

            func = tc.get("function", {})
            if func.get("name"):
                existing["function"]["name"] = func["name"]
            if func.get("arguments"):
                existing["function"]["arguments"] += func["arguments"]

        # Get finish reason
        fr = choice.get("finish_reason")
        if fr:
            finish_reason = fr

    # Build response message
    blocks: list[Any] = []
    full_text = "".join(content_parts)
    if full_text:
        blocks.append(TextContent(text=full_text))

    for idx in sorted(tool_calls_by_index.keys()):
        tc = tool_calls_by_index[idx]
        func = tc.get("function", {})
        raw_args = func.get("arguments", "{}")
        try:
            tool_input = json.loads(raw_args)
        except (json.JSONDecodeError, TypeError):
            tool_input = {"_raw": raw_args}
        blocks.append(
            ToolUseContent(
                tool_call_id=tc.get("id", ""),
                tool_name=func.get("name", ""),
                tool_input=tool_input,
            )
        )

    message = Message(role=MessageRole.ASSISTANT, content=blocks)
    stop_reason = FINISH_REASON_MAP.get(finish_reason, StopReason.UNKNOWN) if finish_reason else None

    return message, stop_reason, usage


class OpenAICompletionsPlugin(ProviderPlugin):
    """Plugin for OpenAI Chat Completions API (/v1/chat/completions)."""

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(name="openai", display_name="OpenAI", color="#22c55e")

    @property
    def endpoints(self) -> list[EndpointPattern]:
        return [
            EndpointPattern("api.openai.com", "/v1/chat/completions"),
        ]

    @property
    def pricing(self) -> dict[str, dict[str, float]]:
        return OPENAI_PRICING

    def can_parse(self, raw: RawCapture) -> bool:
        """Return True if the request URL targets OpenAI's chat completions endpoint."""
        url = raw.request_url
        if "api.openai.com" in url:
            return True
        # Also match generic /v1/chat/completions path
        if "/v1/chat/completions" in url:
            return True
        return False

    def parse(self, raw: RawCapture, duration_ms: float | None = None, ttft_ms: float | None = None) -> LLMRequest:
        """Parse an OpenAI raw capture into a generic LLMRequest."""
        body = raw.request_body if isinstance(raw.request_body, dict) else {}

        # Extract model
        model = body.get("model", "")

        # Convert messages
        raw_messages = body.get("messages", [])
        system_prompt, messages = _convert_messages(raw_messages)

        # Convert tools
        raw_tools = body.get("tools", [])
        tools = _convert_tools(raw_tools)

        # Extract parameters
        temperature = body.get("temperature")
        max_tokens = body.get("max_tokens")
        top_p = body.get("top_p")
        is_streaming = body.get("stream", False)
        tool_choice = body.get("tool_choice")

        # Parse response
        response_messages: list[Message] = []
        stop_reason: StopReason | None = None
        usage = TokenUsage()

        if is_streaming or raw.is_streaming:
            # Reassemble from SSE events
            resp_msg, stop_reason, usage = _reassemble_streaming(raw.sse_events)
            response_messages = [resp_msg]
        else:
            # Non-streaming: parse response_body
            resp_body = raw.response_body if isinstance(raw.response_body, dict) else {}
            choices = resp_body.get("choices", [])
            if choices:
                choice = choices[0]
                msg_data = choice.get("message", {})
                response_messages = [_parse_response_message(msg_data)]

                fr = choice.get("finish_reason")
                stop_reason = FINISH_REASON_MAP.get(fr, StopReason.UNKNOWN) if fr else None

            resp_usage = resp_body.get("usage", {})
            if resp_usage:
                usage = TokenUsage(
                    input_tokens=resp_usage.get("prompt_tokens", 0),
                    output_tokens=resp_usage.get("completion_tokens", 0),
                    total_tokens=resp_usage.get("total_tokens", 0),
                )

        # Estimate cost
        usage.estimated_cost_usd = self.estimate_cost(model, usage)

        return LLMRequest(
            raw_capture_id=raw.id,
            session_id=raw.session_id,
            timestamp=raw.timestamp,
            duration_ms=duration_ms,
            time_to_first_token_ms=ttft_ms,
            provider=self.meta.name,
            model=model,
            api_endpoint=raw.request_url,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            is_streaming=is_streaming or raw.is_streaming,
            tool_choice=tool_choice,
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
            response_messages=response_messages,
            stop_reason=stop_reason,
            usage=usage,
        )
