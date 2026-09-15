"""Line-based JSON protocol between the studio and its worker processes.

studio → worker (stdin):   one JSON object per line
    {"type": "task", "id": "...", "kind": "asr|translation|tts|separation",
     "engine": "whisperx", "params": {...}, "payload": {...}}
    {"type": "shutdown"}

worker → studio (stdout):  lines prefixed with ``@@DUBBY@@``
    {"type": "ready"}
    {"type": "progress", "task": id, "value": 0.42, "message": "..."}
    {"type": "result",   "task": id, "kind": "segment_translation", "data": {...}}
    {"type": "log",      "task": id, "level": "info", "message": "..."}
    {"type": "done",     "task": id, "data": {...}}
    {"type": "error",    "task": id, "error": "...", "traceback": "..."}

Anything else the worker (or a native library) prints goes to stderr and is
forwarded to the log console verbatim.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from typing import Any, Dict, Optional

PREFIX = "@@DUBBY@@"


def encode(event: Dict[str, Any]) -> str:
    return PREFIX + json.dumps(event, ensure_ascii=False) + "\n"


def decode(line: str) -> Optional[Dict[str, Any]]:
    if not line.startswith(PREFIX):
        return None
    try:
        return json.loads(line[len(PREFIX):])
    except json.JSONDecodeError:
        return None


class Channel:
    """Worker-side writer on a private duplicate of the original stdout.

    ``fd 1`` is re-pointed to stderr so stray prints from libraries can never
    corrupt protocol lines.
    """

    def __init__(self) -> None:
        sys.stdout.flush()
        proto_fd = os.dup(1)
        os.dup2(2, 1)
        self._out = os.fdopen(proto_fd, "w", encoding="utf-8", buffering=1, newline="\n")
        sys.stdout = sys.stderr
        self._lock = threading.Lock()

    def send(self, event: Dict[str, Any]) -> None:
        with self._lock:
            self._out.write(encode(event))
            self._out.flush()


class TaskContext:
    """Handed to engines so they can report progress and streaming results."""

    def __init__(self, channel: Channel, task_id: str):
        self._channel = channel
        self.task_id = task_id

    def progress(self, value: float, message: str = "") -> None:
        self._channel.send({"type": "progress", "task": self.task_id, "value": max(0.0, min(1.0, float(value))), "message": message})

    def result(self, kind: str, data: Dict[str, Any]) -> None:
        self._channel.send({"type": "result", "task": self.task_id, "kind": kind, "data": data})

    def log(self, message: str, level: str = "info") -> None:
        self._channel.send({"type": "log", "task": self.task_id, "level": level, "message": message})
