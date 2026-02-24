"""WebSocket route for live event streaming."""

from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..event_bus import EventBus

router = APIRouter(prefix="/api")


@router.websocket("/ws/live")
async def live_events(websocket: WebSocket) -> None:
    """Stream live events to a WebSocket client."""
    await websocket.accept()

    # Access the event bus from app state.
    event_bus: EventBus = websocket.app.state.event_bus
    queue = event_bus.subscribe()

    try:
        while True:
            event = await queue.get()
            await websocket.send_text(json.dumps(event))
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        # Server is shutting down — close the socket with "Going Away" so the
        # client sees a clean close frame instead of ABNORMAL_CLOSURE.
        with contextlib.suppress(Exception):
            await websocket.close(code=1001)
    finally:
        event_bus.unsubscribe(queue)
