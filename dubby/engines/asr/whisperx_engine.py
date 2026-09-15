from __future__ import annotations

from typing import Any, Dict, List

from dubby.engines.asr.common import align_words, bundled_silero_vad
from dubby.engines.base import ASREngine, EngineInfo, ParamSpec, option
from dubby.workers.protocol import TaskContext


class WhisperXEngine(ASREngine):
    info = EngineInfo(
        id="whisperx",
        kind="asr",
        name="WhisperX",
        family="core",
        description="faster-whisper batched transcription with wav2vec2 forced alignment for precise word timings.",
        source_languages=["en", "ar"],
        requires=["whisperx"],
        install="pip install whisperx",
        badges=["word timestamps", "fast", "multilingual"],
        links={"code": "https://github.com/m-bain/whisperX"},
        params=[
            ParamSpec("model", "Whisper model", "select", "large-v3-turbo", [
                option("large-v3-turbo"), option("large-v3"), option("medium.en"), option("medium"),
                option("small.en"), option("small"), option("base.en"), option("tiny.en"),
            ]),
            ParamSpec("batch_size", "Batch size", "number", 8, min=1, max=64, step=1),
            ParamSpec("vad_method", "VAD", "select", "silero", [option("silero", "Silero (bundled)"), option("pyannote", "pyannote")]),
            ParamSpec("align_model", "Alignment model", "text", "", help="wav2vec2 checkpoint; empty uses the default for the language."),
        ],
    )
    load_params = ("model", "vad_method")

    def load(self, ctx: TaskContext) -> None:
        import whisperx

        compute_type = "float16" if self.is_cuda else "int8"
        ctx.progress(0.02, f"Loading Whisper {self.params['model']} ({compute_type})…")
        kwargs = {}
        if self.params["vad_method"] == "silero":
            from whisperx.vads import Silero

            kwargs["vad_model"] = bundled_silero_vad(Silero, onset=0.5, chunk_size=30)
        else:
            kwargs["vad_method"] = "pyannote"
        self.model = whisperx.load_model(
            self.params["model"],
            "cuda" if self.is_cuda else "cpu",
            compute_type=compute_type,
            **kwargs,
        )

    def transcribe(self, audio_path: str, language: str, ctx: TaskContext) -> List[Dict[str, Any]]:
        import whisperx

        audio = whisperx.load_audio(audio_path)
        ctx.progress(0.1, "Transcribing speech…")
        result = self.model.transcribe(audio, batch_size=int(self.params["batch_size"]), language=language)
        segments = [
            {"start": float(s["start"]), "end": float(s["end"]), "text": s["text"].strip(), "words": []}
            for s in result["segments"]
            if s.get("text", "").strip()
        ]
        ctx.result("asr_partial", {"segments": segments, "replace": True})
        ctx.progress(0.7, f"Transcribed {len(segments)} segments")
        return align_words(segments, audio, language, self.device, ctx, self.params.get("align_model") or None)
