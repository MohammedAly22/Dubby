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
    # -------------------------------------------------------- translation
    "emhotob": "dubby.engines.translation.emhotob:EmhotobTranslator",
    "jisr": "dubby.engines.translation.jisr:JisrTranslator",
    "masrawy": "dubby.engines.translation.masrawy:MasrawyTranslator",
    "llm": "dubby.engines.translation.llm:LLMTranslator",
    # ---------------------------------------------------------------- TTS
    "voicetut": "dubby.engines.tts.voicetut:VoiceTutEngine",
    "lahgtna-omnivoice": "dubby.engines.tts.lahgtna:LahgtnaOmniVoiceEngine",
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
