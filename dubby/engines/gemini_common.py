"""Shared Google Gemini helpers: client, retries with backoff, concurrency and key validation.

Gemini engines run in the CPU-only ``cloud`` family: they call the Gemini API instead of
loading weights, so they never compete with local models for VRAM. The API key reaches the
worker through the ``GEMINI_API_KEY`` environment variable (set from Settings).
"""

from __future__ import annotations

import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple, TypeVar

from dubby.engines.base import option

KEY_URL = "https://aistudio.google.com/apikey"

TEXT_MODELS = [
    ("gemini-flash-latest", "Gemini Flash (latest) — fast, strong"),
    ("gemini-flash-lite-latest", "Gemini Flash-Lite (latest) — fastest, cheapest"),
    ("gemini-3.5-flash", "Gemini 3.5 Flash"),
    ("gemini-pro-latest", "Gemini Pro (latest) — highest quality, slower"),
    ("gemini-2.5-flash", "Gemini 2.5 Flash"),
]
TTS_MODELS = [
    ("gemini-3.1-flash-tts-preview", "Gemini 3.1 Flash TTS — newest"),
    ("gemini-2.5-flash-preview-tts", "Gemini 2.5 Flash TTS — fast"),
    ("gemini-2.5-pro-preview-tts", "Gemini 2.5 Pro TTS — most expressive"),
]

RETRYABLE = ("500", "502", "503", "504", "UNAVAILABLE", "DEADLINE_EXCEEDED",
             "INTERNAL", "timed out", "Timeout", "Connection reset", "RemoteProtocolError")
RATE_LIMITED = ("429", "RESOURCE_EXHAUSTED", "Quota exceeded")
RATE_LIMITS_URL = "https://ai.dev/rate-limit"

T = TypeVar("T")
R = TypeVar("R")


def model_options(models) -> List[Dict[str, Any]]:
    return [option(value, label) for value, label in models]


def api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("No Gemini API key is configured")
    return key


def client(key: Optional[str] = None):
    from google import genai

    return genai.Client(api_key=key or api_key())


# ------------------------------------------------------------------ rate limits & quotas
#
# Gemini limits each model separately, per minute (RPM / TPM) and per day (RPD), and those limits
# come from the project's usage tier: billing credits pay for requests but don't raise them.
# A per-minute 429 carries a RetryInfo delay: every thread using that model pauses for it and the
# model's concurrency is halved (growing back after successes). A per-day 429 won't clear by
# waiting, so the caller moves on to the next model of the same kind.

_notify: Callable[[str], None] = lambda message: None  # noqa: E731


def set_notifier(fn: Optional[Callable[[str], None]]) -> None:
    """Where rate-limit and model-switch warnings go (the running task's log, in a worker)."""
    global _notify
    _notify = fn or (lambda message: None)


class QuotaExhausted(RuntimeError):
    """A model's daily quota is used up: waiting won't help, another model might."""

    def __init__(self, model: str, info: Dict[str, Any]):
        self.model, self.info = model, info
        limit = f" (limit {info['limit']} requests per day)" if info.get("limit") else ""
        super().__init__(
            f"429 RESOURCE_EXHAUSTED: the daily Gemini quota for {model} is used up{limit}. "
            f"Quota: {info.get('quota_id') or info.get('metric') or 'requests per day'}. "
            f"Per-model limits come from your usage tier, not your credit balance — see {RATE_LIMITS_URL}."
        )


def _seconds(value: Any) -> Optional[float]:
    match = re.match(r"\s*([\d.]+)\s*s", str(value or ""))
    return float(match.group(1)) if match else None


