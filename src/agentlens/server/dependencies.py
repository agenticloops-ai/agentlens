"""FastAPI dependency injection helpers."""

from __future__ import annotations

from fastapi import Request

from agentlens.storage.repositories import (
    RawCaptureRepository,
    RequestRepository,
    SessionRepository,
)

from .event_bus import EventBus


def get_session_repo(request: Request) -> SessionRepository:
    """FastAPI dependency -- return the ``SessionRepository`` from app state."""
    return request.app.state.session_repo


def get_request_repo(request: Request) -> RequestRepository:
    """FastAPI dependency -- return the ``RequestRepository`` from app state."""
    return request.app.state.request_repo


def get_raw_capture_repo(request: Request) -> RawCaptureRepository:
    """FastAPI dependency -- return the ``RawCaptureRepository`` from app state."""
    return request.app.state.raw_capture_repo


def get_event_bus(request: Request) -> EventBus:
    """FastAPI dependency -- return the ``EventBus`` from app state."""
    return request.app.state.event_bus
