"""Shared Google Gemini helpers: client, retries with backoff, concurrency and key validation.

Gemini engines run in the CPU-only ``cloud`` family: they call the Gemini API instead of
loading weights, so they never compete with local models for VRAM. The API key reaches the
worker through the ``GEMINI_API_KEY`` environment variable (set from Settings).
"""

from __future__ import annotations

import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, TypeVar

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

RETRYABLE = ("429", "RESOURCE_EXHAUSTED", "500", "502", "503", "504", "UNAVAILABLE", "DEADLINE_EXCEEDED",
             "INTERNAL", "timed out", "Timeout", "Connection reset", "RemoteProtocolError")

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


def with_retry(fn: Callable[[], R], attempts: int = 6, base: float = 1.5) -> R:
    """Retry rate limits and transient server errors with exponential backoff + jitter."""
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:
            text = f"{type(exc).__name__}: {exc}"
            if attempt == attempts - 1 or not any(marker in text for marker in RETRYABLE):
                raise
            time.sleep(min(30.0, base * (2 ** attempt)) + random.random())
    raise RuntimeError("unreachable")  # pragma: no cover


def generate(gemini: Any, model: str, contents: Any, config: Any) -> Any:
    """``generate_content`` with retries. Some models reject the thinking setting (400 INVALID_ARGUMENT):
    retry once without it, so model aliases that move to a new generation keep working."""
    call = lambda cfg: with_retry(lambda: gemini.models.generate_content(model=model, contents=contents, config=cfg))  # noqa: E731
    try:
        return call(config)
    except Exception as exc:
        if "INVALID_ARGUMENT" in str(exc) and getattr(config, "thinking_config", None) is not None:
            return call(config.model_copy(update={"thinking_config": None}))
        raise


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
