"""Engine registry: maps engine ids to their implementing classes."""

from __future__ import annotations

import importlib
from functools import lru_cache
from typing import Dict, List, Type

from dubby.engines.base import Engine, EngineInfo

ENGINES: Dict[str, str] = {
    # ---------------------------------------------------------------- ASR
    "whisperx": "dubby.engines.asr.whisperx_engine:WhisperXEngine",
    "parakeet": "dubby.engines.asr.parakeet:ParakeetEngine",
    "qwen3-asr": "dubby.engines.asr.qwen:Qwen3ASREngine",
    "cohere-transcribe": "dubby.engines.asr.cohere:CohereTranscribeEngine",
    "cohere-transcribe-arabic": "dubby.engines.asr.cohere:CohereTranscribeArabicEngine",
    "coherex": "dubby.engines.asr.coherex_engine:CohereXEngine",
    "qwencleo": "dubby.engines.asr.qwen:QwenCleoEngine",
    "metro-asr": "dubby.engines.asr.metro:MetroASREngine",
    "gemini-asr": "dubby.engines.asr.gemini_asr:GeminiASREngine",
    # -------------------------------------------------------- translation
    "emhotob": "dubby.engines.translation.emhotob:EmhotobTranslator",
    "jisr": "dubby.engines.translation.jisr:JisrTranslator",
    "masrawy": "dubby.engines.translation.masrawy:MasrawyTranslator",
    "hunyuan-mt": "dubby.engines.translation.hunyuan:HunyuanMTTranslator",
    "nllb": "dubby.engines.translation.nllb:NLLBTranslator",
    "indictrans2": "dubby.engines.translation.indictrans2:IndicTrans2Translator",
    "arzen-llm": "dubby.engines.translation.arzen:ArzEnTranslator",
    "llm": "dubby.engines.translation.llm:LLMTranslator",
    "gemini-translate": "dubby.engines.translation.gemini_translate:GeminiTranslator",
    "passthrough": "dubby.engines.translation.passthrough:PassthroughTranslator",
    # ---------------------------------------------------------------- TTS
    "voicetut": "dubby.engines.tts.voicetut:VoiceTutEngine",
    "lahgtna-omnivoice": "dubby.engines.tts.lahgtna:LahgtnaOmniVoiceEngine",
    "omnivoice": "dubby.engines.tts.omnivoice:OmniVoiceBaseEngine",
    "qwen3-tts": "dubby.engines.tts.qwen3_tts:Qwen3TTSEngine",
    "indicf5": "dubby.engines.tts.indicf5:IndicF5Engine",
    "gemini-tts": "dubby.engines.tts.gemini_tts:GeminiTTSEngine",
    # ------------------------------------------------------ language ID
    "whisper-langid": "dubby.engines.langid.whisper_langid:WhisperLangIdEngine",
    # --------------------------------------------------------- captions
    "caption-align": "dubby.engines.align.caption_aligner:CaptionAligner",
    # --------------------------------------------------------- separation
    "demucs": "dubby.engines.separation.demucs_engine:DemucsEngine",
}


@lru_cache(maxsize=None)
def engine_class(engine_id: str) -> Type[Engine]:
    if engine_id not in ENGINES:
        raise KeyError(f"Unknown engine '{engine_id}'. Available: {', '.join(ENGINES)}")
    module_name, class_name = ENGINES[engine_id].split(":")
    return getattr(importlib.import_module(module_name), class_name)


def get_info(engine_id: str) -> EngineInfo:
    return engine_class(engine_id).info


def all_infos(kind: str | None = None) -> List[EngineInfo]:
    infos = [get_info(e) for e in ENGINES]
    return [i for i in infos if kind is None or i.kind == kind]
