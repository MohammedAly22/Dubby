"""Google Gemini text-to-speech with its 30 prebuilt voices, generated in parallel.

Gemini TTS doesn't clone a reference voice: pick one of the preset voices instead. A short
style instruction (dialect, tone, pace) is sent with each line; clips are fitted to their
slots at render time.
"""

from __future__ import annotations

import os
import re
import wave
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from dubby import languages as L
from dubby.engines import gemini_common as G
from dubby.engines.base import EngineInfo, ParamSpec, TTSEngine, TTSItem, option
from dubby.engines.tts.omnivoice_base import normalize_param
from dubby.workers.protocol import TaskContext, track

# (name, style, gender) — Gemini's prebuilt voices
VOICES: List[Tuple[str, str, str]] = [
    ("Kore", "Firm", "female"), ("Zephyr", "Bright", "female"), ("Leda", "Youthful", "female"), ("Aoede", "Breezy", "female"),
    ("Callirrhoe", "Easy-going", "female"), ("Autonoe", "Bright", "female"), ("Despina", "Smooth", "female"),
    ("Erinome", "Clear", "female"), ("Laomedeia", "Upbeat", "female"), ("Achernar", "Soft", "female"),
    ("Gacrux", "Mature", "female"), ("Pulcherrima", "Forward", "female"), ("Vindemiatrix", "Gentle", "female"),
    ("Sulafat", "Warm", "female"),
    ("Puck", "Upbeat", "male"), ("Charon", "Informative", "male"), ("Fenrir", "Excitable", "male"), ("Orus", "Firm", "male"),
    ("Enceladus", "Breathy", "male"), ("Iapetus", "Clear", "male"), ("Umbriel", "Easy-going", "male"),
    ("Algieba", "Smooth", "male"), ("Algenib", "Gravelly", "male"), ("Rasalgethi", "Informative", "male"),
    ("Alnilam", "Firm", "male"), ("Schedar", "Even", "male"), ("Achird", "Friendly", "male"),
    ("Zubenelgenubi", "Casual", "male"), ("Sadachbia", "Lively", "male"), ("Sadaltager", "Knowledgeable", "male"),
]
VOICE_NAMES = {v[0] for v in VOICES}

SAMPLE_TEXT = {
    "arz": "أهلا بيك! أنا صوت من أصوات جيميناي، وجاهز أدبلج الفيديو بتاعك بالمصري.",
    "arb": "مرحبا! أنا أحد أصوات جيميناي، وجاهز لدبلجة الفيديو الخاص بك.",
    "en": "Hi! I'm one of Gemini's voices, ready to dub your video.",
    "es": "¡Hola! Soy una de las voces de Gemini, lista para doblar tu vídeo.",
    "fr": "Bonjour ! Je suis l'une des voix de Gemini, prête à doubler votre vidéo.",
    "it": "Ciao! Sono una delle voci di Gemini, pronta a doppiare il tuo video.",
    "hi": "नमस्ते! मैं Gemini की आवाज़ों में से एक हूँ, आपके वीडियो को डब करने के लिए तैयार।",
    "zh": "你好！我是 Gemini 的声音之一，准备好为你的视频配音了。",
    "ja": "こんにちは！Gemini の声のひとつです。あなたの動画を吹き替えます。",
}


def default_style(target: str) -> str:
    if target == "arz":
        return "Say in natural, warm Egyptian Arabic with a Cairene accent, like a professional dubbing actor:"
    if target == "arb":
        return "Say in clear, fluent Modern Standard Arabic, like a professional documentary narrator:"
    name = L.get(target).prompt_name if target in L.LANGUAGES else target
    return f"Say in natural, expressive {name}, like a professional dubbing actor:"


def synthesize_pcm(client: Any, model: str, voice: str, prompt: str) -> Tuple[bytes, int]:
    from google.genai import types

    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))),
    )
    response = G.with_retry(lambda: client.models.generate_content(model=model, contents=prompt, config=config), model=model)
    part = response.candidates[0].content.parts[0].inline_data
    rate = re.search(r"rate=(\d+)", part.mime_type or "")
    return part.data, int(rate.group(1)) if rate else 24000


def write_wav(path: str, pcm: bytes, rate: int) -> float:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(pcm)
    return len(pcm) / 2 / rate


