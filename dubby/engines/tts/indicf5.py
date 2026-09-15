"""AI4Bharat IndicF5 (Hindi voice cloning). Runs in the `indic` family (transformers < 4.50)."""

from __future__ import annotations

import os
from typing import Iterator, Sequence, Tuple

from dubby.engines.base import EngineInfo, ParamSpec, TTSEngine, TTSItem
from dubby.workers.protocol import TaskContext

SAMPLE_RATE = 24000


class IndicF5Engine(TTSEngine):
    info = EngineInfo(
        id="indicf5",
        kind="tts",
        name="AI4Bharat IndicF5",
        family="indic",
        description="F5-TTS trained on 11 Indian languages by AI4Bharat. Natural Hindi zero-shot cloning from a short reference clip and its transcript.",
        targets=["hi"],
        requires=["transformers", "vocos", "torchdiffeq"],
        install="pip install git+https://github.com/ai4bharat/IndicF5.git 'transformers<4.50'  (indic family interpreter)",
        gated=True,
        badges=["Hindi", "voice cloning", "gated"],
        links={"model": "https://huggingface.co/ai4bharat/IndicF5"},
        params=[ParamSpec("model", "Checkpoint", "text", "ai4bharat/IndicF5")],
    )
    load_params = ("model",)

    def load(self, ctx: TaskContext) -> None:
        from transformers import AutoModel

        ctx.progress(0.02, f"Loading {self.params['model']}…")
        self.model = AutoModel.from_pretrained(self.params["model"], trust_remote_code=True).to(self.device).eval()

    def synthesize(self, items: Sequence[TTSItem], target: str, ctx: TaskContext) -> Iterator[Tuple[TTSItem, float]]:
        import numpy as np
        import soundfile as sf

        for it in items:
            if not it.ref_audio or not (it.ref_text or "").strip():
                ctx.result("tts_error", {"id": it.id, "error": "IndicF5 needs a reference clip and its transcript."})
                continue
            ctx.result("tts_running", {"ids": [it.id]})
            try:
                audio = self.model(it.text, ref_audio_path=it.ref_audio, ref_text=it.ref_text)
                audio = np.asarray(audio)
                if audio.dtype == np.int16:
                    audio = audio.astype(np.float32) / 32768.0
                audio = audio.astype(np.float32).reshape(-1)
            except Exception as exc:
                ctx.result("tts_error", {"id": it.id, "error": str(exc)})
                continue
            os.makedirs(os.path.dirname(it.out_path), exist_ok=True)
            sf.write(it.out_path, audio, SAMPLE_RATE)
            yield it, len(audio) / float(SAMPLE_RATE)
