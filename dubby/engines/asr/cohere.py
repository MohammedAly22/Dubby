"""Cohere Transcribe (base + Arabic fine-tune) via transformers, with VAD + wav2vec2 alignment."""

from __future__ import annotations

from typing import Any, Dict, List

from dubby.engines.asr.common import SR, align_words, batched, clip, load_audio, plain_segments, vad_regions
from dubby.engines.base import ASREngine, EngineInfo, ParamSpec, option
from dubby.workers.protocol import TaskContext

BASE_MODEL = "CohereLabs/cohere-transcribe-03-2026"
ARABIC_MODEL = "CohereLabs/cohere-transcribe-arabic-07-2026"


def _params(default_model: str, max_chunk: int = 30) -> List[ParamSpec]:
    return [
        ParamSpec("model", "Checkpoint", "select", default_model, [
            option(ARABIC_MODEL, "Cohere Transcribe Arabic (07-2026)"),
            option(BASE_MODEL, "Cohere Transcribe (03-2026, 14 langs)"),
        ]),
        ParamSpec("batch_size", "Batch size", "number", 8, min=1, max=32, step=1),
        ParamSpec("chunk_seconds", "Max chunk (s)", "number", max_chunk, min=5, max=30, step=1, help="Cohere's hard limit is 35 s per clip."),
        ParamSpec("punctuation", "Punctuation", "bool", True),
    ]


class CohereTranscribeEngine(ASREngine):
    info = EngineInfo(
        id="cohere-transcribe",
        kind="asr",
        name="Cohere Transcribe",
        family="core",
        description="Cohere's 2B open ASR model (#1 on the Open ASR leaderboard at release). Silero VAD chunks + wav2vec2 word alignment.",
        source_languages=["en", "ar"],
        requires=["transformers", "silero_vad", "whisperx"],
        install="pip install 'transformers>=5.4' silero-vad whisperx",
        gated=True,
        badges=["accurate", "gated"],
        links={"model": "https://huggingface.co/CohereLabs/cohere-transcribe-03-2026"},
        params=_params(BASE_MODEL),
    )
    load_params = ("model",)

    def load(self, ctx: TaskContext) -> None:
        from transformers import AutoProcessor, CohereAsrForConditionalGeneration

        model_id = self.params["model"]
        ctx.progress(0.02, f"Loading {model_id}…")
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = CohereAsrForConditionalGeneration.from_pretrained(model_id, dtype=self.torch_dtype()).to(self.device).eval()

    def _decode_batch(self, waveforms: List[Any], language: str) -> List[str]:
        import torch

        inputs = self.processor(
            waveforms,
            sampling_rate=SR,
            return_tensors="pt",
            language=language,
            punctuation=bool(self.params.get("punctuation", True)),
        )
        chunk_index = inputs.get("audio_chunk_index")
        inputs = inputs.to(self.model.device, dtype=self.model.dtype)
        with torch.inference_mode():
            outputs = self.model.generate(**inputs, max_new_tokens=448)
        texts = self.processor.decode(outputs, skip_special_tokens=True, audio_chunk_index=chunk_index, language=language)
        return [texts] if isinstance(texts, str) else [str(t) for t in texts]

    def transcribe(self, audio_path: str, language: str, ctx: TaskContext) -> List[Dict[str, Any]]:
        audio = load_audio(audio_path)
        ctx.progress(0.05, "Detecting speech (VAD)…")
        regions = vad_regions(audio, max_chunk=min(30.0, float(self.params["chunk_seconds"])))
        segments: List[Dict[str, Any]] = []
        batches = list(batched(regions, int(self.params["batch_size"])))
        for bi, batch in enumerate(batches):
            texts = self._decode_batch([clip(audio, s, e) for s, e in batch], language)
            new = plain_segments(batch, texts)
            segments.extend(new)
            ctx.result("asr_partial", {"segments": new})
            ctx.progress(0.1 + 0.65 * (bi + 1) / len(batches), f"Transcribed {bi + 1}/{len(batches)} batches")
        return align_words(segments, audio, language, self.device, ctx)


class CohereTranscribeArabicEngine(CohereTranscribeEngine):
    info = EngineInfo(
        id="cohere-transcribe-arabic",
        kind="asr",
        name="Cohere Transcribe Arabic",
        family="core",
        description="Cohere Transcribe fine-tuned for Arabic dialects (Egyptian, Gulf, Levantine, Maghrebi), MSA and Arabic-English code-switching.",
        source_languages=["ar", "en"],
        requires=["transformers", "silero_vad", "whisperx"],
        install="pip install 'transformers>=5.4' silero-vad whisperx",
        gated=True,
        badges=["Egyptian", "code-switching", "gated"],
        links={"model": "https://huggingface.co/CohereLabs/cohere-transcribe-arabic-07-2026"},
        params=_params(ARABIC_MODEL),
    )