def quota_info(exc: BaseException) -> Dict[str, Any]:
    """The retry delay and the violated quota of a Gemini 429 (structured details first, then the text)."""
    info: Dict[str, Any] = {"retry_after": None, "metric": None, "quota_id": None, "limit": None, "daily": False}
    details = getattr(exc, "details", None)
    error = details.get("error", details) if isinstance(details, dict) else {}
    for item in (error.get("details") or []) if isinstance(error, dict) else []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("@type", ""))
        if kind.endswith("RetryInfo"):
            info["retry_after"] = _seconds(item.get("retryDelay"))
        elif kind.endswith("QuotaFailure"):
            for violation in item.get("violations") or []:
                info["metric"] = info["metric"] or violation.get("quotaMetric")
                info["quota_id"] = info["quota_id"] or violation.get("quotaId")
                info["limit"] = info["limit"] or violation.get("quotaValue")
    text = str(exc)
    if info["retry_after"] is None:
        match = re.search(r"retry in ([\d.]+)\s*s", text, re.I) or re.search(r"retryDelay\W+([\d.]+)s", text)
        info["retry_after"] = float(match.group(1)) if match else None
    if not info["metric"]:
        match = re.search(r"Quota exceeded for metric:\s*([\w./-]+)", text)
        info["metric"] = match.group(1) if match else None
    if not info["quota_id"]:
        match = re.search(r"quotaId\W+([\w-]+)", text)
        info["quota_id"] = match.group(1) if match else None
    if not info["limit"]:
        match = re.search(r"(?:quotaValue\W+|limit:\s*)(\d+)", text)
        info["limit"] = match.group(1) if match else None
    ids = re.sub(r"[_\-\s]", "", f"{info['metric'] or ''} {info['quota_id'] or ''}".lower())
    info["daily"] = "perday" in ids
    return info


def is_rate_limited(exc: BaseException) -> bool:
    return getattr(exc, "code", None) == 429 or any(marker in f"{type(exc).__name__}: {exc}" for marker in RATE_LIMITED)


