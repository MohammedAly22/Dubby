from __future__ import annotations

from typing import Any, Dict

from dubby.engines.asr.common import load_audio
from dubby.engines.base import Engine, EngineInfo, ParamSpec, option
from dubby.workers.protocol import TaskContext


class WhisperLangIdEngine(Engine):
    info = EngineInfo(
        id="whisper-langid",
        kind="langid",
        name="Whisper language ID",
        family="core",
        description="faster-whisper language identification over several speech windows of the video.",
        requires=["faster_whisper"],
        install="pip install faster-whisper",
        badges=["auto-detect"],
        params=[
            ParamSpec("model", "Whisper model", "select", "small", [option("tiny"), option("base"), option("small"), option("medium"), option("large-v3")]),
            ParamSpec("segments", "Windows to vote over", "number", 4, min=1, max=10, step=1),
        ],
    )
    load_params = ("model",)

    def load(self, ctx: TaskContext) -> None:
        from faster_whisper import WhisperModel

        ctx.progress(0.05, f"Loading Whisper {self.params['model']} for language ID…")
        self.model = WhisperModel(self.params["model"], device="cuda" if self.is_cuda else "cpu", compute_type="float16" if self.is_cuda else "int8")

    def detect(self, audio_path: str, ctx: TaskContext) -> Dict[str, Any]:
        audio = load_audio(audio_path)
        ctx.progress(0.4, "Listening to the speech…")
        language, probability, candidates = self.model.detect_language(
            audio=audio,
            vad_filter=True,
            language_detection_segments=int(self.params.get("segments", 4)),
        )
        ctx.progress(1.0, f"Detected {language} ({probability:.0%})")
        return {
            "language": language,
            "probability": float(probability),
            "candidates": [[code, float(p)] for code, p in (candidates or [])[:8]],
        }
