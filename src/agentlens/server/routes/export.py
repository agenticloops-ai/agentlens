"""Export routes for downloading session data in various formats."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from agentlens.models.base import LLMRequest, ThinkingContent
from agentlens.models.enums import ContentBlockType, MessageRole
from agentlens.storage.repositories import (
    RawCaptureRepository,
    RequestRepository,
    SessionRepository,
)

from ..dependencies import get_raw_capture_repo, get_request_repo, get_session_repo

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_filename(name: str) -> str:
    """Sanitize a session name for use in a filename."""
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name)
    return safe.strip() or "session"


def _format_duration(ms: float | None) -> str:
    if ms is None:
        return "--"
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms:.0f}ms"


def _system_prompt_text(prompt: list[str] | str | None) -> str:
    if prompt is None:
        return ""
    if isinstance(prompt, list):
        return "\n\n".join(prompt)
    return prompt


def _request_preview(req: LLMRequest) -> str:
    """First 200 chars of the first user message text."""
    for msg in req.messages:
        if msg.role == MessageRole.USER:
            for block in msg.content:
                if block.type == ContentBlockType.TEXT:
                    return block.text[:200]  # type: ignore[union-attr]
    return ""


def _has_thinking(req: LLMRequest) -> bool:
    for msg in (*req.messages, *req.response_messages):
        for block in msg.content:
            if isinstance(block, ThinkingContent):
                return True
    return False


# ---------------------------------------------------------------------------
# Export: JSON
# ---------------------------------------------------------------------------


async def _export_json(
    session_id: str,
    session_repo: SessionRepository,
    request_repo: RequestRepository,
    raw_capture_repo: RawCaptureRepository,
) -> Response:
    session = await session_repo.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    stats = await session_repo.get_stats(session_id)
    requests = await request_repo.list_by_session(session_id, limit=10_000)

    # Collect raw captures for all requests that have one.
    raw_captures = []
    for req in requests:
        if req.raw_capture_id:
            capture = await raw_capture_repo.get(req.raw_capture_id)
            if capture is not None:
                raw_captures.append(capture.model_dump(mode="json"))

    payload: dict[str, Any] = {
        "session": session.model_dump(mode="json"),
        "stats": stats.model_dump(mode="json"),
        "requests": [r.model_dump(mode="json") for r in requests],
        "raw_captures": raw_captures,
    }

    filename = _safe_filename(session.name) + ".json"
    content = json.dumps(payload, indent=2, default=str)

    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Export: Markdown
# ---------------------------------------------------------------------------


def _render_markdown(
    session: Any,
    stats: Any,
    requests: list[LLMRequest],
) -> str:
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
        f"**Tokens:** {stats.total_tokens:,} "
        f"(in: {stats.total_input_tokens:,} / out: {stats.total_output_tokens:,})  "
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
        duration = _format_duration(req.duration_ms)
        lines.append(
            f"## Request #{i} — {req.model} ({req.provider}) — {duration}"
        )
        lines.append("")

        # System prompt
        sys_text = _system_prompt_text(req.system_prompt)
        if sys_text:
            lines.append("### System Prompt")
            lines.append("")
            lines.append(sys_text)
            lines.append("")

        # Messages
        for msg in req.messages:
            role_label = msg.role.value.capitalize()
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

        # Response messages
        for msg in req.response_messages:
            lines.append("**Assistant:**")
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
                elif block.type == ContentBlockType.THINKING:
                    lines.append("> *Thinking:*")
                    for think_line in block.thinking.split("\n"):  # type: ignore[union-attr]
                        lines.append(f"> {think_line}")
                    lines.append("")

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


async def _export_markdown(
    session_id: str,
    session_repo: SessionRepository,
    request_repo: RequestRepository,
) -> Response:
    session = await session_repo.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    stats = await session_repo.get_stats(session_id)
    requests = await request_repo.list_by_session(session_id, limit=10_000)

    content = _render_markdown(session, stats, requests)
    filename = _safe_filename(session.name) + ".md"

    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Export: CSV
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


async def _export_csv(
    session_id: str,
    session_repo: SessionRepository,
    request_repo: RequestRepository,
) -> Response:
    session = await session_repo.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    requests = await request_repo.list_by_session(session_id, limit=10_000)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)

    for req in requests:
        writer.writerow([
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
            _has_thinking(req),
            _request_preview(req),
        ])

    filename = _safe_filename(session.name) + ".csv"

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

VALID_FORMATS = {"json", "markdown", "csv"}


@router.get("/sessions/{session_id}/export")
async def export_session(
    session_id: str,
    format: str = Query(..., description="Export format: json, markdown, or csv"),
    session_repo: SessionRepository = Depends(get_session_repo),
    request_repo: RequestRepository = Depends(get_request_repo),
    raw_capture_repo: RawCaptureRepository = Depends(get_raw_capture_repo),
) -> Response:
    """Export a session in the requested format."""
    if format not in VALID_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid format '{format}'. Must be one of: {', '.join(sorted(VALID_FORMATS))}",
        )

    if format == "json":
        return await _export_json(session_id, session_repo, request_repo, raw_capture_repo)
    elif format == "markdown":
        return await _export_markdown(session_id, session_repo, request_repo)
    else:
        return await _export_csv(session_id, session_repo, request_repo)