class GeminiTTSEngine(TTSEngine):
    info = EngineInfo(
        id="gemini-tts",
        kind="tts",
        name="Google Gemini TTS (API)",
        family="cloud",
        description="Gemini speech with 30 preset voices and style control (dialect, tone, pace). All clips are generated in parallel — no GPU and no reference voice needed. Uses your Gemini API key.",
        targets=list(L.TARGET_CODES),
        requires=["google.genai"],
        install="pip install google-genai",
        badges=["cloud API", "30 voices", "parallel"],
        links={"voices": "https://ai.google.dev/gemini-api/docs/speech-generation#voices", "api key": G.KEY_URL},
        params=[
            ParamSpec("voice", "Voice", "select", "Kore", [option(name, f"{name} — {style} ({gender})") for name, style, gender in VOICES]),
            ParamSpec("model", "Model", "select", G.TTS_MODELS[0][0], G.model_options(G.TTS_MODELS)),
            ParamSpec("style", "Style instruction", "text", "", help="Empty = automatic for the dub language, e.g. “Say in natural Egyptian Arabic…”"),
            ParamSpec("pace_hint", "Aim for the slot length", "bool", True, help="Ask for a pace that fits each segment's duration"),
            ParamSpec("parallel", "Parallel requests", "number", 4, min=1, max=16, step=1, help="Lowered automatically while Gemini rate-limits the model"),
            normalize_param(),
        ],
    )

    def load(self, ctx: TaskContext) -> None:
        G.api_key()
        self.client = G.client()

    def _prompt(self, item: TTSItem, target: str) -> str:
        style = str(self.params.get("style") or "").strip() or default_style(target)
        if self.params.get("pace_hint", True) and item.duration:
            style = f"{style.rstrip(':')} (pace it to last about {item.duration:.1f} seconds):"
        return f"{style}\n{item.text}"

    def synthesize(self, items: Sequence[TTSItem], target: str, ctx: TaskContext) -> Iterator[Tuple[TTSItem, float]]:
        voice = self.params.get("voice") if self.params.get("voice") in VOICE_NAMES else "Kore"
        model = self.params.get("model") or G.TTS_MODELS[0][0]
        items = list(items)
        parallel = int(self.params.get("parallel") or 4)
        G.set_notifier(lambda message: ctx.log(message, "warning"))
        ctx.result("tts_running", {"ids": [it.id for it in items[:parallel]]})
        # the daily quota ends the run: the remaining clips are paused, never sent to another model
        stopped: Dict[str, Any] = {}

        def run(item: TTSItem) -> Optional[float]:
            if stopped:
                return None
            try:
                with track("tts", f"Gemini TTS · clip {item.id}", model=model, voice=voice, chars=len(item.text)):
                    pcm, rate = synthesize_pcm(self.client, model, voice, self._prompt(item, target))
                return write_wav(item.out_path, pcm, rate)
            except G.QuotaExhausted as exc:
                stopped.setdefault("info", exc.info)
                return None
            except Exception as exc:
                ctx.result("tts_error", {"id": item.id, "error": f"{type(exc).__name__}: {exc}"[:500]})
                return None

        voiced = set()
        for item, duration in G.run_parallel(run, items, parallel):
            if duration is not None:
                voiced.add(item.id)
                yield item, duration
        if stopped:
            info = stopped["info"]
            paused = [it.id for it in items if it.id not in voiced]
            ctx.log(f"{G.quota_sentence(model, info)} Stopped with {len(voiced)} of {len(items)} clips generated.", "warning")
            ctx.result("tts_quota", {"model": model, "limit": info.get("limit"), "quota_id": info.get("quota_id"),
                                     "message": G.quota_sentence(model, info), "paused": paused, "voiced": len(voiced), "total": len(items)})


def preview_voice(voice: str, language: str, out_path: str, key: str, model: Optional[str] = None) -> str:
    """Generate (once) a short sample of a preset voice in the dub language, for the voice picker."""
    if voice not in VOICE_NAMES:
        raise ValueError(f"Unknown Gemini voice '{voice}'")
    if not os.path.exists(out_path):
        text = SAMPLE_TEXT.get(language, SAMPLE_TEXT["en"])
        gemini = G.client(key)  # keep a reference for the whole request
        pcm, rate = synthesize_pcm(gemini, model or G.TTS_MODELS[0][0], voice, f"{default_style(language)}\n{text}")
        write_wav(out_path, pcm, rate)
    return out_path
