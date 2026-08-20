"""In-process pub/sub used by the live trace stream.

Ingest handlers publish compact event payloads keyed by project; SSE
connections subscribe and forward them to the dashboard. Queues are bounded
and drop the oldest event under back-pressure so a slow browser can never stall
ingestion.

This bus is per-process. A multi-worker deployment needs a shared broker
(Redis pub/sub) for a browser connected to worker A to see ingest that landed on
worker B; see docs/architecture.md.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

MAX_QUEUE_SIZE = 200


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[UUID, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._published = 0
        self._dropped = 0

    def subscribe(self, project_id: UUID) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self._subscribers.setdefault(project_id, set()).add(queue)
        return queue

    def unsubscribe(self, project_id: UUID, queue: asyncio.Queue[dict[str, Any]]) -> None:
        listeners = self._subscribers.get(project_id)
        if not listeners:
            return
        listeners.discard(queue)
        if not listeners:
            self._subscribers.pop(project_id, None)

    def publish(self, project_id: UUID, event_type: str, data: dict[str, Any]) -> int:
        """Fan out one event. Returns the number of queues that accepted it."""

        listeners = self._subscribers.get(project_id)
        if not listeners:
            return 0
        payload = {"type": event_type, "data": data}
        delivered = 0
        for queue in list(listeners):
            if queue.full():
                try:
                    queue.get_nowait()
                    self._dropped += 1
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(payload)
                delivered += 1
            except asyncio.QueueFull:
                self._dropped += 1
        self._published += delivered
        return delivered

    @property
    def subscriber_count(self) -> int:
        return sum(len(queues) for queues in self._subscribers.values())

    @property
    def project_count(self) -> int:
        return len(self._subscribers)

    def stats(self) -> dict[str, int]:
        return {
            "subscribers": self.subscriber_count,
            "projects_watched": self.project_count,
            "events_published": self._published,
            "events_dropped": self._dropped,
        }


bus = EventBus()