class _Gate:
    """Per-model gate: pauses every caller during a rate-limit cooldown and adapts concurrency."""

    def __init__(self) -> None:
        self.cond = threading.Condition()
        self.active = 0
        self.limit: Optional[int] = None  # None: the caller's thread pool decides
        self.resume_at = 0.0
        self.streak = 0

    def acquire(self) -> None:
        with self.cond:
            while True:
                wait = self.resume_at - time.time()
                if wait > 0:
                    self.cond.wait(wait)
                elif self.limit is not None and self.active >= self.limit:
                    self.cond.wait(1.0)
                else:
                    self.active += 1
                    return

    def release(self, ok: bool) -> None:
        with self.cond:
            self.active = max(0, self.active - 1)
            if ok and self.limit is not None:
                self.streak += 1
                if self.streak >= 6:  # sustained successes: allow one more parallel request
                    self.limit, self.streak = self.limit + 1, 0
            self.cond.notify_all()

    def throttle(self, delay: float) -> int:
        with self.cond:
            current = self.limit if self.limit is not None else max(2, self.active)
            self.limit = max(1, current // 2)
            self.resume_at = max(self.resume_at, time.time() + delay)
            self.streak = 0
            self.cond.notify_all()
            return self.limit


_gates: Dict[str, _Gate] = {}
_gates_lock = threading.Lock()
_exhausted: Dict[str, float] = {}  # model -> skip it until this time
EXHAUSTED_RECHECK = 3600.0


def _gate(model: Optional[str]) -> _Gate:
    with _gates_lock:
        return _gates.setdefault(model or "", _Gate())


def exhausted(model: str) -> bool:
    return _exhausted.get(model, 0.0) > time.time()


def with_retry(fn: Callable[[], R], attempts: int = 8, base: float = 1.5, model: Optional[str] = None) -> R:
    """Call the API: wait out per-minute rate limits and transient errors; raise QuotaExhausted for daily quotas."""
    gate = _gate(model)
    for attempt in range(attempts):
        gate.acquire()
        ok = False
        try:
            result = fn()
            ok = True
            return result
        except Exception as exc:
            last = attempt == attempts - 1
            if is_rate_limited(exc):
                info = quota_info(exc)
                if info["daily"] and model:
                    _exhausted[model] = time.time() + EXHAUSTED_RECHECK
                    raise QuotaExhausted(model, info) from exc
                if last:
                    raise
                delay = min(90.0, info["retry_after"] or base * (2 ** attempt)) + random.uniform(0.5, 2.0)
                limit = gate.throttle(delay)
                _notify(f"Gemini rate limit on {model or 'the API'} ({info['quota_id'] or info['metric'] or 'requests per minute'}): "
                        f"pausing {delay:.0f}s, then continuing with {limit} parallel request{'s' if limit != 1 else ''}.")
                continue
            if last or not any(marker in f"{type(exc).__name__}: {exc}" for marker in RETRYABLE):
                raise
            time.sleep(min(30.0, base * (2 ** attempt)) + random.random())
        finally:
            gate.release(ok)
    raise RuntimeError("unreachable")  # pragma: no cover


def fallback_models(model: str, models: Sequence[Tuple[str, str]]) -> List[str]:
    """The chosen model, then the rest of the catalogue: used when a daily quota runs out."""
    return [model] + [name for name, _ in models if name != model]


def with_fallback(models: Sequence[str], call: Callable[[str], R]) -> R:
    """Run ``call(model)`` on the first model whose daily quota isn't used up, moving on when one runs out."""
    candidates = [m for m in models if not exhausted(m)] or list(models[:1])
    for index, name in enumerate(candidates):
        try:
            return call(name)
        except QuotaExhausted as exc:
            if index + 1 == len(candidates):
                raise
            _notify(f"{exc} Switching to {candidates[index + 1]}.")
    raise RuntimeError("no Gemini model available")  # pragma: no cover


def generate(gemini: Any, model: str, contents: Any, config: Any, fallbacks: Sequence[str] = ()) -> Any:
    """``generate_content`` with retries, falling back to ``fallbacks`` when a model's daily quota runs out.

    Some models reject the thinking setting (400 INVALID_ARGUMENT): retry once without it, so model
    aliases that move to a new generation keep working."""

    def attempt(name: str) -> Any:
        cfg = config
        if name != model and getattr(config, "thinking_config", None) is not None:
            cfg = config.model_copy(update={"thinking_config": thinking_off(name)})
        call = lambda c: with_retry(lambda: gemini.models.generate_content(model=name, contents=contents, config=c), model=name)  # noqa: E731
        try:
            return call(cfg)
        except Exception as exc:
            if "INVALID_ARGUMENT" in str(exc) and getattr(cfg, "thinking_config", None) is not None:
                return call(cfg.model_copy(update={"thinking_config": None}))
            raise

    return with_fallback([model, *[m for m in fallbacks if m != model]], attempt)


def run_parallel(fn: Callable[[T], R], items: List[T], workers: int) -> Iterator[Tuple[T, R]]:
    """Run ``fn`` over ``items`` with ``workers`` concurrent requests; yield results as they finish."""
    if not items:
        return
    with ThreadPoolExecutor(max_workers=max(1, min(int(workers), len(items)))) as pool:
        futures = {pool.submit(fn, item): item for item in items}
        for future in as_completed(futures):
            yield futures[future], future.result()


def thinking_off(model: str):
    """Minimal thinking for speed where the model allows it (Pro models require some thinking)."""
    from google.genai import types

    if "pro" in model:
        return None
    return types.ThinkingConfig(thinking_budget=0)


def validate_key(key: str) -> Dict[str, Any]:
    """Make one tiny request. Returns ``{"ok": True, "model", "latency_ms"}`` or ``{"ok": False, "error"}``."""
    key = (key or "").strip()
    if not key:
        return {"ok": False, "error": "Paste a Gemini API key first."}
    try:
        from google.genai import types
    except ImportError:
        return {"ok": False, "error": "The google-genai package is not installed (pip install google-genai)."}
    last_error: Optional[str] = None
    gemini = client(key)  # keep a reference: a garbage-collected client closes its connection mid-request
    for model in ("gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash"):
        started = time.time()
        try:
            response = generate(
                gemini,
                model,
                "Reply with the single word: ok",
                types.GenerateContentConfig(temperature=0, max_output_tokens=16, thinking_config=thinking_off(model)),
            )
            return {"ok": True, "model": model, "latency_ms": int((time.time() - started) * 1000), "reply": (response.text or "").strip()[:20]}
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if "API_KEY" in last_error or "API key" in last_error or "PERMISSION_DENIED" in last_error:
                break  # the key itself is the problem: other models won't help
    from dubby.errors import explain

    return {"ok": False, "error": explain(last_error or "unknown error").text()}
