"""Report model download progress to the studio instead of drawing tqdm bars.

Hugging Face Hub (including xet transfers) reports downloads through ``tqdm`` bars
with ``unit="B"``. Inside a worker those bars would only scroll through stderr, so
we patch ``tqdm`` once at start-up: byte bars are silenced and their progress is sent
over the worker protocol as ``download`` events, which the UI renders as progress bars.
"""

from __future__ import annotations

import itertools
import re
import time
from typing import Any, Callable, Dict, Optional, Tuple

MIN_INTERVAL = 0.4  # seconds between updates of one bar
MIN_BYTES = 512 * 1024  # skip tiny files (configs, tokenizer json) — they finish instantly

_ids = itertools.count(1)
_PREFIX = re.compile(r"^(Downloading|Fetching)\s*(\(…\))?\s*", re.I)
# xet transfers report two phases per file: "downloading bytes: x" then "reconstructing file: x"
_PHASE = re.compile(r"^\s*(downloading bytes|reconstructing file|uploading bytes)\s*:\s*(.+)$", re.I)


def _name(desc: Any) -> Tuple[str, str]:
    """``(file name, phase)`` from a tqdm description."""
    text = str(desc or "download").strip()
    phase = _PHASE.match(text)
    if phase:
        return phase.group(2).strip(), "reconstructing" if phase.group(1).lower().startswith("recon") else "downloading"
    return (_PREFIX.sub("", text) or text), "downloading"


def install(send: Callable[[Dict[str, Any]], None], task_id: Callable[[], Optional[str]]) -> bool:
    """Patch tqdm in this process. Returns False when tqdm isn't importable."""
    try:
        import tqdm.std as std
    except Exception:
        return False
    cls = std.tqdm
    if getattr(cls, "_dubby_patched", False):
        return True
    orig_init, orig_update, orig_close = cls.__init__, cls.update, cls.close

    def emit(bar: Any, force: bool = False, done: bool = False) -> None:
        state = bar._dubby
        now = time.time()
        total = getattr(bar, "total", None) or state["total"]
        if not force and now - state["last"] < MIN_INTERVAL:
            return
        if total and total < MIN_BYTES and not state["announced"]:
            return
        state["last"] = now
        state["announced"] = True
        elapsed = max(1e-6, now - state["start"])
        try:
            send({
                "type": "download",
                "task": state["task"],
                "id": state["id"],
                "name": state["name"],
                "phase": state["phase"],
                "downloaded": state["n"],
                "total": total,
                "rate": state["n"] / elapsed,
                "elapsed": elapsed,
                "done": done,
            })
        except Exception:
            pass  # reporting must never break a download

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        track = kwargs.get("unit") == "B"
        if track:
            kwargs["disable"] = True  # nothing on stderr; progress goes through the protocol
        orig_init(self, *args, **kwargs)
        if not track:
            return
        name, phase = _name(kwargs.get("desc"))
        self._dubby = {
            "id": f"dl{next(_ids)}",
            "name": name,
            "phase": phase,
            "n": float(kwargs.get("initial") or 0),
            "total": kwargs.get("total"),
            "start": time.time(),
            "last": 0.0,
            "task": task_id(),
            "announced": False,
            "closed": False,
        }
        emit(self, force=True)

    def update(self: Any, n: Any = 1) -> Any:
        state = getattr(self, "_dubby", None)
        if state is not None and n:
            state["n"] += float(n)
            emit(self)
        return orig_update(self, n)

    def close(self: Any) -> Any:
        state = getattr(self, "_dubby", None)
        if state is not None and not state["closed"]:
            state["closed"] = True
            emit(self, force=True, done=True)
        return orig_close(self)

    cls.__init__, cls.update, cls.close = __init__, update, close
    cls._dubby_patched = True
    return True
