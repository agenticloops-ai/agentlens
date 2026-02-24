"""OpenAI Responses API plugin (used by Codex CLI and /v1/responses)."""

from __future__ import annotations

import json
from typing import Any

from agentlens.models import (
    LLMRequest,
    Message,
    RawCapture,
    StopReason,
    TextContent,
    ThinkingContent,
    TokenUsage,
    ToolDefinition,
    ToolResultContent,
    ToolUseContent,
)
from agentlens.models.enums import MessageRole

from .._base import EndpointPattern, ProviderMeta, ProviderPlugin
from .pricing import OPENAI_PRICING

STATUS_MAP: dict[str, StopReason] = {
    "completed": StopReason.END_TURN,
    "failed": StopReason.ERROR,
    "incomplete": StopReason.MAX_TOKENS,
    "cancelled": StopReason.UNKNOWN,
}


def _split_sse(body: str) -> list[dict[str, Any]]:
    """Split an SSE response body into individual events."""
    events: list[dict[str, Any]] = []
    current: dict[str, Any] = {}

    for line in body.split("\n"):
        line = line.strip()
        if not line:
            if current:
                if "data" in current and current["data"] != "[DONE]":
                    try:
                        current["data"] = json.loads(current["data"])
                    except (json.JSONDecodeError, ValueError):
                        pass
                events.append(current)
                current = {}
            continue
        if line.startswith("event:"):
            current["event"] = line[6:].strip()
        elif line.startswith("data:"):
            data = line[5:].strip()
            if "data" in current:
                current["data"] += data
            else:
                current["data"] = data
        elif line.startswith(":"):
            continue

    if current:
        if "data" in current and current["data"] != "[DONE]":
            try:
                current["data"] = json.loads(current["data"])
            except (json.JSONDecodeError, ValueError):
                pass
        events.append(current)

    return events


def _extract_usage(u: dict[str, Any]) -> TokenUsage:
    """Extract token usage from a usage dict, supporting both field name conventions."""
    input_tokens = u.get("input_tokens", 0) or u.get("prompt_tokens", 0)
    output_tokens = u.get("output_tokens", 0) or u.get("completion_tokens", 0)
    total_tokens = u.get("total_tokens", 0)
    if not total_tokens:
        total_tokens = input_tokens + output_tokens
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _convert_input(raw_input: Any) -> tuple[str | None, list[Message]]:
    """Convert Responses API ``input`` field to (system_prompt, messages).

    ``input`` can be a plain string, a list of message dicts, or omitted.
    """
    if raw_input is None:
        return None, []

    if isinstance(raw_input, str):
        return None, [Message(role=MessageRole.USER, content=[TextContent(text=raw_input)])]

    if not isinstance(raw_input, list):
        return None, []

    system_prompt: str | None = None
    messages: list[Message] = []

    for item in raw_input:
        if not isinstance(item, dict):
            continue

        role = item.get("role", "")
        item_type = item.get("type", "")

        if role == "system" or item_type == "system":
            system_prompt = item.get("content", "") or item.get("text", "")
            continue

        if role == "user" or item_type == "message" and item.get("role") == "user":
            content = item.get("content", "")
            if isinstance(content, str):
                messages.append(Message(role=MessageRole.USER, content=[TextContent(text=content)]))
            elif isinstance(content, list):
                blocks: list[Any] = []
                for part in content:
                    if isinstance(part, str):
                        blocks.append(TextContent(text=part))
                    elif isinstance(part, dict) and part.get("type") == "input_text":
                        blocks.append(TextContent(text=part.get("text", "")))
                if blocks:
                    messages.append(Message(role=MessageRole.USER, content=blocks))

        elif role == "assistant":
            blocks = []
            content = item.get("content", "")
            if isinstance(content, str) and content:
                blocks.append(TextContent(text=content))
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "output_text":
                            blocks.append(TextContent(text=part.get("text", "")))
                        elif part.get("type") == "refusal":
                            blocks.append(TextContent(text=part.get("refusal", "")))
            messages.append(Message(role=MessageRole.ASSISTANT, content=blocks))

        elif item_type == "function_call_output":
            messages.append(
                Message(
                    role=MessageRole.TOOL,
                    content=[
                        ToolResultContent(
                            tool_call_id=item.get("call_id", ""),
                            content=item.get("output", ""),
                        )
                    ],
                )
            )

    return system_prompt, messages


