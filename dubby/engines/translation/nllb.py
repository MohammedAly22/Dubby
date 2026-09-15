from __future__ import annotations

from typing import Any, Dict, Iterator, Sequence, Tuple

from dubby import languages as L
from dubby.engines.asr.common import batched
from dubby.engines.base import EngineInfo, ParamSpec, TranslationEngine, option
from dubby.workers.protocol import TaskContext


class NLLBTranslator(TranslationEngine):
    info = EngineInfo(
        id="nllb",
        kind="translation",
        name="Meta NLLB-200",
        family="core",
        description="No Language Left Behind: one model for 200 languages, including Egyptian Arabic (arz_Arab). Fast batched beam search.",
        source_languages=list(L.SOURCE_CODES),
        targets=list(L.TARGET_CODES),
        requires=["transformers", "sentencepiece"],
        install="pip install transformers sentencepiece",
        badges=["200 languages", "fast"],
        links={"model": "https://huggingface.co/facebook/nllb-200-distilled-1.3B"},
        params=[
            ParamSpec("model", "Checkpoint", "select", "facebook/nllb-200-distilled-1.3B", [
                option("facebook/nllb-200-distilled-600M", "NLLB-200 distilled 600M"),
                option("facebook/nllb-200-distilled-1.3B", "NLLB-200 distilled 1.3B"),
                option("facebook/nllb-200-3.3B", "NLLB-200 3.3B"),
            ]),
            ParamSpec("num_beams", "Beams", "number", 4, min=1, max=8, step=1),
            ParamSpec("batch_size", "Batch size", "number", 16, min=1, max=64, step=1),
        ],
    )
    load_params = ("model",)

    def load(self, ctx: TaskContext) -> None:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        ctx.progress(0.02, f"Loading {self.params['model']}…")
        self.tok = AutoTokenizer.from_pretrained(self.params["model"])
        self.model = AutoModelForSeq2SeqLM.from_pretrained(self.params["model"], dtype=self.torch_dtype("float16")).to(self.device).eval()

    def translate(self, items: Sequence[Dict[str, Any]], source: str, target: str, ctx: TaskContext) -> Iterator[Tuple[str, str]]:
        import torch

        self.tok.src_lang = L.get(source).nllb
        forced_bos = self.tok.convert_tokens_to_ids(L.get(target).nllb)
        for batch in batched(list(items), int(self.params["batch_size"])):
            enc = self.tok([it["text"].strip() for it in batch], return_tensors="pt", padding=True, truncation=True, max_length=512).to(self.device)
            with torch.inference_mode():
                out = self.model.generate(**enc, forced_bos_token_id=forced_bos, num_beams=int(self.params["num_beams"]), max_new_tokens=512)
            for it, seq in zip(batch, out):
                yield it["id"], self.tok.decode(seq, skip_special_tokens=True).strip()
