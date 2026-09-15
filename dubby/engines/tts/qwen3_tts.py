"""Qwen3-TTS Base (voice cloning, 10 languages). Runs in the `qwen` family (transformers 4.57)."""

from __future__ import annotations

import os
from collections import OrderedDict
from typing import Any, Iterator, List, Sequence, Tuple

from dubby import languages as L
from dubby.engines.asr.common import batched
from dubby.engines.base import EngineInfo, ParamSpec, TTSEngine, TTSItem, option
from dubby.workers.protocol import TaskContext


class Qwen3TTSEngine(TTSEngine):
    info = EngineInfo(
        id="qwen3-tts",
        kind="tts",
        name="Qwen3-TTS",
        family="qwen",
        description="Qwen3-TTS 12Hz Base: expressive zero-shot voice cloning for English, Chinese, Japanese, Spanish, French and Italian (no duration control — clips are fitted at render).",
        targets=["en", "zh", "ja", "es", "fr", "it"],
        requires=["qwen_tts"],
        install="pip install qwen-tts --no-deps && pip install onnxruntime einops sox  (qwen family interpreter)",
        badges=["voice cloning", "expressive"],
        links={"model": "https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base"},
        params=[
            ParamSpec("model", "Checkpoint", "select", "Qwen/Qwen3-TTS-12Hz-1.7B-Base", [
                option("Qwen/Qwen3-TTS-12Hz-1.7B-Base", "Qwen3-TTS 1.7B Base"),
                option("Qwen/Qwen3-TTS-12Hz-0.6B-Base", "Qwen3-TTS 0.6B Base"),
            ]),
            ParamSpec("batch_size", "Batch size", "number", 4, min=1, max=16, step=1),
            ParamSpec("x_vector_only", "Speaker embedding only", "bool", False, help="Clone from the speaker embedding without the reference transcript (less faithful)."),
        ],
    )
    load_params = ("model",)

    def load(self, ctx: TaskContext) -> None:
        from qwen_tts import Qwen3TTSModel

        ctx.progress(0.02, f"Loading {self.params['model']}…")
        self.model = Qwen3TTSModel.from_pretrained(self.params["model"], device_map="cuda:0" if self.is_cuda else "cpu", dtype=self.torch_dtype())
        self._prompts: "OrderedDict[Tuple, Any]" = OrderedDict()

    def _prompt(self, ref_audio: str, ref_text: str | None):
        key = (os.path.abspath(ref_audio), os.path.getmtime(ref_audio), ref_text or "", bool(self.params.get("x_vector_only")))
        if key not in self._prompts:
            self._prompts[key] = self.model.create_voice_clone_prompt(
                ref_audio=ref_audio, ref_text=ref_text or "", x_vector_only_mode=bool(self.params.get("x_vector_only"))
            )
            while len(self._prompts) > 64:
                self._prompts.popitem(last=False)
        return self._prompts[key]

    def _generate(self, batch: List[TTSItem], target: str) -> Tuple[List[Any], int]:
        prompt = self._prompt(batch[0].ref_audio or "", batch[0].ref_text)
        wavs, sr = self.model.generate_voice_clone(
            text=[it.text for it in batch],
            language=[L.get(target).qwen] * len(batch),
            voice_clone_prompt=prompt,
        )
        return list(wavs), int(sr)

    def synthesize(self, items: Sequence[TTSItem], target: str, ctx: TaskContext) -> Iterator[Tuple[TTSItem, float]]:
        import soundfile as sf

        missing = [it for it in items if not it.ref_audio]
        for it in missing:
            ctx.result("tts_error", {"id": it.id, "error": "Qwen3-TTS Base needs a reference voice (clip, upload, preset or auto)."})
        ready = [it for it in items if it.ref_audio]
        # Items sharing one reference voice are batched; per-segment voices go one by one.
        groups: "OrderedDict[str, List[TTSItem]]" = OrderedDict()
        for it in ready:
            groups.setdefault(f"{it.ref_audio}|{it.ref_text}", []).append(it)
        for group in groups.values():
            for batch in batched(group, int(self.params.get("batch_size", 4))):
                ctx.result("tts_running", {"ids": [it.id for it in batch]})
                try:
                    wavs, sr = self._generate(batch, target)
                    pairs = list(zip(batch, wavs))
                except Exception as exc:
                    pairs = []
                    for it in batch:
                        try:
                            w, sr = self._generate([it], target)
                            pairs.append((it, w[0]))
                        except Exception as single_exc:
                            ctx.result("tts_error", {"id": it.id, "error": str(single_exc) or str(exc)})
                for it, wav in pairs:
                    os.makedirs(os.path.dirname(it.out_path), exist_ok=True)
                    sf.write(it.out_path, wav, sr)
                    yield it, len(wav) / float(sr)
