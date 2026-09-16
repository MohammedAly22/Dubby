"""Tencent Hunyuan-MT-7B (WMT25 winner) with the model's official prompt templates."""

from __future__ import annotations

from typing import Any, Dict, Iterator, Optional, Sequence, Tuple

from dubby import languages as L
from dubby.engines.base import EngineInfo, ParamSpec, TranslationEngine, option, quantization_param, resolve_quantization
from dubby.workers.protocol import TaskContext

# 7.5B parameters: 16-bit weights alone are ~15 GB, so a 16 GB T4 needs 8-bit or 4-bit.
SIZES = {"none": 18.0, "8bit": 10.0, "4bit": 6.5}


class HunyuanMTTranslator(TranslationEngine):
    info = EngineInfo(
        id="hunyuan-mt",
        kind="translation",
        name="Tencent Hunyuan-MT-7B",
        family="core",
        description="7B translator that won 30 of 31 WMT25 language pairs. Official prompts; strongest open choice for Chinese, Japanese, Spanish, French, Italian, Hindi and MSA.",
        source_languages=list(L.SOURCE_CODES),
        targets=["en", "es", "fr", "it", "hi", "zh", "ja", "arb"],
        requires=["transformers", "accelerate"],
        install="pip install transformers accelerate",
        badges=["WMT25 winner", "33 languages", "4-bit on T4"],
        links={"model": "https://huggingface.co/tencent/Hunyuan-MT-7B"},
        vram_gb=SIZES["none"],
        params=[
            ParamSpec("model", "Checkpoint", "select", "tencent/Hunyuan-MT-7B", [
                option("tencent/Hunyuan-MT-7B", "Hunyuan-MT 7B"),
                option("tencent/Hunyuan-MT-Chimera-7B", "Hunyuan-MT Chimera 7B"),
            ]),
            quantization_param(),
            ParamSpec("sampling", "Use recommended sampling", "bool", False, help="top_k 20 · top_p 0.6 · temperature 0.7 (off = greedy, deterministic)"),
            ParamSpec("max_new_tokens", "Max new tokens", "number", 512, min=64, max=2048, step=64),
        ],
    )
    load_params = ("model", "quantization")

    @classmethod
    def required_vram_gb(cls, params: Dict[str, Any], vram_gb: Optional[float] = None) -> Optional[float]:
        return SIZES[resolve_quantization(params.get("quantization", "auto"), SIZES, vram_gb)]

    @classmethod
    def needs_cuda(cls, params: Dict[str, Any], vram_gb: Optional[float] = None) -> bool:
        return resolve_quantization(params.get("quantization", "auto"), SIZES, vram_gb) in ("8bit", "4bit")

    def load(self, ctx: TaskContext) -> None:
        from transformers import AutoModelForCausalLM, AutoTokenizer

        mode = resolve_quantization(self.params.get("quantization", "auto"), SIZES, self.gpu_vram_gb())
        ctx.progress(0.02, f"Loading {self.params['model']} ({'16-bit' if mode == 'none' else mode})…")
        self.tok = AutoTokenizer.from_pretrained(self.params["model"])
        kwargs: Dict[str, Any] = dict(dtype=self.torch_dtype(), device_map="cuda:0" if self.is_cuda else "cpu")
        if mode != "none":
            kwargs["quantization_config"] = self.quantization_config(mode)
        self.model = AutoModelForCausalLM.from_pretrained(self.params["model"], **kwargs).eval()

    @staticmethod
    def prompt(text: str, source: str, target: str) -> str:
        tgt = L.get(target)
        if "zh" in (L.iso(source), L.iso(target)):
            return f"把下面的文本翻译成{tgt.prompt_name_zh}，不要额外解释。\n\n{text}"
        return f"Translate the following segment into {tgt.prompt_name}, without additional explanation.\n\n{text}"

    def translate(self, items: Sequence[Dict[str, Any]], source: str, target: str, ctx: TaskContext) -> Iterator[Tuple[str, str]]:
        import torch

        sampling = bool(self.params.get("sampling"))
        for item in items:
            messages = [{"role": "user", "content": self.prompt(item["text"].strip(), source, target)}]
            rendered = self.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
            enc = self.tok(rendered, return_tensors="pt", add_special_tokens=False).to(self.model.device)
            gen: Dict[str, Any] = dict(max_new_tokens=int(self.params["max_new_tokens"]), repetition_penalty=1.05)
            gen.update(dict(do_sample=True, top_k=20, top_p=0.6, temperature=0.7) if sampling else dict(do_sample=False))
            with torch.inference_mode():
                out = self.model.generate(**enc, **gen)
            text = self.tok.decode(out[0, enc["input_ids"].shape[1]:], skip_special_tokens=True).strip()
            yield item["id"], text
