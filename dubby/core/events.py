"""Thread-safe event bus bridging worker threads, the terminal and websockets."""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional, Set

Event = Dict[str, Any]


class EventBus:
    def __init__(self, log_history: int = 800):
        self._callbacks: List[Callable[[Event], None]] = []
        self._queues: Set[asyncio.Queue] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = threading.Lock()
        self.logs: Deque[Event] = deque(maxlen=log_history)

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, callback: Callable[[Event], None]) -> None:
        with self._lock:
            self._callbacks.append(callback)

    def open_queue(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=5000)
        with self._lock:
            self._queues.add(q)
        return q

    def close_queue(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._queues.discard(q)

    def publish(self, event: Event) -> None:
        event.setdefault("ts", time.time())
        if event.get("type") == "log":
            self.logs.append(event)
        with self._lock:
            callbacks = list(self._callbacks)
            queues = list(self._queues)
        for cb in callbacks:
            try:
                cb(event)
            except Exception:  # a broken reporter must never break the pipeline
                pass
        if self._loop is None or not queues:
            return
        for q in queues:
            try:
                self._loop.call_soon_threadsafe(_put_nowait, q, event)
            except RuntimeError:  # loop closed during shutdown
                pass

    def log(self, message: str, level: str = "info", project_id: Optional[str] = None, source: str = "dubby") -> None:
        self.publish({"type": "log", "level": level, "message": message, "project_id": project_id, "source": source})


def _put_nowait(q: asyncio.Queue, event: Event) -> None:
    try:
        q.put_nowait(event)
    except asyncio.QueueFull:
        pass
