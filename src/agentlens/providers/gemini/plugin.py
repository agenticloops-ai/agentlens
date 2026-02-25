"""Gemini (Google Generative Language) API plugin."""

from __future__ import annotations

import json
import re
from typing import Any

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
from .pricing import GEMINI_PRICING

_MODEL_RE = re.compile(r"/models/([^/:]+)")

_STOP_REASON_MAP: dict[str, StopReason] = {
    "STOP": StopReason.END_TURN,
    "MAX_TOKENS": StopReason.MAX_TOKENS,
    "SAFETY": StopReason.UNKNOWN,
    "RECITATION": StopReason.UNKNOWN,
    "MALFORMED_FUNCTION_CALL": StopReason.TOOL_USE,
}

_ROLE_MAP: dict[str, MessageRole] = {
    "user": MessageRole.USER,
    "model": MessageRole.ASSISTANT,
}


def _extract_model_from_url(url: str) -> str:
    """Extract model name from a Gemini API URL path."""
    m = _MODEL_RE.search(url)
    return m.group(1) if m else ""


def _parse_gemini_parts(
    parts: list[dict[str, Any]], for_response: bool = False
) -> list[TextContent | ImageContent | ThinkingContent | ToolUseContent | ToolResultContent]:
    """Convert Gemini ``parts[]`` to a list of content blocks."""
    blocks: list[Any] = []
    for part in parts:
        if part.get("thought") and "text" in part:
            blocks.append(ThinkingContent(thinking=part["text"]))
        elif "text" in part:
            blocks.append(TextContent(text=part["text"]))
        elif "functionCall" in part:
            fc = part["functionCall"]
            blocks.append(
                ToolUseContent(
                    tool_call_id=fc.get("name", ""),
                    tool_name=fc.get("name", ""),
                    tool_input=fc.get("args", {}),
                )
            )
        elif "functionResponse" in part:
            fr = part["functionResponse"]
            response = fr.get("response", {})
            content = json.dumps(response) if isinstance(response, dict) else str(response)
            blocks.append(
                ToolResultContent(
                    tool_call_id=fr.get("name", ""),
                    content=content,
                )
            )
        elif "inlineData" in part:
            data = part["inlineData"]
            blocks.append(
                ImageContent(
                    media_type=data.get("mimeType", ""),
                    source_type="base64",
                    has_data=bool(data.get("data")),
                )
            )
    return blocks


def _parse_gemini_messages(contents: list[dict[str, Any]]) -> list[Message]:
    """Convert Gemini ``contents[]`` to generic Message objects."""
    messages: list[Message] = []
    for content in contents:
        role_str = content.get("role", "user")
        role = _ROLE_MAP.get(role_str, MessageRole.USER)
        parts = content.get("parts", [])
        blocks = _parse_gemini_parts(parts, for_response=(role == MessageRole.ASSISTANT))
        if blocks:
            messages.append(Message(role=role, content=blocks))
    return messages


def _parse_system_prompt(system_instruction: dict[str, Any] | None) -> str | None:
    """Extract system prompt from ``systemInstruction.parts``."""
    if not system_instruction:
        return None
    parts = system_instruction.get("parts", [])
    texts = [p["text"] for p in parts if "text" in p]
    if not texts:
        return None
    return texts[0] if len(texts) == 1 else "\n".join(texts)


def _parse_tool_definitions(tools: list[dict[str, Any]]) -> list[ToolDefinition]:
    """Convert Gemini ``tools[].functionDeclarations`` to ToolDefinition list."""
    defs: list[ToolDefinition] = []
    for tool in tools:
        for decl in tool.get("functionDeclarations", []):
            name = decl.get("name", "")
            is_mcp = name.startswith("mcp__")
            mcp_server = name.split("__")[1] if is_mcp and len(name.split("__")) >= 3 else None
            defs.append(
                ToolDefinition(
                    name=name,
                    description=decl.get("description", ""),
                    input_schema=decl.get("parameters") or decl.get("parametersJsonSchema", {}),
                    is_mcp=is_mcp,
                    mcp_server_name=mcp_server,
                )
            )
    return defs


def _parse_tool_choice(tool_config: dict[str, Any] | None) -> Any:
    """Convert Gemini ``toolConfig.functionCallingConfig`` to a tool_choice value."""
    if not tool_config:
        return None
    fcc = tool_config.get("functionCallingConfig")
    if not fcc:
        return None
    mode = fcc.get("mode", "")
    mode_map = {
        "AUTO": "auto",
        "ANY": "required",
        "NONE": "none",
    }
    return mode_map.get(mode, mode.lower()) if mode else None


