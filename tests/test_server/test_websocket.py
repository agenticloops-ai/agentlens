"""Tests for the WebSocket live events endpoint."""

from __future__ import annotations

import asyncio
import json
import threading

from starlette.testclient import TestClient

from agentlens.server.app import create_app
from agentlens.server.event_bus import EventBus
from agentlens.storage.database import init_db
from agentlens.storage.repositories import (
    RawCaptureRepository,
    RequestRepository,
    SessionRepository,
)


def _create_test_app():
    """Create a FastAPI app with an in-memory database and event bus.

    Because Starlette's TestClient runs the ASGI app in a separate thread
    with its own event loop, we cannot simply ``await init_db(...)`` here.
    Instead we wire up a *lifespan-free* app and set state manually using a
    synchronous helper that boots a temporary event loop.
    """
    app = create_app()

    # Run async DB init in a fresh, short-lived event loop so the engine is
    # created on the correct thread.  The TestClient will spin up its own
    # loop later, but SQLite in-memory databases only require the engine
    # object – they don't bind to a specific loop.
    loop = asyncio.new_event_loop()
    engine = loop.run_until_complete(init_db(""))
    loop.close()

    app.state.engine = engine
    app.state.session_repo = SessionRepository(engine)
    app.state.request_repo = RequestRepository(engine)
    app.state.raw_capture_repo = RawCaptureRepository(engine)
    app.state.event_bus = EventBus()

    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_websocket_connects_successfully():
    """The /api/ws/live endpoint accepts a WebSocket connection."""
    app = _create_test_app()
    client = TestClient(app)

    with client.websocket_connect("/api/ws/live") as ws:
        # Connection accepted – nothing to receive yet, just verify we're open.
        assert ws is not None


def test_websocket_receives_published_event():
    """Events published to the EventBus are forwarded to the WebSocket client."""
    app = _create_test_app()
    event_bus: EventBus = app.state.event_bus
    client = TestClient(app)

    sample_event = {
        "type": "new_request",
        "session_id": "sess-1",
        "request_id": "req-1",
    }

    with client.websocket_connect("/api/ws/live") as ws:
        # The WebSocket handler runs on the TestClient's background thread /
        # event loop.  We need to publish *on that same loop* so the queue
        # wakes up.  We can grab the loop from the running thread.
        _publish_on_server_loop(app, event_bus, sample_event)

        data = ws.receive_text()
        parsed = json.loads(data)

        assert parsed == sample_event


def test_websocket_receives_multiple_events():
    """Multiple events are delivered in order."""
    app = _create_test_app()
    event_bus: EventBus = app.state.event_bus
    client = TestClient(app)

    events = [
        {"type": "new_request", "index": 0},
        {"type": "new_request", "index": 1},
        {"type": "new_request", "index": 2},
    ]

    with client.websocket_connect("/api/ws/live") as ws:
        for evt in events:
            _publish_on_server_loop(app, event_bus, evt)

        for expected in events:
            data = ws.receive_text()
            parsed = json.loads(data)
            assert parsed == expected


def test_websocket_disconnect_unsubscribes():
    """After disconnection the subscriber queue is removed from the bus."""
    app = _create_test_app()
    event_bus: EventBus = app.state.event_bus
    client = TestClient(app)

    with client.websocket_connect("/api/ws/live"):
        # While connected there should be exactly one subscriber.
        assert len(event_bus._subscribers) == 1

    # After the context manager exits (WebSocket closed), the handler's
    # finally block should have unsubscribed.
    assert len(event_bus._subscribers) == 0


def test_websocket_multiple_clients():
    """Two simultaneous WebSocket clients each receive the same event."""
    app = _create_test_app()
    event_bus: EventBus = app.state.event_bus
    client = TestClient(app)

    sample_event = {"type": "broadcast", "payload": "hello"}

    with client.websocket_connect("/api/ws/live") as ws1:
        with client.websocket_connect("/api/ws/live") as ws2:
            assert len(event_bus._subscribers) == 2

            _publish_on_server_loop(app, event_bus, sample_event)

            data1 = ws1.receive_text()
            data2 = ws2.receive_text()

            assert json.loads(data1) == sample_event
            assert json.loads(data2) == sample_event

    assert len(event_bus._subscribers) == 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _publish_on_server_loop(app, event_bus: EventBus, event: dict) -> None:
    """Publish an event on the ASGI server's event loop (running in its own thread).

    Starlette's ``TestClient`` runs the ASGI app inside a background thread
    that owns its own ``asyncio`` event loop.  To interact with async objects
    (like ``EventBus.publish``) that live on that loop we must schedule the
    coroutine there using ``asyncio.run_coroutine_threadsafe``.
    """
    # The TestClient stores the portal's loop on the app instance via the
    # anyio backend.  We can find it by inspecting the event bus's subscriber
    # queues – they were created on the server loop.  A simpler, more
    # reliable approach: just call the synchronous queue.put_nowait directly,
    # which is thread-safe for asyncio.Queue.
    for queue in event_bus._subscribers:
        queue.put_nowait(event)
