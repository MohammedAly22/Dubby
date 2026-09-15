"""Qwen3-ASR and QwenCleo-ASR (Egyptian Arabic fine-tune) engines.

Both run on the ``qwen-asr`` runtime, which pins transformers 4.57, so they live
in the ``qwen`` engine family (its own interpreter, see README).
"""

from __future__ import annotations

from typing import Any, Dict, List

from dubby import languages as L
from dubby.engines.asr.common import SR, align_words, batched, clip, load_audio, vad_regions
from dubby.engines.base import ASREngine, EngineInfo, ParamSpec, option
from dubby.workers.protocol import TaskContext

FORCED_ALIGNER = "Qwen/Qwen3-ForcedAligner-0.6B"
# Languages supported by Qwen3-ForcedAligner-0.6B (others fall back to wav2vec2 alignment).
ALIGNER_LANGUAGES = {"en", "zh", "ja", "fr", "es", "it"}


def _items(time_stamps: Any) -> List[Any]:
    if time_stamps is None:
        return []
    items = getattr(time_stamps, "items", time_stamps)
    return list(items() if callable(items) else items)


class Qwen3ASREngine(ASREngine):
    info = EngineInfo(
        id="qwen3-asr",
        kind="asr",
        name="Qwen3-ASR",
        family="qwen",
        description="State-of-the-art open ASR (52 languages). Word timings from Qwen3-ForcedAligner for English, Chinese, Japanese, Spanish, French and Italian; wav2vec2 alignment for Arabic and Hindi.",
        source_languages=["en", "ar", "es", "fr", "it", "hi", "zh", "ja"],
        requires=["qwen_asr", "silero_vad", "whisperx"],
        install="pip install qwen-asr silero-vad whisperx  (qwen family interpreter)",
        badges=["SOTA", "forced aligner"],
        links={"model": "https://huggingface.co/Qwen/Qwen3-ASR-1.7B"},
        params=[
            ParamSpec("model", "Checkpoint", "select", "Qwen/Qwen3-ASR-1.7B", [
                option("Qwen/Qwen3-ASR-1.7B", "Qwen3-ASR 1.7B"), option("Qwen/Qwen3-ASR-0.6B", "Qwen3-ASR 0.6B"),
            ]),
            ParamSpec("use_forced_aligner", "Qwen3 forced aligner", "bool", True, help="Used for en · zh · ja · es · fr · it; other languages use wav2vec2."),
            ParamSpec("batch_size", "Batch size", "number", 8, min=1, max=64, step=1),
            ParamSpec("chunk_seconds", "Max chunk (s)", "number", 30, min=5, max=120, step=1),
        ],
    )
    load_params = ("model", "use_forced_aligner")

    def _device_map(self) -> str:
        return "cuda:0" if self.is_cuda else "cpu"

    def load(self, ctx: TaskContext) -> None:
        from qwen_asr import Qwen3ASRModel

        ctx.progress(0.02, f"Loading {self.params['model']}…")
        kwargs: Dict[str, Any] = dict(
            dtype=self.torch_dtype(),
            device_map=self._device_map(),
            max_inference_batch_size=int(self.params["batch_size"]),
            max_new_tokens=1024,
        )
        if self.params.get("use_forced_aligner"):
            kwargs["forced_aligner"] = FORCED_ALIGNER
            kwargs["forced_aligner_kwargs"] = dict(dtype=self.torch_dtype(), device_map=self._device_map())
        self.model = Qwen3ASRModel.from_pretrained(self.params["model"], **kwargs)

    def postprocess(self, text: str) -> str:
        return text.strip()

    def transcribe(self, audio_path: str, language: str, ctx: TaskContext) -> List[Dict[str, Any]]:
        audio = load_audio(audio_path)
        ctx.progress(0.05, "Detecting speech (VAD)…")
        regions = vad_regions(audio, max_chunk=float(self.params.get("chunk_seconds", 30)))
        lang_name = L.get(language).qwen
        native_ts = (
            bool(self.params.get("use_forced_aligner"))
            and language in ALIGNER_LANGUAGES
            and getattr(self.model, "forced_aligner", True) is not None
        )
        segments: List[Dict[str, Any]] = []
        batches = list(batched(regions, int(self.params.get("batch_size", 8))))
        for bi, batch in enumerate(batches):
            clips = [(clip(audio, s, e), SR) for s, e in batch]
            results = self.model.transcribe(audio=clips, language=lang_name, return_time_stamps=native_ts)
            new = []
            for (s, e), r in zip(batch, results):
                text = self.postprocess(getattr(r, "text", "") or "")
                if not text:
                    continue
                words = []
                if native_ts:
                    for it in _items(getattr(r, "time_stamps", None)):
                        words.append({"text": it.text, "start": s + float(it.start_time), "end": s + float(it.end_time)})
                new.append({"start": s, "end": e, "text": text, "words": words})
            segments.extend(new)
            ctx.result("asr_partial", {"segments": new})
            ctx.progress(0.1 + 0.65 * (bi + 1) / len(batches), f"Transcribed {bi + 1}/{len(batches)} batches")
        if native_ts:
            return segments
        return align_words(segments, audio, language, self.device, ctx)


class QwenCleoEngine(Qwen3ASREngine):
    info = EngineInfo(
        id="qwencleo",
        kind="asr",
        name="QwenCleo-ASR",
        family="qwen",
        description="Qwen3-ASR-1.7B fine-tuned for Egyptian Arabic and Arabic↔English code-switching (≈ half the WER of the base model).",
        source_languages=["ar"],
        requires=["qwen_asr", "qwencleo_asr", "silero_vad", "whisperx"],
        install="pip install qwencleo-asr --no-deps && pip install qwen-asr silero-vad whisperx",
        badges=["Egyptian", "code-switching"],
        links={"model": "https://huggingface.co/mohammedaly22/QwenCleo-ASR", "code": "https://github.com/MohammedAly22/qwencleo-asr"},
        params=[
            ParamSpec("model", "Checkpoint", "text", "mohammedaly22/QwenCleo-ASR"),
            ParamSpec("normalize", "Egyptian normalization", "bool", False, help="Apply QwenCleo's Egyptian-aware text normalization."),
            ParamSpec("batch_size", "Batch size", "number", 8, min=1, max=64, step=1),
            ParamSpec("chunk_seconds", "Max chunk (s)", "number", 20, min=5, max=60, step=1),
        ],
    )
    load_params = ("model",)

    def load(self, ctx: TaskContext) -> None:
        from qwencleo_asr import QwenCleoASR

        ctx.progress(0.02, f"Loading {self.params['model']}…")
        self.cleo = QwenCleoASR(
            self.params["model"],
            device=self._device_map(),
            dtype="bfloat16" if self.is_cuda else "float32",
            max_new_tokens=1024,
        )
        self.model = self.cleo._ensure_model()
        self.model.max_inference_batch_size = int(self.params["batch_size"])

    def postprocess(self, text: str) -> str:
        text = text.strip()
        if self.params.get("normalize"):
            from qwencleo_asr import normalize

            text = normalize(text)
        return text

    def transcribe(self, audio_path: str, language: str, ctx: TaskContext) -> List[Dict[str, Any]]:
        self.params["use_forced_aligner"] = False
        return super().transcribe(audio_path, "ar", ctx)
