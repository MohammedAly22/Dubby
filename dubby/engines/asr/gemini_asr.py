"""Google Gemini speech recognition.

Long audio is cut at silences into multi-minute chunks that are transcribed concurrently,
each returning sentence-level segments with timestamps (JSON). Word timings are either
estimated from word length (fast) or forced-aligned with wav2vec2 (precise).
"""

from __future__ import annotations

import io
import json
from typing import Any, Dict, List, Tuple

from dubby import languages as L
from dubby.engines import gemini_common as G
from dubby.engines.asr.common import align_words, load_audio, vad_regions
from dubby.engines.base import ASREngine, EngineInfo, ParamSpec, option
from dubby.workers.protocol import TaskContext, track

SR = 16000
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "segments": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {"start": {"type": "NUMBER"}, "end": {"type": "NUMBER"}, "text": {"type": "STRING"}},
                "required": ["start", "end", "text"],
            },
        }
    },
    "required": ["segments"],
}


def build_prompt(language: str, hint: str = "") -> str:
    name = L.get(language).prompt_name if language in L.LANGUAGES else language
    dialect = " Write Egyptian or other dialectal Arabic exactly as spoken, in Arabic script." if language == "ar" else ""
    context = f" Names and terms that may appear: {hint.strip()}." if hint and hint.strip() else ""
    return (
        f"Transcribe the speech in this audio verbatim. The main language is {name}.{dialect} "
        "Keep words the speaker says in another language (code-switching) in that language's own script, "
        "for example English words in Latin letters. Do not translate, summarize or correct grammar. "
        "Ignore music and non-speech sounds. Split the transcript into sentence-level segments of at most "
        "about 12 seconds, each with start and end times in seconds (decimals) measured from the beginning "
        f"of this audio clip.{context}"
    )


def group_regions(regions: List[Tuple[float, float]], max_seconds: float) -> List[Tuple[float, float]]:
    """Merge VAD regions into chunks no longer than ``max_seconds`` (cut only at silences)."""
    chunks: List[Tuple[float, float]] = []
    start = end = None
    for s, e in regions:
        if start is None:
            start, end = s, e
        elif e - start <= max_seconds:
            end = e
        else:
            chunks.append((start, end))
            start, end = s, e
    if start is not None:
        chunks.append((start, end))
    return chunks


def estimate_words(segment: Dict[str, Any], language: str) -> List[Dict[str, Any]]:
    """Spread the segment's duration over its words in proportion to their length."""
    tokens = L.tokenize(segment["text"], language) if language in L.LANGUAGES else segment["text"].split()
    if not tokens:
        return []
    weights = [max(1, len(t)) for t in tokens]
    total = float(sum(weights))
    start, span = float(segment["start"]), max(0.05, float(segment["end"]) - float(segment["start"]))
    words, cursor = [], start
    for token, weight in zip(tokens, weights):
        duration = span * weight / total
        words.append({"text": token, "start": round(cursor, 3), "end": round(cursor + duration, 3)})
        cursor += duration
    return words


