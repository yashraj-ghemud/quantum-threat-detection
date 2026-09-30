"""
server/services/hub.py
======================
In-process publish/subscribe for the WebSocket stream.

``publish`` is safe to call from any thread: events are handed to the event
loop with ``call_soon_threadsafe``. Each client has a bounded queue; when a
slow client falls behind, its oldest events are dropped and a ``lag`` notice
tells it how many.
"""

from __future__ import annotations

import asyncio
import itertools
import time
from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = ["EventHub", "Subscriber", "TOPICS"]

TOPICS = ("sessions", "distributions", "incidents", "links", "reservoir", "traffic", "metrics", "jobs",
          "ledger", "system")


@dataclass(eq=False)
class Subscriber:
    queue: asyncio.Queue
    topics: set = field(default_factory=lambda: set(TOPICS))
    dropped: int = 0
    connected_at: float = field(default_factory=time.time)


class EventHub:
    def __init__(self) -> None:
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.subscribers: set = set()
        self._ids = itertools.count(1)
        self.last_disconnect_at: float = time.time()
        self.listeners: list = []   # callables(client_count) notified on connect/disconnect

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    @property
    def client_count(self) -> int:
        return len(self.subscribers)

    def subscribe(self) -> Subscriber:
        sub = Subscriber(queue=asyncio.Queue(maxsize=512))
        self.subscribers.add(sub)
        for cb in self.listeners:
            cb(len(self.subscribers))
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        self.subscribers.discard(sub)
        self.last_disconnect_at = time.time()
        for cb in self.listeners:
            cb(len(self.subscribers))

    def publish(self, topic: str, type_: str, data: Any) -> None:
        if self.loop is None or not self.subscribers:
            return
        event = {"v": 1, "topic": topic, "type": type_, "ts": time.time(), "id": next(self._ids), "data": data}
        try:
            self.loop.call_soon_threadsafe(self._fanout, event)
        except RuntimeError:  # loop closed during shutdown
            pass

    def _fanout(self, event: dict) -> None:
        for sub in list(self.subscribers):
            if event["topic"] not in sub.topics:
                continue
            q = sub.queue
            if q.full():
                try:
                    q.get_nowait()
                    sub.dropped += 1
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(event)