def _reassemble_streaming(sse_events: list[dict[str, Any]]) -> dict[str, Any]:
    """Reassemble Gemini SSE chunks into a single response dict.

    Each SSE ``data:`` line is a complete ``GenerateContentResponse`` JSON
    containing partial ``candidates[].content.parts``.  We concatenate text
    parts across chunks and take ``usageMetadata`` from the last chunk that
    has it.
    """
    text_chunks: list[str] = []
    thinking_chunks: list[str] = []
    non_text_parts: list[dict[str, Any]] = []
    finish_reason: str | None = None
    usage: dict[str, Any] = {}

    for sse in sse_events:
        data_raw = sse.get("data", "{}")
        if isinstance(data_raw, str):
            if data_raw == "[DONE]":
                continue
            try:
                data = json.loads(data_raw)
            except json.JSONDecodeError:
                continue
        else:
            data = data_raw

        if not isinstance(data, dict):
            continue

        # Cloud Code wraps the Gemini response under a "response" key.
        data = data.get("response", data) if "response" in data else data

        candidates = data.get("candidates", [])
        if candidates:
            candidate = candidates[0]
            content = candidate.get("content", {})
            for part in content.get("parts", []):
                if part.get("thought") and "text" in part:
                    thinking_chunks.append(part["text"])
                elif "text" in part and "functionCall" not in part:
                    text_chunks.append(part["text"])
                else:
                    non_text_parts.append(part)
            fr = candidate.get("finishReason")
            if fr:
                finish_reason = fr

        um = data.get("usageMetadata")
        if um:
            usage = um

    # Rebuild merged parts list
    merged_parts: list[dict[str, Any]] = []
    if thinking_chunks:
        merged_parts.append({"text": "".join(thinking_chunks), "thought": True})
    if text_chunks:
        merged_parts.append({"text": "".join(text_chunks)})
    merged_parts.extend(non_text_parts)

    return {
        "parts": merged_parts,
        "finishReason": finish_reason,
        "usageMetadata": usage,
    }


class GeminiPlugin(ProviderPlugin):
    """Plugin for the Google Gemini (Generative Language) API."""

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(name="google", display_name="Google", color="#4285f4")

    @property
    def endpoints(self) -> list[EndpointPattern]:
        return [
            EndpointPattern("generativelanguage.googleapis.com", ":generateContent"),
            EndpointPattern("generativelanguage.googleapis.com", ":streamGenerateContent"),
            EndpointPattern("cloudcode-pa.googleapis.com", ":generateContent"),
            EndpointPattern("cloudcode-pa.googleapis.com", ":streamGenerateContent"),
        ]

    @property
    def pricing(self) -> dict[str, dict[str, float]]:
        return GEMINI_PRICING

    def parse(
        self,
        raw: RawCapture,
        duration_ms: float | None = None,
        ttft_ms: float | None = None,
    ) -> LLMRequest:
        """Parse a Gemini API raw capture into an LLMRequest."""
        outer_body = raw.request_body if isinstance(raw.request_body, dict) else {}
        # Cloud Code wraps the Gemini payload under a "request" key.
        request_body = outer_body.get("request", outer_body) if "request" in outer_body else outer_body
        is_streaming = raw.is_streaming or ":streamGenerateContent" in raw.request_url

        # --- Request side ---
        model = _extract_model_from_url(raw.request_url) or outer_body.get("model", "")
        system_prompt = _parse_system_prompt(request_body.get("systemInstruction"))
        messages = _parse_gemini_messages(request_body.get("contents", []))
        tools = _parse_tool_definitions(request_body.get("tools", []))
        tool_choice = _parse_tool_choice(request_body.get("toolConfig"))

        gen_config = request_body.get("generationConfig", {})
        temperature = gen_config.get("temperature")
        max_tokens = gen_config.get("maxOutputTokens")
        top_p = gen_config.get("topP")

        # --- Response side ---
        if is_streaming and raw.sse_events:
            reassembled = _reassemble_streaming(raw.sse_events)
            resp_parts = reassembled["parts"]
            finish_reason_str = reassembled.get("finishReason")
            resp_usage = reassembled.get("usageMetadata", {})
        else:
            response_body = raw.response_body if isinstance(raw.response_body, dict) else {}
            # Cloud Code wraps the Gemini response under a "response" key.
            response_body = response_body.get("response", response_body) if "response" in response_body else response_body
            candidates = response_body.get("candidates", [])
            if candidates:
                candidate = candidates[0]
                resp_parts = candidate.get("content", {}).get("parts", [])
                finish_reason_str = candidate.get("finishReason")
            else:
                resp_parts = []
                finish_reason_str = None
            resp_usage = response_body.get("usageMetadata", {})

        response_content = _parse_gemini_parts(resp_parts, for_response=True)
        response_messages = []
        if response_content:
            response_messages.append(Message(role=MessageRole.ASSISTANT, content=response_content))

        stop_reason = _STOP_REASON_MAP.get(finish_reason_str, StopReason.UNKNOWN) if finish_reason_str else None

        input_tokens = resp_usage.get("promptTokenCount", 0)
        output_tokens = resp_usage.get("candidatesTokenCount", 0)
        cache_read = resp_usage.get("cachedContentTokenCount", 0)

        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read,
            total_tokens=input_tokens + output_tokens,
        )

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
            is_streaming=is_streaming,
            tool_choice=tool_choice,
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
            response_messages=response_messages,
            stop_reason=stop_reason,
            usage=usage,
        )
