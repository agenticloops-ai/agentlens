"""Provider metadata routes."""

from __future__ import annotations

from fastapi import APIRouter

from agentlens.providers import PluginRegistry

router = APIRouter(prefix="/api")


@router.get("/providers")
async def list_providers() -> list[dict]:
    """Return metadata for all registered providers."""
    registry = PluginRegistry.default()
    return registry.get_providers()
