"""oddadmix 50M ChatML translators (Emhotob family).

* ``50M-Egyptian-Translation-v1``  English → Egyptian Arabic   (chrF 52.4)
* ``50M-English-MSA-v1``           English ↔ MSA               (BLEU 46.2)
* ``50M-MSA-Egyptian-v1``          MSA ↔ Egyptian Arabic
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, Sequence, Tuple

from dubby.engines.base import EngineInfo, ParamSpec, TranslationEngine
from dubby.workers.protocol import TaskContext

PAIRS: Dict[Tuple[str, str], Tuple[str, str]] = {
    ("en", "arz"): ("oddadmix/50M-Egyptian-Translation-v1", "أنت مترجم محترف. ترجم النص الإنجليزي إلى اللهجة المصرية العامية."),
    ("en", "arb"): ("oddadmix/50M-English-MSA-v1", "أنت مترجم محترف. ترجم النص الإنجليزي إلى اللغة العربية الفصحى."),
    ("ar", "arb"): ("oddadmix/50M-MSA-Egyptian-v1", "أنت مترجم محترف. ترجم النص من اللهجة المصرية العامية إلى اللغة العربية الفصحى."),
    ("ar", "arz"): ("oddadmix/50M-MSA-Egyptian-v1", "أنت مترجم محترف. ترجم النص من اللغة العربية الفصحى إلى اللهجة المصرية العامية."),
}


class EmhotobTranslator(TranslationEngine):
    info = EngineInfo(
        id="emhotob",
        kind="translation",
        name="oddadmix Emhotob-50M",
        family="core",
        description="Tiny (51.8M) ChatML translators by oddadmix: English→Egyptian, English→MSA and MSA↔Egyptian. Greedy decoding, runs anywhere.",
        source_languages=["en", "ar"],
        targets=["arz", "arb"],
        requires=["transformers"],
        install="pip install transformers",
        badges=["tiny", "Egyptian", "MSA"],
        links={
            "egyptian": "https://huggingface.co/oddadmix/50M-Egyptian-Translation-v1",
            "msa": "https://huggingface.co/oddadmix/50M-English-MSA-v1",
        },
        params=[
            ParamSpec("max_new_tokens", "Max new tokens", "number", 256, min=32, max=1024, step=16),
        ],
    )

    def load(self, ctx: TaskContext) -> None:
        self._models: Dict[str, Any] = {}

    def _get(self, model_id: str, ctx: TaskContext):
        if model_id not in self._models:
            from transformers import AutoModelForCausalLM, AutoTokenizer

            ctx.log(f"Loading {model_id}")
            tok = AutoTokenizer.from_pretrained(model_id)
            model = AutoModelForCausalLM.from_pretrained(model_id, dtype=self.torch_dtype()).to(self.device).eval()
            self._models[model_id] = (tok, model)
        return self._models[model_id]

    def translate(self, items: Sequence[Dict[str, Any]], source: str, target: str, ctx: TaskContext) -> Iterator[Tuple[str, str]]:
        import torch

        model_id, system = PAIRS[(source, target)]
        tok, model = self._get(model_id, ctx)
        for item in items:
            prompt = (
                f"<|im_start|>system\n{system}<|im_end|>\n"
                f"<|im_start|>user\n{item['text'].strip()}<|im_end|>\n"
                f"<|im_start|>assistant\n"
            )
            ids = tok(prompt, return_tensors="pt", add_special_tokens=False).to(model.device)
            if tok.bos_token_id is not None:
                bos = torch.tensor([[tok.bos_token_id]], device=model.device)
                ids["input_ids"] = torch.cat([bos, ids["input_ids"]], dim=1)
                ids["attention_mask"] = torch.cat([torch.ones_like(bos), ids["attention_mask"]], dim=1)
            with torch.inference_mode():
                out = model.generate(
                    **ids,
                    max_new_tokens=int(self.params["max_new_tokens"]),
                    do_sample=False,
                    eos_token_id=tok.eos_token_id,
                    pad_token_id=tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id,
                )
            yield item["id"], tok.decode(out[0, ids["input_ids"].size(1):], skip_special_tokens=True).strip()
