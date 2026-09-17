"""ArzEn-LLM: code-switched Egyptian Arabic → English (Heakl et al., 2024).

A DoRA adapter trained on Egyptian speech transcripts that mix Arabic and English
(BLEU 53.6 to English). The adapter was trained on ``meta-llama/Meta-Llama-3-8B-Instruct``,
which is gated, so we load unsloth's ungated copies of the same weights instead —
the pre-quantized 4-bit one fits a 16 GB Colab T4.

Paper: https://arxiv.org/abs/2406.18120
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from dubby.engines.asr.common import batched
from dubby.engines.base import EngineInfo, ParamSpec, TranslationEngine, quantization_param, resolve_quantization
from dubby.workers.protocol import TaskContext, track

ADAPTER = "ahmedheakl/arazn-llama3-english"
BASES = {
    "4bit": "unsloth/llama-3-8b-Instruct-bnb-4bit",  # pre-quantized: no quantization config needed
    "8bit": "unsloth/llama-3-8b-Instruct",
    "none": "unsloth/llama-3-8b-Instruct",
}
SIZES = {"none": 18.0, "8bit": 10.5, "4bit": 7.0}

# Prompt format from the model card (Llama-3 chat headers, fixed system instruction).
PROMPT = (
    "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
    "Translate the following code-switched Arabic-English-mixed text to English only.<|eot_id|>"
    "<|start_header_id|>user<|end_header_id|>\n\n{text}<|eot_id|>"
    "<|start_header_id|>assistant<|end_header_id|>\n\n"
)


class ArzEnTranslator(TranslationEngine):
    info = EngineInfo(
        id="arzen-llm",
        kind="translation",
        name="ArzEn-LLM (Egyptian → English)",
        family="core",
        description="Llama-3-8B fine-tuned on code-switched Egyptian Arabic speech (ArzEn-LLM, BLEU 53.6 to English). Made for everyday Egyptian talk that mixes in English words. Runs in 4-bit on a 16 GB T4.",
        source_languages=["ar"],
        targets=["en"],
        requires=["transformers", "accelerate", "peft"],
        install="pip install transformers accelerate peft bitsandbytes",
        badges=["Egyptian → English", "code-switching", "T4-friendly"],
        links={"adapter": f"https://huggingface.co/{ADAPTER}", "paper": "https://arxiv.org/abs/2406.18120"},
        vram_gb=SIZES["4bit"],
        params=[
            quantization_param(),
            ParamSpec("batch_size", "Batch size", "number", 8, min=1, max=32, step=1, help="Segments generated together"),
            ParamSpec("max_new_tokens", "Max new tokens", "number", 256, min=32, max=1024, step=16),
        ],
    )
    load_params = ("quantization",)

    @classmethod
    def required_vram_gb(cls, params: Dict[str, Any], vram_gb: Optional[float] = None) -> Optional[float]:
        mode = resolve_quantization(params.get("quantization", "auto"), SIZES, vram_gb)
        return SIZES[mode]

    @classmethod
    def needs_cuda(cls, params: Dict[str, Any], vram_gb: Optional[float] = None) -> bool:
        return resolve_quantization(params.get("quantization", "auto"), SIZES, vram_gb) in ("8bit", "4bit")

    def load(self, ctx: TaskContext) -> None:
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        mode = resolve_quantization(self.params.get("quantization", "auto"), SIZES, self.gpu_vram_gb())
        if mode in ("8bit", "4bit") and not self.is_cuda:
            raise RuntimeError("bitsandbytes quantization requires a CUDA GPU")
        base = BASES[mode]
        ctx.progress(0.02, f"Loading {base} ({mode})…")
        kwargs: Dict[str, Any] = dict(dtype=self.torch_dtype(), device_map="cuda:0" if self.is_cuda else "cpu")
        if mode == "8bit":
            kwargs["quantization_config"] = self.quantization_config("8bit")
        model = AutoModelForCausalLM.from_pretrained(base, **kwargs)
        ctx.progress(0.6, f"Applying the {ADAPTER} adapter…")
        self.model = PeftModel.from_pretrained(model, ADAPTER).eval()
        self.tok = AutoTokenizer.from_pretrained(ADAPTER)
        self.tok.padding_side = "left"
        if self.tok.pad_token is None:
            self.tok.pad_token = self.tok.eos_token
        self.mode = mode

    def translate(self, items: Sequence[Dict[str, Any]], source: str, target: str, ctx: TaskContext) -> Iterator[Tuple[str, str]]:
        import torch

        eot = self.tok.convert_tokens_to_ids("<|eot_id|>")
        for batch in batched(list(items), max(1, int(self.params.get("batch_size") or 1))):
            prompts: List[str] = [PROMPT.format(text=it["text"].strip()) for it in batch]
            enc = self.tok(prompts, return_tensors="pt", padding=True, add_special_tokens=False).to(self.model.device)
            with track("translation", f"ArzEn-LLM translate · {len(batch)} line{'s' if len(batch) != 1 else ''}"), torch.inference_mode():
                out = self.model.generate(
                    **enc,
                    max_new_tokens=int(self.params.get("max_new_tokens") or 256),
                    do_sample=False,
                    temperature=None,
                    top_p=None,
                    eos_token_id=[eot, self.tok.eos_token_id],
                    pad_token_id=self.tok.pad_token_id,
                )
            width = enc["input_ids"].shape[1]
            for it, seq in zip(batch, out):
                text = self.tok.decode(seq[width:], skip_special_tokens=False)
                yield it["id"], text.split("<|eot_id|>")[0].replace("<|end_of_text|>", "").strip()
