from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict, List

from dubby import languages as L
from dubby.engines.base import EngineInfo
from dubby.engines.tts.omnivoice_base import OmniVoiceEngine, omnivoice_params
from dubby.workers.protocol import TaskContext


class VoiceTutEngine(OmniVoiceEngine):
    info = EngineInfo(
        id="voicetut",
        kind="tts",
        name="VoiceTut-TTS",
        family="core",
        description="OmniVoice fine-tuned on ~380 h of Egyptian podcasts. Natural Egyptian prosody, Arabic↔English code-switching, 17 studio voices, zero-shot cloning. MSA via the 'arb' language id; other languages run through the OmniVoice backbone.",
        targets=list(L.TARGET_CODES),
        requires=["omnivoice", "voicetut_tts"],
        install="pip install omnivoice voicetut-tts",
        badges=["Egyptian", "code-switching", "voice cloning"],
        links={"model": "https://huggingface.co/mohammedaly22/VoiceTut-TTS", "code": "https://github.com/MohammedAly22/VoiceTuT-TTS"},
        params=omnivoice_params("mohammedaly22/VoiceTut-TTS"),
    )

    def load(self, ctx: TaskContext) -> None:
        from voicetut_tts import VoiceTutTTS

        ctx.progress(0.02, f"Loading {self.params['model']}…")
        self.tts = VoiceTutTTS.from_pretrained(
            self.params["model"],
            device=self._device_map(),
            dtype="float16" if self.is_cuda else "float32",
        )
        self.model = self.tts.model
        # VoiceTut's built-in ArabicNormalizer is intentionally unused: the studio normalizes with dubby.text
        # (Egyptian = VoiceTut's rules without diacritics) before the text reaches this engine.
        self._prompts = OrderedDict()

    def presets(self) -> List[Dict[str, Any]]:
        return [s.to_public() for s in self.tts.list_speakers()] if getattr(self, "tts", None) else []
