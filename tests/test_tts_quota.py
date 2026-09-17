"""A Gemini daily quota pauses voice generation: clips so far are kept, the rest wait (no network)."""

from pathlib import Path

import pytest

pytest.importorskip("google.genai")

from dubby.engines import gemini_common as G  # noqa: E402
from dubby.engines.base import TTSItem  # noqa: E402
from dubby.engines.tts import gemini_tts  # noqa: E402


class Ctx:
    def __init__(self):
        self.results, self.logs = [], []

    def progress(self, *a, **k):
        pass

    def log(self, message, level="info"):
        self.logs.append((level, message))

    def result(self, kind, data):
        self.results.append((kind, data))

    def request(self, *a, **k):
        import contextlib

        return contextlib.nullcontext()


@pytest.fixture(autouse=True)
def fresh():
    G._gates.clear()
    G._exhausted.clear()
    G._exhausted_info.clear()
    yield
    G.set_notifier(None)


def test_daily_quota_stops_the_run_on_the_chosen_model(tmp_path, monkeypatch):
    models_used, calls = set(), {"n": 0}

    def fake_synthesize(client, model, voice, prompt):
        models_used.add(model)
        return G.with_retry(lambda: request(), model=model)

    # a real 429 payload for the daily quota
    from google.genai import errors

    daily = errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
            {"quotaMetric": "generativelanguage.googleapis.com/generate_requests_per_model", "quotaId": "GenerateRequestsPerDayPerProjectPerModel", "quotaValue": "100"}]}]}})

    def request():
        calls["n"] += 1
        if calls["n"] > 3:
            raise daily
        return b"\x00\x00" * 2400, 24000

    monkeypatch.setattr(gemini_tts, "synthesize_pcm", fake_synthesize)
    engine = gemini_tts.GeminiTTSEngine("cpu", {"model": "gemini-3.1-flash-tts-preview", "parallel": 1})
    engine.client = object()
    items = [TTSItem(id=f"s{i}", text="مرحبا", out_path=str(tmp_path / f"s{i}.wav"), duration=1.0) for i in range(8)]
    ctx = Ctx()
    voiced = [item.id for item, _ in engine.synthesize(items, "arz", ctx)]

    assert voiced == ["s0", "s1", "s2"]
    assert models_used == {"gemini-3.1-flash-tts-preview"}  # never switched model
    assert calls["n"] == 4  # the remaining clips were not sent once the quota was hit
    quota = [data for kind, data in ctx.results if kind == "tts_quota"]
    assert len(quota) == 1 and quota[0]["paused"] == ["s3", "s4", "s5", "s6", "s7"] and quota[0]["limit"] == "100"
    assert "limited to 100 requests per day" in quota[0]["message"]
    assert not [1 for kind, _ in ctx.results if kind == "tts_error"]
    assert any(level == "warning" and "3 of 8" in message for level, message in ctx.logs)


def test_studio_pauses_the_stage_and_offers_render(tmp_path, monkeypatch):
    monkeypatch.setenv("DUBBY_HOME", str(tmp_path / "home"))
    from dubby.config import load_settings
    from dubby.core.studio import Studio
    from dubby.media import pot
    from dubby.schemas import Project, Segment

    pot.warm_up = lambda *a, **k: None
    studio = Studio(load_settings(reload=True))
    try:
        p = Project(id="q1", title="Quota")
        p.settings.target = "arz"
        p.settings.tts.engine = "gemini-tts"
        p.segments = [Segment(id=f"s{i}", start=i, end=i + 1, text="hi", translation="أهلا") for i in range(4)]
        studio.store.save(p)
        monkeypatch.setattr(studio, "_require_available", lambda engine_id: None)
        submitted = []
        monkeypatch.setattr(studio.jobs, "submit", lambda job: submitted.append(job) or job)
        events = []
        studio.bus.subscribe(events.append)

        studio.run_tts("q1")
        job = submitted[0]
        items = job.payload["items"]
        job.handlers.on_start()
        for item in items[:2]:
            wav = Path(item["out_path"])
            wav.parent.mkdir(parents=True, exist_ok=True)
            wav.write_bytes(b"RIFF")
            job.handlers.on_result("segment_audio", {"id": item["id"], "path": str(wav), "duration": 0.9})
        job.handlers.on_result("tts_quota", {"model": "gemini-3.1-flash-tts-preview", "limit": "100", "paused": ["s2", "s3"], "voiced": 2, "total": 4,
                                             "message": "gemini-3.1-flash-tts-preview is limited to 100 requests per day on your Gemini plan, and today's quota is used up."})
        job.handlers.on_done({})

        project = studio.store.get("q1")
        st = project.stages["tts"]
        assert st.status == "paused" and "2/4" in st.message and "limited to 100 requests per day" in st.error
        assert [s.tts.status for s in project.segments] == ["done", "done", "pending", "pending"]
        quota = [e for e in events if e.get("type") == "quota"]
        assert quota and quota[0]["generated"] == 2 and quota[0]["remaining"] == 2 and quota[0]["voiced_total"] == 2
        # the Logs drawer gets the same yellow pause line as the terminal
        lines = [r for r in studio.bus.console_lines if r.get("tone") == "warning" and "paused" in "".join(s["t"] for s in r.get("spans", []))]
        assert lines and any(s["c"] == "yellow" for s in lines[0]["spans"])
    finally:
        studio.shutdown()
