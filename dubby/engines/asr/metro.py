from __future__ import annotations

from typing import Any, Dict, List

from dubby.engines.asr.common import align_words, batched, clip, load_audio, plain_segments, vad_regions
from dubby.engines.base import ASREngine, EngineInfo, ParamSpec, option
from dubby.workers.protocol import TaskContext


class MetroASREngine(ASREngine):
    info = EngineInfo(
        id="metro-asr",
        kind="asr",
        name="Metro-ASR",
        family="core",
        description="61.6M non-autoregressive CTC Conformer for Egyptian Arabic & code-switching. Runs 40–55× real time on CPU; optional KenLM beam search.",
        source_languages=["ar"],
        requires=["metro_asr", "silero_vad", "whisperx"],
        install="pip install metro-asr silero-vad whisperx   (beam search: pip install 'metro-asr[lm]')",
        badges=["Egyptian", "CPU friendly", "tiny"],
        links={"model": "https://huggingface.co/mohammedaly22/Metro-ASR-Small", "code": "https://github.com/MohammedAly22/metro-asr"},
        params=[
            ParamSpec("model", "Checkpoint", "select", "mohammedaly22/Metro-ASR-Small", [option("mohammedaly22/Metro-ASR-Small", "Metro-Small (61.6M)")]),
            ParamSpec("beam_search", "Beam search + 5-gram LM", "bool", False, help="Downloads the multi-GB KenLM head and needs metro-asr[lm]."),
            ParamSpec("batch_size", "Batch size", "number", 16, min=1, max=64, step=1),
            ParamSpec("chunk_seconds", "Max chunk (s)", "number", 20, min=5, max=60, step=1),
        ],
    )
    load_params = ("model", "beam_search")

    def load(self, ctx: TaskContext) -> None:
        from metro_asr import MetroASREngine as Metro

        ctx.progress(0.02, "Loading Metro-ASR…")
        self.engine = Metro.from_pretrained(
            self.params["model"],
            device="cuda" if self.is_cuda else "cpu",
            lm_path="auto" if self.params.get("beam_search") else None,
        )

    def transcribe(self, audio_path: str, language: str, ctx: TaskContext) -> List[Dict[str, Any]]:
        audio = load_audio(audio_path)
        ctx.progress(0.05, "Detecting speech (VAD)…")
        regions = vad_regions(audio, max_chunk=float(self.params["chunk_seconds"]))
        segments: List[Dict[str, Any]] = []
        batches = list(batched(regions, int(self.params["batch_size"])))
        for bi, batch in enumerate(batches):
            results = self.engine.transcribe_batch([clip(audio, s, e) for s, e in batch], beam_search=bool(self.params.get("beam_search")))
            new = plain_segments(batch, [r.text for r in results])
            segments.extend(new)
            ctx.result("asr_partial", {"segments": new})
            ctx.progress(0.1 + 0.65 * (bi + 1) / len(batches), f"Transcribed {bi + 1}/{len(batches)} batches")
        return align_words(segments, audio, "ar", self.device, ctx)
