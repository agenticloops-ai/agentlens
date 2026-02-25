"""Request routes for the AgentLens API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from agentlens.models.base import LLMRequest, ThinkingContent
from agentlens.models.enums import ContentBlockType, MessageRole
from agentlens.storage.repositories import (
    RawCaptureRepository,
    RequestRepository,
)

from ..dependencies import get_raw_capture_repo, get_request_repo

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _request_summary(req: LLMRequest) -> dict[str, Any]:
    """Build a lightweight summary dict from an ``LLMRequest``."""
    # Preview text: first 200 chars of the first user message text content.
    preview_text = ""
    for msg in req.messages:
        if msg.role == MessageRole.USER:
            for block in msg.content:
                if block.type == ContentBlockType.TEXT:
                    preview_text = block.text[:200]  # type: ignore[union-attr]
                    break
            if preview_text:
                break

    # has_thinking: any ThinkingContent in messages or response_messages.
    has_thinking = False
    for msg in (*req.messages, *req.response_messages):
        for block in msg.content:
            if isinstance(block, ThinkingContent):
                has_thinking = True
                break
        if has_thinking:
            break

    return {
        "id": req.id,
        "session_id": req.session_id,
        "timestamp": req.timestamp.isoformat(),
        "provider": str(req.provider),
        "model": req.model,
        "duration_ms": req.duration_ms,
        "is_streaming": req.is_streaming,
        "status": str(req.status),
        "stop_reason": str(req.stop_reason) if req.stop_reason else None,
        "usage": {
            "input_tokens": req.usage.input_tokens,
            "output_tokens": req.usage.output_tokens,
            "total_tokens": req.usage.total_tokens,
            "estimated_cost_usd": req.usage.estimated_cost_usd,
        },
        "preview_text": preview_text,
        "has_tools": len(req.tools) > 0,
        "has_thinking": has_thinking,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}/requests")
async def list_requests(
    session_id: str,
    provider: str | None = Query(default=None),
    model: str | None = Query(default=None),
    has_tools: bool | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int | None = Query(default=None, ge=1, le=5000),
    request_repo: RequestRepository = Depends(get_request_repo),
) -> list[dict[str, Any]]:
    """List requests for a session with optional filters, returning summaries."""
    requests = await request_repo.list_by_session(
        session_id,
        provider=provider,
        model=model,
        has_tools=has_tools,
        offset=offset,
        limit=limit,
    )
    return [_request_summary(r) for r in requests]


@router.get("/requests/{request_id}")
async def get_request(
    request_id: str,
    request_repo: RequestRepository = Depends(get_request_repo),
) -> dict[str, Any]:
    """Return full LLMRequest detail."""
    req = await request_repo.get(request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return req.model_dump(mode="json")


@router.get("/requests/{request_id}/raw")
async def get_request_raw(
    request_id: str,
    request_repo: RequestRepository = Depends(get_request_repo),
    raw_capture_repo: RawCaptureRepository = Depends(get_raw_capture_repo),
) -> dict[str, Any]:
    """Return the RawCapture associated with a request."""
    req = await request_repo.get(request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")

    if not req.raw_capture_id:
        raise HTTPException(status_code=404, detail="No raw capture for this request")

    capture = await raw_capture_repo.get(req.raw_capture_id)
    if capture is None:
        raise HTTPException(status_code=404, detail="Raw capture not found")

    return capture.model_dump(mode="json")
