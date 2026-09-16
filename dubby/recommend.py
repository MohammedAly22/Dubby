"""Ranked engine recommendations per language and stage.

The rankings encode what we know about each model (training data, published
benchmarks, alignment support). They are filtered against each engine's declared
language support, so a recommendation is always runnable for the pair.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set

from dubby import languages as L
from dubby.engines.registry import ENGINES, get_info


@dataclass
class Recommendation:
    engine: str
    reason: str
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def R(engine: str, reason: str, **params: Any) -> Recommendation:
    return Recommendation(engine, reason, params)


_EUROPEAN_ASR = [
    R("qwen3-asr", "SOTA multilingual accuracy; the Qwen3 forced aligner gives word timings for this language"),
    R("parakeet", "Parakeet TDT v3 covers 25 European languages with native word timestamps, very fast"),
    R("cohere-transcribe", "Top of the Open ASR leaderboard; wav2vec2 word alignment"),
    R("whisperx", "Whisper large-v3 with a dedicated wav2vec2 aligner", model="large-v3"),
]

ASR: Dict[str, List[Recommendation]] = {
    "en": [
        R("whisperx", "Batched Whisper large-v3-turbo with precise wav2vec2 word timings", model="large-v3-turbo"),
        R("parakeet", "Fastest English ASR with native word timestamps"),
        R("qwen3-asr", "SOTA accuracy with the Qwen3 forced aligner"),
        R("cohere-transcribe", "Top of the Open ASR leaderboard"),
    ],
    "ar": [
        R("cohere-transcribe-arabic", "Best open Arabic ASR across dialects (Egyptian, Gulf, Levantine) and code-switching"),
        R("qwencleo", "SOTA Egyptian Arabic fine-tune of Qwen3-ASR (≈ half the base WER)"),
        R("coherex", "Cohere Transcribe Arabic inside a WhisperX-style VAD + alignment pipeline"),
        R("qwen3-asr", "Strong general Arabic ASR"),
        R("whisperx", "Whisper large-v3 with Arabic wav2vec2 alignment", model="large-v3"),
        R("metro-asr", "Tiny Egyptian CTC model — fastest option on CPU"),
    ],
    "es": _EUROPEAN_ASR,
    "fr": _EUROPEAN_ASR,
    "it": _EUROPEAN_ASR,
    "hi": [
        R("qwen3-asr", "Strong Hindi accuracy; words aligned with a Hindi wav2vec2 model"),
        R("whisperx", "Whisper large-v3 with Hindi wav2vec2 alignment", model="large-v3"),
    ],
    "zh": [
        R("qwen3-asr", "Best open Mandarin ASR, with character-level forced alignment"),
        R("cohere-transcribe", "Very accurate Chinese transcription with wav2vec2 alignment"),
        R("whisperx", "Whisper large-v3 with a Chinese wav2vec2 aligner", model="large-v3"),
    ],
    "ja": [
        R("qwen3-asr", "Best open Japanese ASR, with character-level forced alignment"),
        R("whisperx", "Kotoba-Whisper v2 (Japanese-specialised Whisper) with wav2vec2 alignment", model="kotoba-tech/kotoba-whisper-v2.0-faster"),
        R("cohere-transcribe", "Accurate Japanese transcription with wav2vec2 alignment"),
    ],
}

TTS: Dict[str, List[Recommendation]] = {
    "arz": [
        R("voicetut", "Fine-tuned on ~380 h of Egyptian podcasts: natural Egyptian prosody and code-switching"),
        R("lahgtna-omnivoice", "OmniVoice fine-tuned on 13 Arabic dialects; add tashkeel for best pronunciation"),
        R("omnivoice", "Base OmniVoice has only ~23 h of Egyptian data — use the fine-tunes above when possible"),
    ],
    "arb": [
        R("lahgtna-omnivoice", "Multi-dialect Arabic fine-tune, handles fusha with diacritics well"),
        R("voicetut", "Same OmniVoice backbone switched to the Standard Arabic (arb) language id"),
        R("omnivoice", "Base OmniVoice: ~1.5k h of Standard Arabic training data"),
    ],
    "en": [
        R("omnivoice", "206k h of English training data, zero-shot cloning and exact duration control"),
        R("qwen3-tts", "Qwen3-TTS voice cloning with strong expressiveness (fit at render time)"),
    ],
    "zh": [
        R("omnivoice", "111k h of Chinese training data, duration control and text normalization"),
        R("qwen3-tts", "Qwen3-TTS: excellent Mandarin cloning and prosody"),
    ],
    "ja": [
        R("omnivoice", "37k h of Japanese training data with duration control"),
        R("qwen3-tts", "Qwen3-TTS: natural Japanese voice cloning"),
    ],
    "es": [
        R("omnivoice", "27.6k h of Spanish training data with duration control"),
        R("qwen3-tts", "Qwen3-TTS Spanish voice cloning"),
    ],
    "fr": [
        R("omnivoice", "23.7k h of French training data with duration control"),
        R("qwen3-tts", "Qwen3-TTS French voice cloning"),
    ],
    "it": [
        R("omnivoice", "9.4k h of Italian training data with duration control"),
        R("qwen3-tts", "Qwen3-TTS Italian voice cloning"),
    ],
    "hi": [
        R("indicf5", "AI4Bharat F5-TTS trained on Indian languages — the most natural open Hindi voice cloning"),
        R("omnivoice", "Works, but OmniVoice saw only ~117 h of Hindi: expect weaker pronunciation"),
    ],
}


def _translation(source: str, target: str) -> List[Recommendation]:
    if L.same_language(source, target) and not (L.is_arabic(target) and source == "ar"):
        return [R("passthrough", "Same language — keep the transcript and only re-voice it")]
    src, tgt = L.get(source).name, L.get(target).name
    recs: List[Recommendation] = []
    if target == "arz":
        if source in ("en", "ar"):
            recs.append(R("emhotob", "oddadmix model trained for natural Egyptian colloquial translation"))
        if source == "en":
            recs += [R("masrawy", "English→Egyptian Marian fine-tune (chrF 66.7)"), R("jisr", "Multi-dialect Marian with the Egyptian tag")]
        recs += [R("llm", "Context-aware LLM prompted for spoken Egyptian Arabic"), R("nllb", "NLLB-200 has a native Egyptian Arabic (arz_Arab) target")]
    elif target == "arb":
        if source in ("en", "ar"):
            recs.append(R("emhotob", "oddadmix English/Egyptian→MSA model (BLEU 46 on En→MSA)"))
        recs.append(R("hunyuan-mt", "WMT25-winning 7B translator with strong Arabic"))
        if source == "en":
            recs.append(R("jisr", "Tiny Marian model with the MSA tag"))
        recs += [R("nllb", "Fast 200-language baseline"), R("llm", "Context-aware LLM translation")]
    elif target == "hi":
        if source == "en":
            recs.append(R("indictrans2", "AI4Bharat IndicTrans2: state-of-the-art English→Hindi"))
        recs += [R("hunyuan-mt", f"WMT25-winning 7B translator for {src}→Hindi"), R("nllb", "Fast 200-language baseline"), R("llm", "Context-aware LLM translation")]
    elif source == "ar" and target == "en":
        recs += [
            R("arzen-llm", "Llama-3-8B fine-tuned on code-switched Egyptian Arabic → English (ArzEn-LLM); fits a 16 GB T4 in 4-bit"),
            R("llm", "Context-aware 4-bit LLM that keeps names and English words intact"),
            R("nllb", "Reads Egyptian Arabic (arz_Arab) directly; fast and light", arabic_variety="arz_Arab"),
            R("hunyuan-mt", "WMT25-winning 7B translator; loads in 4-bit on 16 GB GPUs"),
        ]
    else:
        recs.append(R("hunyuan-mt", f"WMT25-winning 7B model — strongest open translator for {src}→{tgt} (4-bit on 16 GB GPUs)"))
        llm_reason = "Qwen instruct LLM — excellent for Chinese and Japanese, uses previous lines as context" if target in ("zh", "ja") else "Context-aware LLM translation that keeps spoken length"
        nllb_params = {"arabic_variety": "arz_Arab"} if source == "ar" else {}
        recs += [R("llm", llm_reason), R("nllb", "Fast 200-language baseline, runs on small GPUs", **nllb_params)]
    return recs


def _supports(engine_id: str, kind: str, source: str, target: str) -> bool:
    if engine_id not in ENGINES:
        return False
    info = get_info(engine_id)
    if info.kind != kind:
        return False
    if kind == "asr":
        return source in info.source_languages
    if kind == "tts":
        return target in info.targets
    if engine_id == "passthrough":
        return L.same_language(source, target)
    return source in info.source_languages and target in info.targets


_GEMINI = {"enabled": False}


def set_gemini(enabled: bool) -> None:
    """With a valid Gemini API key, Gemini becomes the top translation pick for every language pair."""
    _GEMINI["enabled"] = bool(enabled)


def recommendations(kind: str, source: str, target: str) -> List[Recommendation]:
    if kind == "asr":
        recs = ASR.get(source, [])
    elif kind == "tts":
        recs = TTS.get(target, [])
    elif kind == "translation":
        recs = _translation(source, target)
        if _GEMINI["enabled"] and not (recs and recs[0].engine == "passthrough"):
            recs = [R("gemini-translate", "Your Gemini API key: fast, context-aware translation for any language pair")] + recs
    else:
        recs = []
    return [r for r in recs if _supports(r.engine, kind, source, target)]


def best(kind: str, source: str, target: str, available: Optional[Set[str]] = None) -> Optional[Recommendation]:
    recs = recommendations(kind, source, target)
    if available is not None:
        ready = [r for r in recs if r.engine in available]
        if ready:
            return ready[0]
    return recs[0] if recs else None


def matrix() -> Dict[str, Any]:
    return {
        "asr": {s: [r.to_dict() for r in recommendations("asr", s, "en")] for s in L.SOURCE_CODES},
        "tts": {t: [r.to_dict() for r in recommendations("tts", "en", t)] for t in L.TARGET_CODES},
        "translation": {f"{s}>{t}": [r.to_dict() for r in recommendations("translation", s, t)] for s in L.SOURCE_CODES for t in L.TARGET_CODES},
    }


def supports(engine_id: str, kind: str, source: str, target: str) -> bool:
    return _supports(engine_id, kind, source, target)


__all__: Iterable[str] = ["Recommendation", "recommendations", "best", "matrix", "supports"]
