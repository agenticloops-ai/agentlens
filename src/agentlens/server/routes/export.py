"""Export routes for downloading session data in various formats."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from agentlens.export.formats import (
    render_csv,
    render_json,
    render_markdown,
    safe_filename,
)
from agentlens.storage.repositories import (
    RawCaptureRepository,
    RequestRepository,
    SessionRepository,
)

from ..dependencies import get_raw_capture_repo, get_request_repo, get_session_repo

router = APIRouter(prefix="/api")


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

    content = render_json(session, stats, requests, raw_captures)
    filename = safe_filename(session.name) + ".json"

    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Export: Markdown
# ---------------------------------------------------------------------------


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

    content = render_markdown(session, stats, requests)
    filename = safe_filename(session.name) + ".md"

    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Export: CSV
# ---------------------------------------------------------------------------


async def _export_csv(
    session_id: str,
    session_repo: SessionRepository,
    request_repo: RequestRepository,
) -> Response:
    session = await session_repo.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    requests = await request_repo.list_by_session(session_id, limit=10_000)
    content = render_csv(requests)
    filename = safe_filename(session.name) + ".csv"

    return Response(
        content=content,
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