def _convert_tools(raw_tools: list[dict[str, Any]]) -> list[ToolDefinition]:
    tools: list[ToolDefinition] = []
    for tool in raw_tools:
        tool_type = tool.get("type", "")
        if tool_type == "function":
            name = tool.get("name", "")
            is_mcp = name.startswith("mcp__")
            mcp_server = name.split("__")[1] if is_mcp and len(name.split("__")) >= 3 else None
            tools.append(
                ToolDefinition(
                    name=name,
                    description=tool.get("description", ""),
                    input_schema=tool.get("parameters", {}),
                    is_mcp=is_mcp,
                    mcp_server_name=mcp_server,
                )
            )
    return tools


def _parse_output(output: list[dict[str, Any]]) -> tuple[list[Message], StopReason | None]:
    """Parse the ``output`` array from a non-streaming response."""
    messages: list[Message] = []
    for item in output:
        item_type = item.get("type", "")

        if item_type == "message":
            blocks: list[Any] = []
            for part in item.get("content", []):
                pt = part.get("type", "")
                if pt == "output_text":
                    blocks.append(TextContent(text=part.get("text", "")))
                elif pt == "refusal":
                    blocks.append(TextContent(text=part.get("refusal", "")))
            messages.append(Message(role=MessageRole.ASSISTANT, content=blocks))

        elif item_type == "function_call":
            raw_args = item.get("arguments", "{}")
            try:
                tool_input = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except (json.JSONDecodeError, TypeError):
                tool_input = {"_raw": raw_args}
            messages.append(
                Message(
                    role=MessageRole.ASSISTANT,
                    content=[
                        ToolUseContent(
                            tool_call_id=item.get("call_id", item.get("id", "")),
                            tool_name=item.get("name", ""),
                            tool_input=tool_input,
                        )
                    ],
                )
            )

        elif item_type == "reasoning":
            summary_parts = item.get("summary", [])
            text = ""
            for s in summary_parts:
                if isinstance(s, dict):
                    text += s.get("text", "")
                elif isinstance(s, str):
                    text += s
            if text:
                messages.append(
                    Message(
                        role=MessageRole.ASSISTANT,
                        content=[ThinkingContent(thinking=text)],
                    )
                )

    stop = StopReason.END_TURN if messages else None
    return messages, stop


def _reassemble_streaming(sse_events: list[dict[str, Any]]) -> tuple[list[Message], StopReason | None, TokenUsage, str]:
    """Reassemble Responses API SSE events.

    Returns (response_messages, stop_reason, usage, model).
    """
    text_parts: dict[int, list[str]] = {}  # output_index -> text chunks
    tool_calls: dict[int, dict[str, Any]] = {}  # output_index -> tool call info
    reasoning_parts: dict[int, list[str]] = {}
    usage = TokenUsage()
    model = ""
    status = ""

    for event in sse_events:
        event_type = event.get("event", "")
        data = event.get("data", {})

        if isinstance(data, str):
            if data == "[DONE]":
                continue
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                continue

        if not isinstance(data, dict):
            continue

        if event_type == "response.created":
            model = data.get("model", model)

        elif event_type == "response.output_text.delta":
            idx = data.get("output_index", 0)
            text_parts.setdefault(idx, []).append(data.get("delta", ""))

        elif event_type == "response.function_call_arguments.delta":
            idx = data.get("output_index", 0)
            if idx not in tool_calls:
                tool_calls[idx] = {"name": "", "call_id": "", "arguments": ""}
            tool_calls[idx]["arguments"] += data.get("delta", "")

        elif event_type == "response.output_item.added":
            item = data.get("item", {})
            idx = data.get("output_index", 0)
            if item.get("type") == "function_call":
                tool_calls[idx] = {
                    "name": item.get("name", ""),
                    "call_id": item.get("call_id", item.get("id", "")),
                    "arguments": "",
                }

        elif event_type == "response.reasoning_summary_text.delta":
            idx = data.get("output_index", 0)
            reasoning_parts.setdefault(idx, []).append(data.get("delta", ""))

        elif event_type in ("response.completed", "response.done"):
            # Try both nestings: data.response.{usage,status} and data.{usage,status}
            resp = data.get("response", data) if isinstance(data.get("response"), dict) else data
            status = resp.get("status", "") or data.get("status", "")
            model = resp.get("model", model)
            u = resp.get("usage", {}) or data.get("usage", {})
            if u:
                usage = _extract_usage(u)

        elif event_type in ("response.usage", "usage"):
            # Dedicated usage event (some backends send usage separately)
            u = data.get("usage", data) if "usage" in data else data
            if isinstance(u, dict) and ("input_tokens" in u or "prompt_tokens" in u):
                usage = _extract_usage(u)

    # Also scan all events for usage data if we still have nothing
    if usage.total_tokens == 0:
        for event in reversed(sse_events):
            data = event.get("data", {})
            if isinstance(data, dict) and "usage" in data:
                u = data["usage"]
                if isinstance(u, dict) and ("input_tokens" in u or "prompt_tokens" in u):
                    usage = _extract_usage(u)
                    break

    # Build messages
    messages: list[Message] = []
    all_indices = sorted(set(list(text_parts.keys()) + list(tool_calls.keys()) + list(reasoning_parts.keys())))

    for idx in all_indices:
        if idx in reasoning_parts:
            text = "".join(reasoning_parts[idx])
            if text:
                messages.append(Message(role=MessageRole.ASSISTANT, content=[ThinkingContent(thinking=text)]))

        if idx in text_parts:
            text = "".join(text_parts[idx])
            if text:
                messages.append(Message(role=MessageRole.ASSISTANT, content=[TextContent(text=text)]))

        if idx in tool_calls:
            tc = tool_calls[idx]
            raw_args = tc.get("arguments", "{}")
            try:
                tool_input = json.loads(raw_args)
            except (json.JSONDecodeError, TypeError):
                tool_input = {"_raw": raw_args}
            messages.append(
                Message(
                    role=MessageRole.ASSISTANT,
                    content=[
                        ToolUseContent(
                            tool_call_id=tc.get("call_id", ""),
                            tool_name=tc.get("name", ""),
                            tool_input=tool_input,
                        )
                    ],
                )
            )

    stop_reason = STATUS_MAP.get(status, StopReason.UNKNOWN) if status else None
    return messages, stop_reason, usage, model


