"""Gemini rate limits: per-minute 429s are waited out, a daily quota stops the run (no network)."""

import threading
import time

import pytest

pytest.importorskip("google.genai")
from google.genai import errors  # noqa: E402

from dubby.engines import gemini_common as G  # noqa: E402


def rate_error(quota_id: str, retry: str = "0.2s", limit: str = "10") -> errors.ClientError:
    return errors.ClientError(429, {"error": {
        "code": 429,
        "status": "RESOURCE_EXHAUSTED",
        "message": f"You exceeded your current quota. Quota exceeded for metric: generativelanguage.googleapis.com/generate_requests_per_model, limit: {limit}",
        "details": [
            {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
                {"quotaMetric": "generativelanguage.googleapis.com/generate_requests_per_model", "quotaId": quota_id,
                 "quotaDimensions": {"model": "gemini-3.1-flash-tts-preview"}, "quotaValue": limit}]},
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry},
        ],
    }})


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    G._gates.clear()
    G._exhausted.clear()
    G._exhausted_info.clear()
    monkeypatch.setattr(G.random, "uniform", lambda a, b: 0.0)  # no jitter: keep the tests fast
    yield
    G.set_notifier(None)


def test_quota_info_reads_structured_details():
    info = G.quota_info(rate_error("GenerateRequestsPerDayPerProjectPerModel", "37s", "100"))
    assert info["daily"] and info["retry_after"] == 37.0 and info["limit"] == "100"
    minute = G.quota_info(rate_error("GenerateRequestsPerMinutePerProjectPerModel"))
    assert not minute["daily"] and minute["retry_after"] == 0.2


def test_quota_info_from_plain_text():
    info = G.quota_info(RuntimeError("429 RESOURCE_EXHAUSTED. quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier' Please retry in 12.5s."))
    assert info["daily"] and info["retry_after"] == 12.5


def test_per_minute_limit_is_waited_out_and_concurrency_halved():
    calls, notes = {"n": 0}, []
    G.set_notifier(notes.append)

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise rate_error("GenerateRequestsPerMinutePerProjectPerModel", "0.1s")
        return "audio"

    started = time.time()
    assert G.with_retry(flaky, model="tts-a") == "audio"
    assert calls["n"] == 3 and time.time() - started >= 0.2
    assert G._gates["tts-a"].limit == 1 and len(notes) == 2 and "pausing" in notes[0]


def test_daily_quota_stops_and_fails_fast_without_switching_model():
    calls = {"n": 0}

    def request():
        calls["n"] += 1
        raise rate_error("GenerateRequestsPerDayPerProjectPerModel", limit="100")

    with pytest.raises(G.QuotaExhausted) as caught:
        G.with_retry(request, model="gemini-3.1-flash-tts-preview")
    assert calls["n"] == 1 and G.exhausted("gemini-3.1-flash-tts-preview")
    assert "limited to 100 requests per day" in str(caught.value)
    # later calls in the same run don't hit the API again
    with pytest.raises(G.QuotaExhausted):
        G.with_retry(request, model="gemini-3.1-flash-tts-preview")
    assert calls["n"] == 1
    assert not hasattr(G, "with_fallback")


def test_quota_error_is_explained():
    with pytest.raises(G.QuotaExhausted) as caught:
        G.with_retry(lambda: (_ for _ in ()).throw(rate_error("GenerateRequestsPerDayPerProjectPerModel")), model="tts-b")
    from dubby.errors import explain

    explained = explain(caught.value).text()
    assert "daily quota" in explained and "credits" in explained


def test_parallel_callers_share_the_cooldown():
    """A fake API that allows 2 requests in flight: every thread still completes."""
    lock, state = threading.Lock(), {"inflight": 0, "rejections": 0}

    def request():
        with lock:
            if state["inflight"] >= 2:
                state["rejections"] += 1
                raise rate_error("GenerateRequestsPerMinutePerProjectPerModel", "0.05s")
            state["inflight"] += 1
        time.sleep(0.02)
        with lock:
            state["inflight"] -= 1
        return "ok"

    results = list(G.run_parallel(lambda i: G.with_retry(request, model="tts-p", attempts=12), list(range(16)), 8))
    assert len(results) == 16 and all(r == "ok" for _, r in results)
