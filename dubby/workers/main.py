"""Worker process entry point: ``python -m dubby.workers.main --family core``."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from typing import Any, Dict, Optional

if os.environ.get("MPLBACKEND", "").startswith("module://"):
    os.environ["MPLBACKEND"] = "Agg"  # e.g. Colab's matplotlib_inline backend, absent from this venv

from dubby.engines.base import Engine, TTSItem
from dubby.languages import join_tokens
from dubby.engines.registry import engine_class
from dubby.pipeline.chunking import build_chunks
from dubby.workers.protocol import Channel, TaskContext


def detect_device() -> str:
    requested = os.environ.get("DUBBY_DEVICE", "auto")
    if requested != "auto":
        return requested
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


class Worker:
    def __init__(self, family: str, channel: Channel):
        self.family = family
        self.channel = channel
        self.device = detect_device()
        self.engine: Optional[Engine] = None
        self.engine_key: Optional[tuple] = None

    # ----------------------------------------------------------------- engines
    def engine_for(self, engine_id: str, params: Dict[str, Any], ctx: TaskContext) -> Engine:
        cls = engine_class(engine_id)
        key = cls.load_key(params)
        if self.engine is not None and self.engine_key == key:
            self.engine.params.update(params or {})
            return self.engine
        if self.engine is not None:
            ctx.log(f"Unloading {self.engine.info.name}")
            self.engine.unload()
            self.engine = None
        engine = cls(self.device, params)
        started = time.time()
        engine.load(ctx)
        ctx.log(f"{cls.info.name} ready on {self.device} in {time.time() - started:.1f}s")
        self.engine, self.engine_key = engine, key
        return engine

    # ------------------------------------------------------------------ stages
    def run(self, task: Dict[str, Any]) -> Dict[str, Any]:
        ctx = TaskContext(self.channel, task["id"])
        kind, payload = task["kind"], task.get("payload", {})
        engine = self.engine_for(task["engine"], task.get("params", {}), ctx)

        if kind == "asr":
            ctx.progress(0.05, "Model ready")
            raw = engine.transcribe(payload["audio"], payload["language"], ctx)
            ctx.progress(0.97, "Building dubbing chunks…")
            chunks = build_chunks(raw, **payload.get("chunking", {}))
            return {"segments": chunks}

        if kind == "asr_ref":
            ctx.progress(0.05, "Transcribing the reference voice…")
            raw = engine.transcribe(payload["audio"], payload["language"], ctx)
            text = join_tokens([s.get("text", "") for s in raw], payload["language"])
            ctx.progress(1.0, "Reference transcribed")
            return {"text": text}

        if kind == "langid":
            return engine.detect(payload["audio"], ctx)

        if kind == "translation":
            items = payload["items"]
            total = max(1, len(items))
            ctx.progress(0.02, f"Translating {len(items)} segments…")
            count = 0
            for seg_id, text in engine.translate(items, payload["source"], payload["target"], ctx):
                count += 1
                ctx.result("segment_translation", {"id": seg_id, "text": text})
                ctx.progress(count / total, f"Translated {count}/{total}")
            return {"count": count}

        if kind == "tts":
            items = [TTSItem(**it) for it in payload["items"]]
            total = max(1, len(items))
            ctx.progress(0.02, f"Voicing {len(items)} segments…")
            count = 0
            for item, duration in engine.synthesize(items, payload["target"], ctx):
                count += 1
                ctx.result("segment_audio", {"id": item.id, "path": item.out_path, "duration": duration, "text": item.text})
                ctx.progress(count / total, f"Voiced {count}/{total}")
            return {"count": count}

        if kind == "separation":
            engine.separate(payload["audio"], payload["vocals_out"], payload["background_out"], ctx)
            return {"vocals": payload["vocals_out"], "background": payload["background_out"]}

        raise ValueError(f"Unknown task kind: {kind}")

    def serve(self) -> None:
        self.channel.send({"type": "ready", "family": self.family, "python": sys.executable, "device": self.device, "pid": os.getpid()})
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "shutdown":
                break
            if msg.get("type") != "task":
                continue
            try:
                data = self.run(msg)
                self.channel.send({"type": "done", "task": msg["id"], "data": data})
            except Exception as exc:  # report and keep serving
                self.channel.send({"type": "error", "task": msg["id"], "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()})


def main() -> None:
    parser = argparse.ArgumentParser(description="Dubby model worker")
    parser.add_argument("--family", default="core")
    args = parser.parse_args()
    try:
        sys.stdin.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    Worker(args.family, Channel()).serve()


if __name__ == "__main__":
    main()
