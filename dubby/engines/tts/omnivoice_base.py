"""Shared OmniVoice synthesis: voice-clone prompt caching, batching and slot fitting."""

from __future__ import annotations

import os
from collections import OrderedDict
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from dubby import languages as L
from dubby.engines.asr.common import batched
from dubby.engines.base import ParamSpec, TTSEngine, TTSItem, option
from dubby.workers.protocol import TaskContext


def normalize_param() -> ParamSpec:
    """The studio normalizes the text before any TTS engine sees it (``dubby.text``)."""
    return ParamSpec(
        "normalize",
        "Normalize numbers & symbols",
        "bool",
        True,
        help="Numbers, dates, times, money, units, emails and abbreviations become words for the dub language. See each clip's processed text.",
    )


def omnivoice_params(default_model: str, extra: Optional[List[ParamSpec]] = None) -> List[ParamSpec]:
    return [
        ParamSpec("model", "Checkpoint", "text", default_model),
        ParamSpec("fit", "Timing", "select", "duration", [
            option("duration", "Match segment duration"),
            option("natural", "Natural pace (stretch at render)"),
            option("speed", "Fixed speed"),
        ], help="'Match segment duration' asks OmniVoice to speak exactly within the original slot."),
        ParamSpec("speed", "Speed", "number", 1.0, min=0.7, max=1.5, step=0.05),
        ParamSpec("num_step", "Decoding steps", "number", 32, min=4, max=64, step=4),
        ParamSpec("guidance_scale", "Guidance scale", "number", 2.0, min=0.5, max=5.0, step=0.1),
        ParamSpec("batch_size", "Batch size", "number", 4, min=1, max=16, step=1),
        normalize_param(),
        ParamSpec("denoise", "Denoise token", "bool", True),
    ] + (extra or [])


class OmniVoiceEngine(TTSEngine):
    load_params = ("model",)
    prompt_cache_size = 128

    def _device_map(self) -> str:
        return "cuda:0" if self.is_cuda else "cpu"

    def _torch_dtype(self):
        import torch

        return torch.float16 if self.is_cuda else torch.float32

    def load(self, ctx: TaskContext) -> None:
        from omnivoice.models.omnivoice import OmniVoice

        ctx.progress(0.02, f"Loading {self.params['model']}…")
        self.model = OmniVoice.from_pretrained(self.params["model"], device_map=self._device_map(), dtype=self._torch_dtype())
        self._prompts: "OrderedDict[Tuple, Any]" = OrderedDict()

    # ----------------------------------------------------------------- text
    @staticmethod
    def prepare_text(text: str, target: str) -> str:
        # Already normalized by the studio (dubby.text) when "Normalize" is on. Neither VoiceTut's
        # nor OmniVoice's own normalizer runs here, so the processed text shown in the UI is exact.
        return " ".join(text.split())

    # --------------------------------------------------------------- voices
    def _prompt(self, ref_audio: Optional[str], ref_text: Optional[str]):
        if not ref_audio:
            return None
        key = (os.path.abspath(ref_audio), os.path.getmtime(ref_audio), ref_text or "")
        if key not in self._prompts:
            self._prompts[key] = self.model.create_voice_clone_prompt(ref_audio=ref_audio, ref_text=ref_text or None)
            while len(self._prompts) > self.prompt_cache_size:
                self._prompts.popitem(last=False)
        self._prompts.move_to_end(key)
        return self._prompts[key]

    # ------------------------------------------------------------ synthesis
    def _generate(self, batch: Sequence[TTSItem], target: str) -> List[Any]:
        texts = [self.prepare_text(it.text, target) for it in batch]
        prompts = [self._prompt(it.ref_audio, it.ref_text) for it in batch]
        kwargs: Dict[str, Any] = dict(
            text=texts,
            language=[L.get(target).omnivoice] * len(batch),
            normalize_text=False,
            num_step=int(self.params["num_step"]),
            guidance_scale=float(self.params["guidance_scale"]),
            denoise=bool(self.params.get("denoise", True)),
        )
        if all(p is not None for p in prompts):
            kwargs["voice_clone_prompt"] = prompts
        fit = self.params.get("fit", "duration")
        if fit == "duration" and all(it.duration for it in batch):
            kwargs["duration"] = [float(it.duration) for it in batch]
        elif fit == "speed":
            kwargs["speed"] = float(self.params.get("speed", 1.0))
        return self.model.generate(**kwargs)

    def synthesize(self, items: Sequence[TTSItem], target: str, ctx: TaskContext) -> Iterator[Tuple[TTSItem, float]]:
        import soundfile as sf

        mixed_voices = any(it.ref_audio is None for it in items) and any(it.ref_audio for it in items)
        size = 1 if mixed_voices else int(self.params.get("batch_size", 4))
        for batch in batched(list(items), size):
            ctx.result("tts_running", {"ids": [it.id for it in batch]})
            try:
                audios = self._generate(batch, target)
                pairs = list(zip(batch, audios))
            except Exception as exc:
                if len(batch) == 1:
                    ctx.result("tts_error", {"id": batch[0].id, "error": str(exc)})
                    continue
                ctx.log(f"Batch failed ({exc}); retrying one by one.", "warning")
                self._empty_cache()
                pairs = []
                for it in batch:
                    try:
                        pairs.append((it, self._generate([it], target)[0]))
                    except Exception as single_exc:
                        ctx.result("tts_error", {"id": it.id, "error": str(single_exc)})
            for it, wav in pairs:
                os.makedirs(os.path.dirname(it.out_path), exist_ok=True)
                sf.write(it.out_path, wav, self.model.sampling_rate)
                yield it, len(wav) / float(self.model.sampling_rate)

    def _empty_cache(self) -> None:
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
