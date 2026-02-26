"""Pure rendering functions for exporting session data.

These are used by both the HTTP export route and the CLI export commands.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from agentlens.models.base import LLMRequest, ThinkingContent
from agentlens.models.enums import ContentBlockType, MessageRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def safe_filename(name: str) -> str:
    """Sanitize a session name for use in a filename."""
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name)
    return safe.strip() or "session"


def format_duration(ms: float | None) -> str:
    if ms is None:
        return "--"
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms:.0f}ms"


def system_prompt_text(prompt: list[str] | str | None) -> str:
    if prompt is None:
        return ""
    if isinstance(prompt, list):
        return "\n\n".join(prompt)
    return prompt


def request_preview(req: LLMRequest) -> str:
    """First 200 chars of the first user message text."""
    for msg in req.messages:
        if msg.role == MessageRole.USER:
            for block in msg.content:
                if block.type == ContentBlockType.TEXT:
                    return block.text[:200]  # type: ignore[union-attr]
    return ""


def has_thinking(req: LLMRequest) -> bool:
    for msg in (*req.messages, *req.response_messages):
        for block in msg.content:
            if isinstance(block, ThinkingContent):
                return True
    return False


# ---------------------------------------------------------------------------
# Render: JSON
# ---------------------------------------------------------------------------


def render_json(
    session: Any,
    stats: Any,
    requests: list[LLMRequest],
    raw_captures: list[dict[str, Any]],
) -> str:
    """Render session data as a JSON string."""
    payload: dict[str, Any] = {
        "session": session.model_dump(mode="json"),
        "stats": stats.model_dump(mode="json"),
        "requests": [r.model_dump(mode="json") for r in requests],
        "raw_captures": raw_captures,
    }
    return json.dumps(payload, indent=2, default=str)


# ---------------------------------------------------------------------------
# Render: Markdown
# ---------------------------------------------------------------------------


def _render_messages(
    lines: list[str],
    messages: list[Any],
    default_role: str | None = None,
) -> None:
    """Render a list of messages into markdown lines."""
    for i, msg in enumerate(messages):
        if i > 0:
            lines.append("---")
            lines.append("")
        role_label = default_role or msg.role.value.capitalize()
        lines.append(f"**{role_label}:**")
        lines.append("")
        for block in msg.content:
            if block.type == ContentBlockType.TEXT:
                lines.append(block.text)  # type: ignore[union-attr]
                lines.append("")
            elif block.type == ContentBlockType.TOOL_USE:
                lines.append(f"```tool_call: {block.tool_name}")  # type: ignore[union-attr]
                lines.append(json.dumps(block.tool_input, indent=2))  # type: ignore[union-attr]
                lines.append("```")
                lines.append("")
            elif block.type == ContentBlockType.TOOL_RESULT:
                lines.append(f"> **Tool Result** (id: {block.tool_call_id})")  # type: ignore[union-attr]
                for result_line in (block.content or "").split("\n"):  # type: ignore[union-attr]
                    lines.append(f"> {result_line}")
                lines.append("")
            elif block.type == ContentBlockType.THINKING:
                lines.append("> *Thinking:*")
                for think_line in block.thinking.split("\n"):  # type: ignore[union-attr]
                    lines.append(f"> {think_line}")
                lines.append("")
            elif block.type == ContentBlockType.IMAGE:
                lines.append("*[Image content]*")
                lines.append("")


def render_markdown(
    session: Any,
    stats: Any,
    requests: list[LLMRequest],
) -> str:
    """Render session data as a Markdown document."""
    lines: list[str] = []

    # Header
    lines.append(f"# {session.name or 'Unnamed Session'}")
    lines.append("")

    started = session.started_at.isoformat() if session.started_at else "--"
    ended = session.ended_at.isoformat() if session.ended_at else "Active"
    lines.append(f"**Started:** {started}  ")
    lines.append(f"**Ended:** {ended}  ")
    lines.append(f"**Requests:** {stats.total_requests}  ")
    lines.append(
        f"**Tokens:** {stats.total_tokens:,} (in: {stats.total_input_tokens:,} / out: {stats.total_output_tokens:,})  "
    )
    if stats.estimated_cost_usd:
        lines.append(f"**Cost:** ${stats.estimated_cost_usd:.4f}  ")
    if stats.models_used:
        lines.append(f"**Models:** {', '.join(stats.models_used)}  ")
    if stats.providers_used:
        lines.append(f"**Providers:** {', '.join(stats.providers_used)}  ")
    lines.append("")
    lines.append("---")
    lines.append("")

    for i, req in enumerate(requests, 1):
        duration = format_duration(req.duration_ms)
        thinking_flag = " | thinking" if has_thinking(req) else ""
        lines.append(f"## Request #{i} — {req.model} ({req.provider}) — {duration}{thinking_flag}")
        lines.append("")

        # System prompt
        sys_text = system_prompt_text(req.system_prompt)
        if sys_text:
            lines.append("### System Prompt")
            lines.append("")
            lines.append(sys_text)
            lines.append("")

        # Tool definitions
        if req.tools:
            lines.append("### Tools")
            lines.append("")
            for tool in req.tools:
                mcp_tag = f" (MCP: {tool.mcp_server_name})" if tool.is_mcp and tool.mcp_server_name else ""
                lines.append(f"#### `{tool.name}`{mcp_tag}")
                lines.append("")
                if tool.description:
                    lines.append(tool.description)
                    lines.append("")
                if tool.input_schema:
                    props = tool.input_schema.get("properties", {})
                    required = set(tool.input_schema.get("required", []))
                    if props:
                        lines.append("| Parameter | Type | Required | Description |")
                        lines.append("|-----------|------|----------|-------------|")
                        for param_name, param_def in props.items():
                            param_type = param_def.get("type", "any")
                            param_desc = param_def.get("description", "")
                            req_mark = "yes" if param_name in required else "no"
                            lines.append(f"| `{param_name}` | {param_type} | {req_mark} | {param_desc} |")
                        lines.append("")
            lines.append("")

        # Messages
        _render_messages(lines, req.messages)

        # Response messages
        _render_messages(lines, req.response_messages, default_role="Assistant")

        # Token usage footer
        usage = req.usage
        cost = f"${usage.estimated_cost_usd:.4f}" if usage.estimated_cost_usd else "--"
        lines.append(
            f"*Tokens: {usage.input_tokens:,} in / {usage.output_tokens:,} out "
            f"({usage.total_tokens:,} total) — Cost: {cost}*"
        )
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Render: CSV
# ---------------------------------------------------------------------------

CSV_COLUMNS = [
    "timestamp",
    "provider",
    "model",
    "duration_ms",
    "ttft_ms",
    "status",
    "stop_reason",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cost_usd",
    "is_streaming",
    "has_tools",
    "has_thinking",
    "preview_text",
]


def render_csv(requests: list[LLMRequest]) -> str:
    """Render request data as CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)

    for req in requests:
        writer.writerow(
            [
                req.timestamp.isoformat(),
                str(req.provider),
                req.model,
                req.duration_ms,
                req.time_to_first_token_ms,
                str(req.status),
                str(req.stop_reason) if req.stop_reason else "",
                req.usage.input_tokens,
                req.usage.output_tokens,
                req.usage.total_tokens,
                req.usage.estimated_cost_usd or "",
                req.is_streaming,
                len(req.tools) > 0,
                has_thinking(req),
                request_preview(req),
            ]
        )

    return buf.getvalue()