class GeminiASREngine(ASREngine):
    info = EngineInfo(
        id="gemini-asr",
        kind="asr",
        name="Google Gemini (API)",
        family="cloud",
        description="Gemini transcribes long audio in parallel chunks with sentence timestamps. No GPU needed; handles code-switching and dialects. Uses your Gemini API key.",
        source_languages=list(L.SOURCE_CODES),
        requires=["google.genai", "soundfile"],
        install="pip install google-genai soundfile",
        badges=["cloud API", "parallel", "no GPU"],
        links={"api key": G.KEY_URL, "docs": "https://ai.google.dev/gemini-api/docs/audio"},
        params=[
            ParamSpec("model", "Model", "select", "gemini-flash-latest", G.model_options(G.TEXT_MODELS)),
            ParamSpec("word_timing", "Word timing", "select", "estimate", [
                option("estimate", "Estimate from word length (fast)"),
                option("align", "wav2vec2 forced alignment (precise, loads a model)"),
            ]),
            ParamSpec("chunk_seconds", "Chunk length (s)", "number", 240, min=30, max=600, step=30, help="Audio is cut at silences into chunks of this size"),
            ParamSpec("parallel", "Parallel requests", "number", 6, min=1, max=16, step=1, help="Chunks transcribed at the same time"),
            ParamSpec("auto_fallback", "Switch model when a daily quota runs out", "bool", True, help="Per-minute limits are waited out automatically; when a model's daily quota is used up, continue with the next Gemini model"),
            ParamSpec("hint", "Names & terms", "text", "", help="Optional: names or jargon to spell correctly"),
        ],
    )

    def load(self, ctx: TaskContext) -> None:
        G.api_key()  # fail fast with a clear message when no key is configured
        self.client = G.client()

    def transcribe(self, audio_path: str, language: str, ctx: TaskContext) -> List[Dict[str, Any]]:
        import soundfile as sf
        from google.genai import types

        audio = load_audio(audio_path)
        total = len(audio) / SR
        ctx.progress(0.03, "Finding speech regions…")
        try:
            regions = vad_regions(audio, max_chunk=25.0)
        except Exception as exc:  # VAD is an optimisation; fixed windows still work
            ctx.log(f"Voice activity detection unavailable ({exc}); using fixed windows.", "warning")
            regions = [(float(t), min(total, t + 25.0)) for t in range(0, int(total) + 1, 25)]
        chunks = group_regions(regions, float(self.params.get("chunk_seconds") or 240))
        if not chunks:
            return []
        model = self.params.get("model") or "gemini-flash-latest"
        G.set_notifier(lambda message: ctx.log(message, "warning"))
        prompt = build_prompt(language, str(self.params.get("hint") or ""))
        config = types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=SCHEMA, temperature=0, thinking_config=G.thinking_off(model)
        )

        def run(chunk: Tuple[float, float]) -> List[Dict[str, Any]]:
            a = max(0, int((chunk[0] - 0.3) * SR))
            b = min(len(audio), int((chunk[1] + 0.3) * SR))
            offset, duration = a / SR, (b - a) / SR
            buffer = io.BytesIO()
            sf.write(buffer, audio[a:b], SR, format="FLAC")
            part = types.Part.from_bytes(data=buffer.getvalue(), mime_type="audio/flac")
            with track("asr", f"Gemini ASR · part {chunks.index(chunk) + 1}/{len(chunks)}", model=model, seconds=round(duration, 1)):
                fallbacks = G.fallback_models(model, G.TEXT_MODELS) if self.params.get("auto_fallback", True) else []
                response = G.generate(self.client, model, [part, prompt], config, fallbacks)
            data = json.loads(response.text or "{}")
            out = []
            for seg in data.get("segments", []):
                text = str(seg.get("text", "")).strip()
                if not text:
                    continue
                start = max(0.0, min(duration, float(seg.get("start") or 0)))
                end = max(start + 0.2, min(duration, float(seg.get("end") or start)))
                out.append({"start": round(offset + start, 3), "end": round(offset + end, 3), "text": text})
            return out

        segments: List[Dict[str, Any]] = []
        ctx.progress(0.06, f"Transcribing {len(chunks)} part{'s' if len(chunks) > 1 else ''} with {model}…")
        for done, (_, result) in enumerate(G.run_parallel(run, chunks, int(self.params.get("parallel") or 6)), start=1):
            segments.extend(result)
            segments.sort(key=lambda s: s["start"])
            ctx.result("asr_partial", {"segments": [dict(s, words=[]) for s in segments], "replace": True})
            ctx.progress(0.06 + 0.74 * done / len(chunks), f"Transcribed {done}/{len(chunks)} parts")

        # keep segments from overlapping after chunk offsets are applied
        for prev, cur in zip(segments, segments[1:]):
            if cur["start"] < prev["end"]:
                prev["end"] = max(prev["start"] + 0.2, cur["start"])

        if self.params.get("word_timing") == "align":
            return align_words([dict(s, words=[]) for s in segments], audio, language, self.device, ctx)
        for seg in segments:
            seg["words"] = estimate_words(seg, language)
        return segments
