from __future__ import annotations

from typing import Any, Dict, List

from dubby.engines.asr.cohere import ARABIC_MODEL, BASE_MODEL
from dubby.engines.asr.common import bundled_silero_vad
from dubby.engines.base import ASREngine, EngineInfo, ParamSpec, option
from dubby.workers.protocol import TaskContext


class CohereXEngine(ASREngine):
    info = EngineInfo(
        id="coherex",
        kind="asr",
        name="CohereX",
        family="core",
        description="WhisperX-style pipeline around Cohere Transcribe: VAD → Cohere ASR → wav2vec2 forced alignment.",
        source_languages=["ar", "en", "es", "fr", "it", "zh", "ja"],
        requires=["coherex"],
        install="pip install coherex",
        gated=True,
        badges=["Egyptian", "word timestamps", "gated"],
        links={"code": "https://github.com/bakrianoo/cohereX"},
        params=[
            ParamSpec("model", "Checkpoint", "select", ARABIC_MODEL, [
                option(ARABIC_MODEL, "Cohere Transcribe Arabic (07-2026)"),
                option(BASE_MODEL, "Cohere Transcribe (03-2026)"),
            ]),
            ParamSpec("batch_size", "Batch size", "number", 8, min=1, max=32, step=1),
            ParamSpec("chunk_size", "Max chunk (s)", "number", 30, min=5, max=30, step=1),
            ParamSpec("vad_method", "VAD", "select", "silero", [option("silero"), option("pyannote")]),
        ],
    )
    load_params = ("model", "vad_method")

    def _dev(self) -> str:
        return "cuda" if self.is_cuda else "cpu"

    def load(self, ctx: TaskContext) -> None:
        import coherex

        ctx.progress(0.02, f"Loading {self.params['model']} through CohereX…")
        vad_kwargs: dict = {"vad_method": "pyannote"}
        if self.params["vad_method"] == "silero":
            from coherex.vads import Silero

            vad_kwargs = {"vad_model": bundled_silero_vad(Silero, onset=0.5, chunk_size=float(self.params["chunk_size"]))}
        self.pipeline = coherex.load_model(
            model_name=self.params["model"],
            device=self._dev(),
            compute_type="default",
            batch_size=int(self.params["batch_size"]),
            asr_options={"punctuation": True, "max_new_tokens": 448},
            **vad_kwargs,
        )

    def transcribe(self, audio_path: str, language: str, ctx: TaskContext) -> List[Dict[str, Any]]:
        import coherex

        audio = coherex.load_audio(audio_path)
        result = self.pipeline.transcribe(
            audio,
            language=language,
            batch_size=int(self.params["batch_size"]),
            chunk_size=int(self.params["chunk_size"]),
            progress_callback=lambda p: ctx.progress(0.05 + 0.6 * p / 100.0, f"Transcribing… {p:.0f}%"),
        )
        segments = [
            {"start": float(s["start"]), "end": float(s["end"]), "text": s["text"].strip(), "words": []}
            for s in result["segments"]
            if s.get("text", "").strip()
        ]
        ctx.result("asr_partial", {"segments": segments, "replace": True})
        ctx.progress(0.7, "Loading alignment model…")
        try:
            model_a, metadata = coherex.load_align_model(language_code=language, device=self._dev())
            aligned = coherex.align(
                result["segments"], model_a, metadata, audio, self._dev(),
                progress_callback=lambda p: ctx.progress(0.7 + 0.25 * p / 100.0, f"Aligning… {p:.0f}%"),
            )
        except Exception as exc:
            ctx.log(f"CohereX alignment failed ({exc}); using chunk timestamps.", "warning")
            return segments
        return [
            {
                "start": float(s["start"]),
                "end": float(s["end"]),
                "text": s["text"].strip(),
                "words": [{"text": w.get("word", ""), "start": w.get("start"), "end": w.get("end"), "score": w.get("score")} for w in s.get("words", [])],
            }
            for s in aligned["segments"]
            if s.get("text", "").strip()
        ]