class OpenAIPlugin(ProviderPlugin):
    """Plugin for the OpenAI Responses API (/v1/responses, Codex CLI)."""

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(name="openai", display_name="OpenAI", color="#22c55e")

    @property
    def endpoints(self) -> list[EndpointPattern]:
        return [
            EndpointPattern("api.openai.com", "/v1/responses"),
            EndpointPattern("chatgpt.com", "/backend-api/codex/responses"),
        ]

    @property
    def pricing(self) -> dict[str, dict[str, float]]:
        return OPENAI_PRICING

    def can_parse(self, raw: RawCapture) -> bool:
        url = raw.request_url
        if "/backend-api/codex/responses" in url:
            return True
        if "/v1/responses" in url:
            return True
        return False

    def parse(self, raw: RawCapture, duration_ms: float | None = None, ttft_ms: float | None = None) -> LLMRequest:
        body = raw.request_body if isinstance(raw.request_body, dict) else {}

        model = body.get("model", "")
        instructions = body.get("instructions")
        temperature = body.get("temperature")
        max_tokens = body.get("max_output_tokens") or body.get("max_tokens")
        top_p = body.get("top_p")
        is_streaming = body.get("stream", False)
        tool_choice = body.get("tool_choice")

        # Convert input
        raw_input = body.get("input")
        input_system, messages = _convert_input(raw_input)
        system_prompt = instructions or input_system

        # Convert tools
        raw_tools = body.get("tools", [])
        tools = _convert_tools(raw_tools)

        # Parse response
        response_messages: list[Message] = []
        stop_reason: StopReason | None = None
        usage = TokenUsage()

        # Determine effective SSE events
        sse_events = raw.sse_events
        effective_streaming = is_streaming or raw.is_streaming

        if not sse_events and isinstance(raw.response_body, str) and raw.response_body.lstrip().startswith("event:"):
            sse_events = _split_sse(raw.response_body)
            effective_streaming = True

        if sse_events:
            response_messages, stop_reason, usage, stream_model = _reassemble_streaming(sse_events)
            if stream_model and not model:
                model = stream_model
        elif not effective_streaming:
            resp_body = raw.response_body if isinstance(raw.response_body, dict) else {}
            model = resp_body.get("model", model)
            output = resp_body.get("output", [])
            response_messages, stop_reason = _parse_output(output)

            status = resp_body.get("status", "")
            if status:
                stop_reason = STATUS_MAP.get(status, stop_reason)

            u = resp_body.get("usage", {})
            if u:
                usage = _extract_usage(u)

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
