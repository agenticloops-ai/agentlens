"""In-process async pub/sub for live updates."""

from __future__ import annotations

import asyncio
from typing import Any


class EventBus:
    """Simple in-process event bus that fans out events to async subscribers."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """Create a new subscription queue and return it."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """Remove a subscription queue."""
        try:
            self._subscribers.remove(queue)
        except ValueError:
            pass

    async def publish(self, event: dict[str, Any]) -> None:
        """Publish an event to all current subscribers."""
        for queue in self._subscribers:
            await queue.put(event)
