"""Context-aware dubbing translation with any Hugging Face instruct LLM."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterator, List, Sequence, Tuple

from dubby import languages as L
from dubby.engines.base import EngineInfo, ParamSpec, TranslationEngine, option
from dubby.workers.protocol import TaskContext

STYLE: Dict[str, str] = {
    "arz": "Write natural, everyday spoken Egyptian Arabic (عامية مصرية) exactly as an Egyptian voice actor would say it, in Arabic script.",
    "arb": "Write clear, fluent Modern Standard Arabic (الفصحى) suitable for a professional documentary voice-over, in Arabic script.",
    "zh": "Write natural spoken Simplified Chinese (简体中文) as a professional Mandarin voice actor would say it.",
    "ja": "Write natural spoken Japanese with appropriate politeness, as a professional Japanese voice actor would say it.",
    "hi": "Write natural spoken Hindi in Devanagari script, keeping common English loanwords where Hindi speakers use them.",
}


def _system_prompt(source: str, target: str) -> str:
    src, tgt = L.get(source), L.get(target)
    style = STYLE.get(target, f"Write natural, idiomatic spoken {tgt.prompt_name} as a professional voice actor would say it.")
    return (
        f"You are an expert audiovisual translator writing dubbing scripts from {src.prompt_name} into {tgt.prompt_name}. "
        f"{style} Rules: output ONLY the translation, with no quotes, notes or explanations; "
        "keep the meaning, tone and register; keep the spoken length close to the source so it fits the same time slot; "
        "write numbers as words; transliterate names and brands the way they are spoken."
    )


class LLMTranslator(TranslationEngine):
    info = EngineInfo(
        id="llm",
        kind="translation",
        name="Instruct LLM (context-aware)",
        family="core",
        description="Any chat LLM from the Hub (default Qwen3-4B-Instruct-2507). Uses the previous lines as context and targets similar spoken length. Strong for Chinese and Japanese.",
        source_languages=list(L.SOURCE_CODES),
        targets=list(L.TARGET_CODES),
        requires=["transformers", "accelerate"],
        install="pip install transformers accelerate",
        badges=["context-aware", "any pair"],
        links={"model": "https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507"},
        params=[
            ParamSpec("model", "Model", "select", "Qwen/Qwen3-4B-Instruct-2507", [
                option("Qwen/Qwen3-4B-Instruct-2507", "Qwen3 4B Instruct 2507"),
                option("Qwen/Qwen3.5-4B", "Qwen3.5 4B"),
                option("Qwen/Qwen3.5-9B", "Qwen3.5 9B"),
            ]),
            ParamSpec("context_lines", "Context lines", "number", 4, min=0, max=16, step=1),
            ParamSpec("max_new_tokens", "Max new tokens", "number", 256, min=32, max=1024, step=16),
        ],
    )
    load_params = ("model",)

    def load(self, ctx: TaskContext) -> None:
        from transformers import AutoModelForCausalLM, AutoTokenizer

        model_id = self.params["model"]
        ctx.progress(0.02, f"Loading {model_id}…")
        self.tok = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id, dtype=self.torch_dtype(), device_map="cuda:0" if self.is_cuda else "cpu"
        ).eval()

    def translate(self, items: Sequence[Dict[str, Any]], source: str, target: str, ctx: TaskContext) -> Iterator[Tuple[str, str]]:
        import torch

        system = _system_prompt(source, target)
        history: List[Tuple[str, str]] = []
        n_ctx = int(self.params["context_lines"])
        for item in items:
            messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
            for src, tgt in history[-n_ctx:] if n_ctx else []:
                messages += [{"role": "user", "content": src}, {"role": "assistant", "content": tgt}]
            seconds = item.get("duration")
            hint = f"\n\n(spoken slot ≈ {seconds:.1f} s)" if seconds else ""
            messages.append({"role": "user", "content": item["text"].strip() + hint})
            prompt = self.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            enc = self.tok(prompt, return_tensors="pt", add_special_tokens=False).to(self.model.device)
            with torch.inference_mode():
                out = self.model.generate(**enc, max_new_tokens=int(self.params["max_new_tokens"]), do_sample=False)
            text = self.tok.decode(out[0, enc["input_ids"].shape[1]:], skip_special_tokens=True)
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip().strip('"“”「」')
            history.append((item["text"].strip(), text))
            yield item["id"], text
