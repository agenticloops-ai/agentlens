"""Headless proxy runner — async context manager for proxy lifecycle without a web server."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from agentlens.models import Session
from agentlens.providers import PluginRegistry
from agentlens.proxy.addon import AgentLensAddon
from agentlens.server.event_bus import EventBus
from agentlens.storage.database import init_db
from agentlens.storage.repositories import (
    RawCaptureRepository,
    RequestRepository,
    SessionRepository,
)


@dataclass
class ProxyContext:
    """Holds references to the running proxy infrastructure."""

    session: Session
    session_repo: SessionRepository
    request_repo: RequestRepository
    raw_capture_repo: RawCaptureRepository
    event_bus: EventBus
    proxy_port: int
    host: str


@contextlib.asynccontextmanager
async def headless_proxy(
    *,
    session_name: str = "",
    proxy_port: int = 8080,
    host: str = "127.0.0.1",
    db_path: str | None = None,
):
    """Async context manager that runs a MITM proxy without a web server.

    Usage::

        async with headless_proxy(session_name="test") as ctx:
            # ctx.session, ctx.session_repo, etc. are available
            # proxy is running and capturing traffic on ctx.proxy_port
            ...
        # on exit: session finalized, proxy shut down, DB disposed
    """
    if db_path is None:
        db_path = str(Path.home() / ".agentlens" / "data.db")

    # Ensure DB directory exists
    db_dir = Path(db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)

    engine = await init_db(db_path)

    session_repo = SessionRepository(engine)
    request_repo = RequestRepository(engine)
    raw_capture_repo = RawCaptureRepository(engine)
    event_bus = EventBus()

    # End stale active sessions
    await session_repo.end_all_active()

    # Create session
    session = Session(
        name=session_name or f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    )
    await session_repo.create(session)

    # Create proxy addon
    plugin_registry = PluginRegistry.default()
    addon = AgentLensAddon(
        session_id=session.id,
        session_repo=session_repo,
        request_repo=request_repo,
        raw_capture_repo=raw_capture_repo,
        event_bus=event_bus,
        parser_registry=plugin_registry,
    )

    # Start proxy
    from agentlens.proxy.runner import run_proxy

    proxy_master, proxy_task = await run_proxy(addon, host=host, port=proxy_port)

    ctx = ProxyContext(
        session=session,
        session_repo=session_repo,
        request_repo=request_repo,
        raw_capture_repo=raw_capture_repo,
        event_bus=event_bus,
        proxy_port=proxy_port,
        host=host,
    )

    try:
        yield ctx
    finally:
        # Finalize session
        session.ended_at = datetime.utcnow()
        await session_repo.update(session)

        # Shut down proxy
        proxy_master.shutdown()
        try:
            await asyncio.wait_for(proxy_task, timeout=5)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass

        # Cancel proxy task if still running
        if not proxy_task.done():
            proxy_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await proxy_task

        await engine.dispose()
