"""AI4Bharat IndicTrans2 English→Hindi (runs in the `indic` family: transformers < 4.50)."""

from __future__ import annotations

from typing import Any, Dict, Iterator, Sequence, Tuple

from dubby.engines.asr.common import batched
from dubby.engines.base import EngineInfo, ParamSpec, TranslationEngine, option
from dubby.workers.protocol import TaskContext


class IndicTrans2Translator(TranslationEngine):
    info = EngineInfo(
        id="indictrans2",
        kind="translation",
        name="AI4Bharat IndicTrans2",
        family="indic",
        description="State-of-the-art English→Indic translation (22 Indian languages). Used here for English→Hindi.",
        source_languages=["en"],
        targets=["hi"],
        requires=["IndicTransToolkit", "transformers"],
        install="pip install IndicTransToolkit 'transformers<4.50' sentencepiece  (indic family interpreter)",
        gated=True,
        badges=["Hindi", "SOTA", "gated"],
        links={"model": "https://huggingface.co/ai4bharat/indictrans2-en-indic-1B"},
        params=[
            ParamSpec("model", "Checkpoint", "select", "ai4bharat/indictrans2-en-indic-1B", [
                option("ai4bharat/indictrans2-en-indic-1B", "IndicTrans2 en→indic 1B"),
                option("ai4bharat/indictrans2-en-indic-dist-200M", "IndicTrans2 en→indic distilled 200M"),
            ]),
            ParamSpec("num_beams", "Beams", "number", 5, min=1, max=8, step=1),
            ParamSpec("batch_size", "Batch size", "number", 16, min=1, max=64, step=1),
        ],
    )
    load_params = ("model",)

    def load(self, ctx: TaskContext) -> None:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        try:
            from IndicTransToolkit.processor import IndicProcessor
        except ImportError:  # older toolkit layout
            from IndicTransToolkit import IndicProcessor

        ctx.progress(0.02, f"Loading {self.params['model']}…")
        self.tok = AutoTokenizer.from_pretrained(self.params["model"], trust_remote_code=True)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(
            self.params["model"], trust_remote_code=True, torch_dtype=self.torch_dtype("float16")
        ).to(self.device).eval()
        self.processor = IndicProcessor(inference=True)

    def translate(self, items: Sequence[Dict[str, Any]], source: str, target: str, ctx: TaskContext) -> Iterator[Tuple[str, str]]:
        import torch

        src, tgt = "eng_Latn", "hin_Deva"
        for batch in batched(list(items), int(self.params["batch_size"])):
            prepared = self.processor.preprocess_batch([it["text"].strip() for it in batch], src_lang=src, tgt_lang=tgt)
            enc = self.tok(prepared, truncation=True, padding="longest", max_length=256, return_tensors="pt", return_attention_mask=True).to(self.device)
            with torch.inference_mode():
                out = self.model.generate(**enc, use_cache=True, min_length=0, max_length=256, num_beams=int(self.params["num_beams"]), num_return_sequences=1)
            decoded = self.tok.batch_decode(out, skip_special_tokens=True, clean_up_tokenization_spaces=True)
            for it, text in zip(batch, self.processor.postprocess_batch(decoded, lang=tgt)):
                yield it["id"], text.strip()
