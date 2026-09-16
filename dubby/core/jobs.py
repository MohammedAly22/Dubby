"""GPU job queue and worker process management (studio side)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional

from dubby.config import Settings
from dubby.core.events import EventBus
from dubby.engines.registry import engine_class
from dubby.workers.protocol import decode

PACKAGE_ROOT = str(Path(__file__).resolve().parents[2])


def worker_env(settings: Settings) -> Dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env["DUBBY_DEVICE"] = settings.device
    env["PYTHONPATH"] = PACKAGE_ROOT + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env.setdefault("TOKENIZERS_PARALLELISM", "false")
    # Colab exports MPLBACKEND=module://matplotlib_inline.backend_inline, which only exists in its
    # own kernel — any import chain reaching matplotlib (whisperx → pyannote → lightning → torchmetrics)
    # would crash the worker. Workers are headless, so force a safe backend.
    env["MPLBACKEND"] = "Agg"
    if settings.hf_token:
        env["HF_TOKEN"] = settings.hf_token
    node = settings.resolved_node()
    if node:
        env["PATH"] = str(Path(node).parent) + os.pathsep + env.get("PATH", "")
    return env


@dataclass
class JobHandlers:
    on_start: Callable[[], None] = lambda: None
    on_progress: Callable[[float, str], None] = lambda v, m: None
    on_result: Callable[[str, Dict[str, Any]], None] = lambda k, d: None
    on_done: Callable[[Dict[str, Any]], None] = lambda d: None
    on_error: Callable[[str], None] = lambda e: None
    on_cancel: Callable[[], None] = lambda: None


@dataclass
class Job:
    project_id: str
    stage: str
    kind: str
    engine: str
    params: Dict[str, Any]
    payload: Dict[str, Any]
    handlers: JobHandlers
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: str = "queued"
    created_at: float = field(default_factory=time.time)

    def describe(self) -> Dict[str, Any]:
        return {"id": self.id, "project_id": self.project_id, "stage": self.stage, "engine": self.engine, "status": self.status, "created_at": self.created_at}


class WorkerProcess:
    def __init__(self, family: str, settings: Settings, bus: EventBus, on_event: Callable[[str, Dict[str, Any]], None]):
        self.family = family
        self.settings = settings
        self.bus = bus
        self.on_event = on_event
        self.proc: Optional[subprocess.Popen] = None
        self.ready = threading.Event()
        self.info: Dict[str, Any] = {}
        self._write_lock = threading.Lock()

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, timeout: float = 180.0) -> None:
        python = self.settings.python_for(self.family)
        if not Path(python).exists():
            raise RuntimeError(f"Interpreter for engine family '{self.family}' not found: {python}")
        self.ready.clear()
        self.bus.log(f"Starting {self.family} worker ({python})", source=f"worker:{self.family}")
        self.proc = subprocess.Popen(
            [python, "-u", "-m", "dubby.workers.main", "--family", self.family],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=worker_env(self.settings),
            cwd=PACKAGE_ROOT,
        )
        threading.Thread(target=self._read_stdout, daemon=True, name=f"worker-{self.family}-out").start()
        threading.Thread(target=self._read_stderr, daemon=True, name=f"worker-{self.family}-err").start()
        deadline = time.time() + timeout
        while not self.ready.wait(0.25):
            if not self.alive:
                raise RuntimeError(f"{self.family} worker exited during startup (code {self.proc.returncode}). See logs.")
            if time.time() > deadline:
                self.kill()
                raise RuntimeError(f"{self.family} worker did not start within {timeout:.0f}s")

    def _read_stdout(self) -> None:
        proc = self.proc
        assert proc and proc.stdout
        for line in proc.stdout:
            event = decode(line)
            if event is None:
                if line.strip():
                    self.bus.log(line.rstrip(), source=f"worker:{self.family}")
                continue
            if event.get("type") == "ready":
                self.info = event
                self.ready.set()
                self.bus.log(f"{self.family} worker ready · device={event.get('device')} · pid={event.get('pid')}", source=f"worker:{self.family}")
                continue
            self.on_event(self.family, event)
        code = proc.wait()
        self.on_event(self.family, {"type": "exit", "code": code})

    def _read_stderr(self) -> None:
        proc = self.proc
        assert proc and proc.stderr
        for raw in proc.stderr:
            # progress bars redraw with carriage returns: keep the last frame only
            line = raw.rstrip("\n").split("\r")[-1].rstrip()
            if line:
                # Library chatter (warnings, progress bars) stays at debug level; engines
                # report meaningful messages through the protocol with explicit levels.
                fatal = line.startswith(("Traceback", "RuntimeError", "torch.OutOfMemoryError", "CUDA out of memory", "Killed"))
                self.bus.log(line, level="error" if fatal else "debug", source=f"worker:{self.family}")

    def send(self, message: Dict[str, Any]) -> None:
        if not self.alive or not self.proc or not self.proc.stdin:
            raise RuntimeError(f"{self.family} worker is not running")
        with self._write_lock:
            self.proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()

    def stop(self) -> None:
        if not self.alive:
            return
        try:
            self.send({"type": "shutdown"})
            self.proc.wait(timeout=8)  # type: ignore[union-attr]
        except Exception:
            self.kill()

    def kill(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass


class JobManager:
    """Runs model jobs one at a time (they share the GPU) on per-family workers."""

    def __init__(self, settings: Settings, bus: EventBus):
        self.settings = settings
        self.bus = bus
        self.queue: Deque[Job] = deque()
        self.current: Optional[Job] = None
        self.workers: Dict[str, WorkerProcess] = {}
        self._cond = threading.Condition()
        self._finished = threading.Event()
        self._cancelled_current = False
        self._stop = False
        threading.Thread(target=self._loop, daemon=True, name="dubby-jobs").start()

    # ------------------------------------------------------------------ public
    def submit(self, job: Job) -> Job:
        with self._cond:
            self.queue.append(job)
            self._cond.notify_all()
        self.bus.publish({"type": "jobs", "jobs": self.snapshot()})
        return job

    def cancel(self, project_id: str, stage: Optional[str] = None) -> int:
        cancelled: List[Job] = []
        with self._cond:
            for job in list(self.queue):
                if job.project_id == project_id and (stage is None or job.stage == stage):
                    self.queue.remove(job)
                    cancelled.append(job)
            current = self.current
        for job in cancelled:
            job.status = "cancelled"
            job.handlers.on_cancel()
        if current and current.project_id == project_id and (stage is None or current.stage == stage):
            self._cancelled_current = True
            family = engine_class(current.engine).info.family
            worker = self.workers.get(family)
            if worker:
                self.bus.log(f"Cancelling {current.stage} — stopping {family} worker", "warning", project_id)
                worker.kill()
            cancelled.append(current)
        self.bus.publish({"type": "jobs", "jobs": self.snapshot()})
        return len(cancelled)

    def snapshot(self) -> Dict[str, Any]:
        with self._cond:
            return {
                "current": self.current.describe() if self.current else None,
                "queued": [j.describe() for j in self.queue],
                "workers": {f: {"alive": w.alive, **{k: w.info.get(k) for k in ("device", "python", "pid")}} for f, w in self.workers.items()},
            }

    def stop_workers(self) -> None:
        for w in self.workers.values():
            w.stop()

    def shutdown(self) -> None:
        self._stop = True
        with self._cond:
            self._cond.notify_all()
        for w in self.workers.values():
            w.kill()

    # ----------------------------------------------------------------- private
    def _worker(self, family: str) -> WorkerProcess:
        if self.settings.exclusive_gpu:
            for other_family, other in self.workers.items():
                if other_family != family and other.alive:
                    self.bus.log(f"Stopping {other_family} worker to free GPU memory", source="jobs")
                    other.stop()
        worker = self.workers.get(family)
        if worker is None:
            worker = WorkerProcess(family, self.settings, self.bus, self._on_worker_event)
            self.workers[family] = worker
        if not worker.alive:
            worker.start()
        return worker

    def _loop(self) -> None:
        while not self._stop:
            with self._cond:
                while not self.queue and not self._stop:
                    self._cond.wait()
                if self._stop:
                    return
                job = self.queue.popleft()
                self.current = job
            self._cancelled_current = False
            self._finished.clear()
            job.status = "running"
            self.bus.publish({"type": "jobs", "jobs": self.snapshot()})
            try:
                job.handlers.on_start()
                family = engine_class(job.engine).info.family
                worker = self._worker(family)
                worker.send({"type": "task", "id": job.id, "kind": job.kind, "engine": job.engine, "params": job.params, "payload": job.payload})
                self._finished.wait()
            except Exception as exc:
                job.status = "error"
                job.handlers.on_error(str(exc))
            finally:
                if self._cancelled_current and job.status not in ("done", "error"):
                    job.status = "cancelled"
                    job.handlers.on_cancel()
                with self._cond:
                    self.current = None
                self.bus.publish({"type": "jobs", "jobs": self.snapshot()})

    def _on_worker_event(self, family: str, event: Dict[str, Any]) -> None:
        job = self.current
        etype = event.get("type")
        if etype == "exit":
            if job and job.status == "running" and engine_class(job.engine).info.family == family:
                if not self._cancelled_current:
                    job.status = "error"
                    job.handlers.on_error(f"{family} worker exited unexpectedly (code {event.get('code')}). Check the logs — often out of memory.")
                self._finished.set()
            return
        if etype == "log":
            self.bus.log(event.get("message", ""), event.get("level", "info"), job.project_id if job else None, source=f"worker:{family}")
            return
        if not job or event.get("task") != job.id:
            return
        try:
            if etype == "progress":
                job.handlers.on_progress(float(event.get("value", 0)), event.get("message", ""))
            elif etype == "result":
                job.handlers.on_result(event.get("kind", ""), event.get("data", {}))
            elif etype == "done":
                job.status = "done"
                job.handlers.on_done(event.get("data", {}))
                self._finished.set()
            elif etype == "error":
                job.status = "error"
                tb = event.get("traceback")
                if tb:
                    self.bus.log(tb, "error", job.project_id, source=f"worker:{family}")
                job.handlers.on_error(event.get("error", "unknown error"))
                self._finished.set()
        except Exception as exc:  # handler bug must not wedge the queue
            self.bus.log(f"Job handler failed: {exc}", "error", job.project_id, source="jobs")
            if etype in ("done", "error"):
                self._finished.set()


def run_doctor(settings: Settings, family: str, timeout: float = 120.0) -> Dict[str, Any]:
    python = settings.python_for(family)
    if not Path(python).exists():
        return {"family": family, "python": python, "error": "interpreter not found", "engines": {}}
    try:
        out = subprocess.run(
            [python, "-m", "dubby.workers.doctor", "--family", family],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, env=worker_env(settings), cwd=PACKAGE_ROOT,
        )
        line = next((ln for ln in reversed(out.stdout.splitlines()) if ln.strip().startswith("{")), None)
        if line is None:
            return {"family": family, "python": python, "error": (out.stderr or "no output")[-800:], "engines": {}}
        return json.loads(line)
    except Exception as exc:
        return {"family": family, "python": python, "error": str(exc), "engines": {}}


__all__ = ["Job", "JobHandlers", "JobManager", "WorkerProcess", "run_doctor", "sys"]
