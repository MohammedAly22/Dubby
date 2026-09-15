from __future__ import annotations

from typing import Any, Dict, Iterator, Sequence, Tuple

from dubby.engines.asr.common import batched
from dubby.engines.base import EngineInfo, ParamSpec, TranslationEngine
from dubby.workers.protocol import TaskContext


class MasrawyTranslator(TranslationEngine):
    info = EngineInfo(
        id="masrawy",
        kind="translation",
        name="oddadmix Masrawy v2",
        family="core",
        description="opus-mt-en-ar fine-tuned on Claude-generated English→Egyptian pairs (chrF 66.7).",
        source_languages=["en"],
        targets=["arz"],
        requires=["transformers", "sentencepiece"],
        install="pip install transformers sentencepiece",
        badges=["Egyptian", "Marian"],
        links={"model": "https://huggingface.co/oddadmix/masrawy-english-arabic-translator-v2"},
        params=[
            ParamSpec("model", "Checkpoint", "text", "oddadmix/masrawy-english-arabic-translator-v2"),
            ParamSpec("num_beams", "Beams", "number", 4, min=1, max=8, step=1),
            ParamSpec("batch_size", "Batch size", "number", 16, min=1, max=64, step=1),
        ],
    )
    load_params = ("model",)

    def load(self, ctx: TaskContext) -> None:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        ctx.progress(0.02, f"Loading {self.params['model']}…")
        self.tok = AutoTokenizer.from_pretrained(self.params["model"])
        self.model = AutoModelForSeq2SeqLM.from_pretrained(self.params["model"]).to(self.device).eval()

    def translate(self, items: Sequence[Dict[str, Any]], source: str, target: str, ctx: TaskContext) -> Iterator[Tuple[str, str]]:
        import torch

        for batch in batched(list(items), int(self.params["batch_size"])):
            enc = self.tok([it["text"].strip() for it in batch], return_tensors="pt", padding=True, truncation=True, max_length=512).to(self.device)
            with torch.inference_mode():
                out = self.model.generate(**enc, num_beams=int(self.params["num_beams"]), max_new_tokens=512)
            for it, seq in zip(batch, out):
                yield it["id"], self.tok.decode(seq, skip_special_tokens=True).strip()
