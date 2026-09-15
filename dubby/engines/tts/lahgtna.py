from __future__ import annotations

from dubby.engines.base import EngineInfo
from dubby.engines.tts.omnivoice_base import OmniVoiceEngine, omnivoice_params


class LahgtnaOmniVoiceEngine(OmniVoiceEngine):
    info = EngineInfo(
        id="lahgtna-omnivoice",
        kind="tts",
        name="Lahgtna OmniVoice v2",
        family="core",
        description="لهجتنا — OmniVoice fine-tuned by oddadmix for 13 Arabic dialects incl. Egyptian. Diacritics (تشكيل) improve pronunciation. MSA via the 'arb' language id.",
        targets=["arz", "arb"],
        requires=["omnivoice"],
        install="pip install omnivoice",
        badges=["multi-dialect", "diacritics", "voice cloning"],
        links={"model": "https://huggingface.co/oddadmix/lahgtna-omnivoice-v2"},
        params=omnivoice_params("oddadmix/lahgtna-omnivoice-v2"),
    )
