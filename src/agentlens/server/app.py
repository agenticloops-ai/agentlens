"""FastAPI application for the AgentLens API."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from agentlens.storage.database import init_db
from agentlens.storage.repositories import (
    RawCaptureRepository,
    RequestRepository,
    SessionRepository,
)

from .event_bus import EventBus
from .routes import events_router, export_router, providers_router, requests_router, sessions_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle for the FastAPI application."""
    # Resolve database path.
    db_path = os.environ.get("AGENT_PROFILER_DB_PATH", "")
    if not db_path:
        default_dir = Path.home() / ".agentlens"
        default_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(default_dir / "data.db")

    engine = await init_db(db_path)

    # Wire up repositories and event bus on app.state.
    app.state.engine = engine
    app.state.session_repo = SessionRepository(engine)
    app.state.request_repo = RequestRepository(engine)
    app.state.raw_capture_repo = RawCaptureRepository(engine)
    app.state.event_bus = EventBus()

    yield

    # Shutdown: dispose of the engine.
    await engine.dispose()


def create_app(
    *,
    custom_lifespan: asynccontextmanager | None = None,
    skip_lifespan: bool = False,
) -> FastAPI:
    """Build and return the configured FastAPI application.

    Parameters
    ----------
    custom_lifespan:
        An optional async context-manager to use instead of the default lifespan.
    skip_lifespan:
        If ``True``, no lifespan handler is registered.  The caller is
        responsible for setting ``app.state`` attributes before the server
        starts accepting requests and for disposing of the engine on shutdown.
    """
    effective_lifespan = None
    if not skip_lifespan:
        effective_lifespan = custom_lifespan if custom_lifespan is not None else lifespan

    app = FastAPI(title="AgentLens API", lifespan=effective_lifespan)

    # CORS — permissive for development.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers.
    app.include_router(sessions_router)
    app.include_router(requests_router)
    app.include_router(events_router)
    app.include_router(export_router)
    app.include_router(providers_router)

    # Serve built React frontend from web/dist/ if available.
    _dist_dir = Path(__file__).resolve().parent.parent / "static"
    if _dist_dir.is_dir():
        # Mount static assets (JS, CSS, images) under /assets.
        _assets_dir = _dist_dir / "assets"
        if _assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="static-assets")

        # Serve other static files at root (e.g. /vite.svg).
        @app.get("/vite.svg", include_in_schema=False)
        async def _vite_svg():
            svg = _dist_dir / "vite.svg"
            if svg.exists():
                return FileResponse(str(svg), media_type="image/svg+xml")
            return HTMLResponse("", status_code=404)

        # SPA catch-all: serve index.html for any non-API path.
        @app.get("/{path:path}", include_in_schema=False)
        async def _spa_catchall(request: Request, path: str):
            # Don't intercept API or WebSocket routes.
            if path.startswith("api/"):
                return HTMLResponse('{"detail":"Not Found"}', status_code=404)
            index = _dist_dir / "index.html"
            if index.exists():
                return FileResponse(str(index), media_type="text/html")
            return HTMLResponse("<h1>Frontend not built</h1><p>Run <code>cd web && npm run build</code></p>", status_code=404)

    return app
