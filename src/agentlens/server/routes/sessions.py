"""Session routes for the AgentLens API."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from agentlens.models import Session
from agentlens.server.event_bus import EventBus
from agentlens.storage.repositories import SessionRepository

from ..dependencies import get_addon, get_event_bus, get_session_repo

router = APIRouter(prefix="/api")


class _NewSessionBody(BaseModel):
    name: str | None = None


class _RenameBody(BaseModel):
    name: str


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


@router.post("/sessions/new")
async def create_new_session(
    body: _NewSessionBody | None = None,
    session_repo: SessionRepository = Depends(get_session_repo),
    event_bus: EventBus = Depends(get_event_bus),
    addon=Depends(get_addon),
) -> dict:
    """End the current session and start a new one."""
    # End the current active session
    current = await session_repo.get(addon.session_id)
    if current and current.ended_at is None:
        current.ended_at = datetime.utcnow()
        await session_repo.update(current)

    # Create a new session
    name = (body.name if body and body.name else None) or f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    new_session = Session(name=name)
    await session_repo.create(new_session)

    # Swap the addon's session_id
    addon.session_id = new_session.id

    # Notify clients
    await event_bus.publish({"type": "session_updated"})

    return new_session.model_dump(mode="json")


@router.patch("/sessions/{session_id}")
async def rename_session(
    session_id: str,
    body: _RenameBody,
    session_repo: SessionRepository = Depends(get_session_repo),
    event_bus: EventBus = Depends(get_event_bus),
) -> dict:
    """Rename a session."""
    session = await session_repo.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    session.name = body.name
    await session_repo.update(session)

    await event_bus.publish({"type": "session_updated"})

    return session.model_dump(mode="json")


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
