from __future__ import annotations

from dubby import languages as L
from dubby.engines.base import EngineInfo
from dubby.engines.tts.omnivoice_base import OmniVoiceEngine, omnivoice_params


class OmniVoiceBaseEngine(OmniVoiceEngine):
    info = EngineInfo(
        id="omnivoice",
        kind="tts",
        name="OmniVoice",
        family="core",
        description="k2-fsa OmniVoice base model: zero-shot voice cloning in 646 languages with exact duration control. Huge data for English, Chinese, Japanese, Spanish, French and Italian; weak for Hindi (117 h).",
        targets=list(L.TARGET_CODES),
        requires=["omnivoice"],
        install="pip install omnivoice",
        badges=["646 languages", "voice cloning", "duration control"],
        links={"model": "https://huggingface.co/k2-fsa/OmniVoice", "languages": "https://github.com/k2-fsa/OmniVoice/blob/master/docs/languages.md"},
        params=omnivoice_params("k2-fsa/OmniVoice"),
    )
