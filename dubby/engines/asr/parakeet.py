from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, List

from dubby.engines.asr.common import SR, batched, clip, load_audio, vad_regions
from dubby.engines.base import ASREngine, EngineInfo, ParamSpec, option
from dubby.workers.protocol import TaskContext


class ParakeetEngine(ASREngine):
    info = EngineInfo(
        id="parakeet",
        kind="asr",
        name="NVIDIA Parakeet TDT",
        family="nemo",
        description="NVIDIA FastConformer-TDT (0.6B). Very fast English ASR with native word timestamps from NeMo.",
        source_languages=["en"],
        requires=["nemo", "silero_vad"],
        install="pip install 'nemo_toolkit[asr]' silero-vad  (nemo family interpreter)",
        badges=["fastest", "word timestamps"],
        links={"model": "https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3"},
        params=[
            ParamSpec("model", "Checkpoint", "select", "nvidia/parakeet-tdt-0.6b-v3", [
                option("nvidia/parakeet-tdt-0.6b-v3", "Parakeet TDT 0.6B v3"),
                option("nvidia/parakeet-tdt-0.6b-v2", "Parakeet TDT 0.6B v2 (English)"),
            ]),
            ParamSpec("batch_size", "Batch size", "number", 8, min=1, max=64, step=1),
            ParamSpec("chunk_seconds", "Max chunk (s)", "number", 60, min=10, max=600, step=5),
        ],
    )
    load_params = ("model",)

    def load(self, ctx: TaskContext) -> None:
        import nemo.collections.asr as nemo_asr

        ctx.progress(0.02, f"Loading {self.params['model']}…")
        model = nemo_asr.models.ASRModel.from_pretrained(model_name=self.params["model"])
        self.model = (model.cuda() if self.is_cuda else model.cpu()).eval()

    def transcribe(self, audio_path: str, language: str, ctx: TaskContext) -> List[Dict[str, Any]]:
        import soundfile as sf

        audio = load_audio(audio_path)
        ctx.progress(0.05, "Detecting speech (VAD)…")
        regions = vad_regions(audio, max_chunk=float(self.params["chunk_seconds"]))
        segments: List[Dict[str, Any]] = []
        batches = list(batched(regions, int(self.params["batch_size"])))
        with tempfile.TemporaryDirectory(prefix="dubby-parakeet-") as tmp:
            for bi, batch in enumerate(batches):
                paths = []
                for i, (s, e) in enumerate(batch):
                    p = os.path.join(tmp, f"{bi}_{i}.wav")
                    sf.write(p, clip(audio, s, e), SR)
                    paths.append(p)
                outputs = self.model.transcribe(paths, batch_size=len(paths), timestamps=True)
                new = []
                for (s, e), out in zip(batch, outputs):
                    text = (getattr(out, "text", "") or "").strip()
                    if not text:
                        continue
                    stamps = (getattr(out, "timestamp", None) or {}).get("word", [])
                    words = [{"text": w.get("word", ""), "start": s + float(w["start"]), "end": s + float(w["end"])} for w in stamps]
                    new.append({"start": s, "end": e, "text": text, "words": words})
                segments.extend(new)
                ctx.result("asr_partial", {"segments": new})
                ctx.progress(0.1 + 0.85 * (bi + 1) / len(batches), f"Transcribed {bi + 1}/{len(batches)} batches")
        return segments
