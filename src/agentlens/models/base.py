"""Core data models for the agent profiler."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .enums import (
    ContentBlockType,
    MessageRole,
    RequestStatus,
    StopReason,
)


def _uuid() -> str:
    return str(uuid4())


# --- Content Blocks (discriminated union) ---


class TextContent(BaseModel):
    type: Literal[ContentBlockType.TEXT] = ContentBlockType.TEXT
    text: str


class ImageContent(BaseModel):
    type: Literal[ContentBlockType.IMAGE] = ContentBlockType.IMAGE
    media_type: str = ""
    source_type: str = ""  # "base64", "url"
    has_data: bool = False


class ThinkingContent(BaseModel):
    type: Literal[ContentBlockType.THINKING] = ContentBlockType.THINKING
    thinking: str


class ToolUseContent(BaseModel):
    type: Literal[ContentBlockType.TOOL_USE] = ContentBlockType.TOOL_USE
    tool_call_id: str
    tool_name: str
    tool_input: dict[str, Any] = Field(default_factory=dict)


class ToolResultContent(BaseModel):
    type: Literal[ContentBlockType.TOOL_RESULT] = ContentBlockType.TOOL_RESULT
    tool_call_id: str
    content: str = ""
    is_error: bool = False


ContentBlock = Annotated[
    TextContent | ImageContent | ThinkingContent | ToolUseContent | ToolResultContent,
    Field(discriminator="type"),
]


# --- Message ---


class Message(BaseModel):
    role: MessageRole
    content: list[ContentBlock] = Field(default_factory=list)


# --- Tool Definition ---


class ToolDefinition(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    is_mcp: bool = False
    mcp_server_name: str | None = None


# --- Token Usage ---


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float | None = None


# --- LLM Request (central unit) ---


class LLMRequest(BaseModel):
    id: str = Field(default_factory=_uuid)
    session_id: str = ""
    raw_capture_id: str = ""
    capture_mode: str = "explicit_proxy"
    capture_label: str | None = None
    capture_metadata: dict[str, Any] = Field(default_factory=dict)

    # Timing
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: float | None = None
    time_to_first_token_ms: float | None = None

    # Provider
    provider: str = "unknown"
    model: str = ""
    api_endpoint: str = ""

    # Params
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    is_streaming: bool = False
    tool_choice: Any = None

    # Content
    system_prompt: list[str] | str | None = None
    messages: list[Message] = Field(default_factory=list)
    tools: list[ToolDefinition] = Field(default_factory=list)

    # Response
    response_messages: list[Message] = Field(default_factory=list)
    stop_reason: StopReason | None = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
    status: RequestStatus = RequestStatus.SUCCESS

    # Extras (provider-specific overflow)
    request_params: dict[str, Any] = Field(default_factory=dict)
    response_metadata: dict[str, Any] = Field(default_factory=dict)


# --- Session ---


class Session(BaseModel):
    id: str = Field(default_factory=_uuid)
    name: str = ""
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: datetime | None = None
    request_count: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


# --- Session Stats ---


class SessionStats(BaseModel):
    total_requests: int = 0
    total_tokens: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    avg_duration_ms: float | None = None
    avg_tokens_per_request: float | None = None
    models_used: list[str] = Field(default_factory=list)
    providers_used: list[str] = Field(default_factory=list)
