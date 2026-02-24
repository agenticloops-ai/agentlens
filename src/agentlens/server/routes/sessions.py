"""Session routes for the AgentLens API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from agentlens.storage.repositories import SessionRepository

from ..dependencies import get_session_repo

router = APIRouter(prefix="/api")


@router.get("/sessions")
async def list_sessions(
    session_repo: SessionRepository = Depends(get_session_repo),
) -> list[dict]:
    """Return all sessions with basic stats."""
    sessions = await session_repo.list_all()
    return [s.model_dump(mode="json") for s in sessions]


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    session_repo: SessionRepository = Depends(get_session_repo),
) -> dict:
    """Return a single session with aggregated stats."""
    session = await session_repo.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    stats = await session_repo.get_stats(session_id)
    result = session.model_dump(mode="json")
    result["stats"] = stats.model_dump(mode="json")
    return result


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    session_repo: SessionRepository = Depends(get_session_repo),
) -> Response:
    """Delete a session and all its requests/captures."""
    session = await session_repo.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    await session_repo.delete(session_id)
    return Response(status_code=204)


@router.delete("/sessions", status_code=204)
async def delete_all_sessions(
    session_repo: SessionRepository = Depends(get_session_repo),
) -> Response:
    """Delete all sessions and their requests/captures."""
    sessions = await session_repo.list_all()
    for s in sessions:
        await session_repo.delete(s.id)
    return Response(status_code=204)
