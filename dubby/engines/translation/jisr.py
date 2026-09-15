from __future__ import annotations

from typing import Any, Dict, Iterator, Sequence, Tuple

from dubby.engines.asr.common import batched
from dubby.engines.base import EngineInfo, ParamSpec, TranslationEngine
from dubby.workers.protocol import TaskContext

TAGS = {"arz": ">>arz<<", "arb": ">>ara<<"}


class JisrTranslator(TranslationEngine):
    info = EngineInfo(
        id="jisr",
        kind="translation",
        name="oddadmix Jisr-MT-50M",
        family="core",
        description="49M Marian model: English → 13 Arabic dialects + MSA selected by tag (>>arz<< Egyptian, >>ara<< MSA). Beam search, batched.",
        source_languages=["en"],
        targets=["arz", "arb"],
        requires=["transformers", "sentencepiece"],
        install="pip install transformers sentencepiece",
        badges=["tiny", "multi-dialect"],
        links={"model": "https://huggingface.co/oddadmix/Jisr-MT-50M-AllDialects"},
        params=[
            ParamSpec("model", "Checkpoint", "text", "oddadmix/Jisr-MT-50M-AllDialects"),
            ParamSpec("num_beams", "Beams", "number", 4, min=1, max=8, step=1),
            ParamSpec("batch_size", "Batch size", "number", 16, min=1, max=64, step=1),
        ],
    )
    load_params = ("model",)

    def load(self, ctx: TaskContext) -> None:
        from transformers import AutoTokenizer, MarianMTModel

        ctx.progress(0.02, f"Loading {self.params['model']}…")
        self.tok = AutoTokenizer.from_pretrained(self.params["model"])
        self.model = MarianMTModel.from_pretrained(self.params["model"]).to(self.device).eval()

    def translate(self, items: Sequence[Dict[str, Any]], source: str, target: str, ctx: TaskContext) -> Iterator[Tuple[str, str]]:
        import torch

        tag = TAGS[target]
        for batch in batched(list(items), int(self.params["batch_size"])):
            enc = self.tok([f"{tag} {it['text'].strip()}" for it in batch], return_tensors="pt", padding=True, truncation=True, max_length=512).to(self.device)
            with torch.inference_mode():
                out = self.model.generate(**enc, num_beams=int(self.params["num_beams"]), max_new_tokens=512)
            for it, seq in zip(batch, out):
                yield it["id"], self.tok.decode(seq, skip_special_tokens=True).strip()
