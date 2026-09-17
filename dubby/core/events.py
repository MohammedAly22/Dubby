"""Thread-safe event bus bridging worker threads, the terminal and websockets."""

from __future__ import annotations

import asyncio
import threading
import time
from collections import OrderedDict, deque
from typing import Any, Callable, Deque, Dict, List, Optional, Set

Event = Dict[str, Any]


class EventBus:
    def __init__(self, log_history: int = 800):
        self._callbacks: List[Callable[[Event], None]] = []
        self._queues: Set[asyncio.Queue] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = threading.Lock()
        self.logs: Deque[Event] = deque(maxlen=log_history)
        # in-flight model downloads, so a browser that connects mid-download sees them too
        self.downloads: Dict[str, Event] = {}
        # every tracked request (jobs, VAD, API calls, TTS batches, renders…), newest last
        self.requests: "OrderedDict[str, Event]" = OrderedDict()
        self.max_requests = 2000

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

    def download(self, event: Event) -> None:
        with self._lock:
            if event.get("done"):
                self.downloads.pop(event["id"], None)
            else:
                self.downloads[event["id"]] = event
        self.publish(event)

    def request(self, event: Event) -> Event:
        """Create or update one request record (merged by id) and broadcast it."""
        with self._lock:
            merged = {**self.requests.get(event["id"], {}), **{k: v for k, v in event.items() if v is not None}}
            merged["type"] = "request"
            if merged.get("started") and merged.get("ended"):
                merged["duration"] = round(float(merged["ended"]) - float(merged["started"]), 3)
            self.requests[event["id"]] = merged
            self.requests.move_to_end(event["id"])
            while len(self.requests) > self.max_requests:
                self.requests.popitem(last=False)
        self.publish(dict(merged))
        return merged

    def clear_requests(self) -> None:
        """Forget finished requests (running and queued ones stay visible)."""
        with self._lock:
            for rid in [k for k, v in self.requests.items() if v.get("status") not in ("running", "queued")]:
                self.requests.pop(rid, None)
        self.publish({"type": "requests_cleared"})

    def clear_downloads(self, family: str) -> None:
        """A worker died: its downloads will never report ``done``."""
        with self._lock:
            stale = [e for k, e in self.downloads.items() if e.get("family") == family]
            for e in stale:
                self.downloads.pop(e["id"], None)
        for e in stale:
            self.publish({**e, "done": True, "failed": True})

    def log(self, message: str, level: str = "info", project_id: Optional[str] = None, source: str = "dubby") -> None:
        self.publish({"type": "log", "level": level, "message": message, "project_id": project_id, "source": source})


def _put_nowait(q: asyncio.Queue, event: Event) -> None:
    try:
        q.put_nowait(event)
    except asyncio.QueueFull:
        pass
