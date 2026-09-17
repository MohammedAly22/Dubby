"""Context-aware dubbing translation with any Hugging Face instruct LLM.

The default models are unsloth's pre-quantized 4-bit checkpoints. Loaded through
transformers + bitsandbytes they need about a third of the VRAM of 16-bit weights,
so 4B–12B models run on a 16 GB Colab T4 (the unsloth *library* is not required —
it would force a different torch). Segments are generated in batches for speed,
and every batch sees the previous translations as context.

The system prompt is a template: ``{source}``, ``{target}``, ``{style}`` and
``{code_switching}`` are filled in for each language pair, and users can edit it
in the UI.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from dubby import languages as L
from dubby.engines.asr.common import batched
from dubby.engines.base import EngineInfo, ParamSpec, TranslationEngine, option
from dubby.workers.protocol import TaskContext, track

# (model id, label, approximate VRAM in GB, bitsandbytes 4-bit checkpoint)
MODELS: List[Tuple[str, str, float, bool]] = [
    ("unsloth/Qwen3-4B-Instruct-2507-unsloth-bnb-4bit", "Qwen3 4B Instruct 2507 · 4-bit (unsloth)", 4.5, True),
    ("unsloth/Qwen2.5-7B-Instruct-unsloth-bnb-4bit", "Qwen2.5 7B Instruct · 4-bit (unsloth)", 7.0, True),
    ("unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit", "Llama 3.1 8B Instruct · 4-bit (unsloth)", 7.5, True),
    ("unsloth/gemma-3-12b-it-unsloth-bnb-4bit", "Gemma 3 12B · 4-bit (unsloth) — strongest multilingual", 10.5, True),
    ("Qwen/Qwen3-4B-Instruct-2507", "Qwen3 4B Instruct 2507 · 16-bit", 10.0, False),
    ("Qwen/Qwen3.5-9B", "Qwen3.5 9B · 16-bit", 21.0, False),
]
_MODELS = {m[0]: m for m in MODELS}

STYLE: Dict[str, str] = {
    "arz": "Write natural, everyday spoken Egyptian Arabic (عامية مصرية) exactly as an Egyptian voice actor would say it, in Arabic script.",
    "arb": "Write clear, fluent Modern Standard Arabic (الفصحى) suitable for a professional documentary voice-over, in Arabic script.",
    "en": "Write natural, conversational English exactly as a professional voice actor would say it.",
    "zh": "Write natural spoken Simplified Chinese (简体中文) as a professional Mandarin voice actor would say it.",
    "ja": "Write natural spoken Japanese with appropriate politeness, as a professional Japanese voice actor would say it.",
    "hi": "Write natural spoken Hindi in Devanagari script, keeping common English loanwords where Hindi speakers use them.",
}

DEFAULT_SYSTEM_PROMPT = """You are an expert audiovisual translator writing a dubbing script from {source} into {target}.

{style}

Rules:
- Output ONLY the translation of the last message — no quotes, labels, notes or explanations.
- Keep the meaning, tone, emotion and register of the speaker.
- Keep the spoken length close to the source so the line fits the same time slot.
- Write numbers, dates and units the way they are spoken.
- {code_switching}"""

PLACEHOLDERS = ("source", "target", "style", "code_switching", "source_code", "target_code")


def style_for(target: str) -> str:
    return STYLE.get(target) or f"Write natural, idiomatic spoken {L.get(target).prompt_name} as a professional voice actor would say it."


def code_switching_rule(source: str, target: str) -> str:
    if L.iso(target) == "en":
        return (
            "The speaker may mix languages (code-switching, e.g. Egyptian Arabic with English words). "
            "Translate everything into fluent English and keep English words from the source as they are."
        )
    return (
        "Keep code-switched terms exactly as the speaker would say them: English technical words, brand and product names, "
        "acronyms and loanwords that people normally say in English stay in their original Latin spelling. Do not translate "
        "or transliterate them — the text-to-speech voice pronounces them correctly as written."
    )


def render_system_prompt(template: Optional[str], source: str, target: str) -> str:
    """Fill the known ``{placeholders}``; any other braces are left exactly as typed."""
    values = {
        "source": L.get(source).prompt_name,
        "target": L.get(target).prompt_name,
        "style": style_for(target),
        "code_switching": code_switching_rule(source, target),
        "source_code": source,
        "target_code": target,
    }
    text = template if template and template.strip() else DEFAULT_SYSTEM_PROMPT
    return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), text).strip()


_THINK = re.compile(r"<think>.*?</think>", re.S)
_LABEL = re.compile(r"^(translation|translated text|dub|الترجمة)\s*[:：]\s*", re.I)
_SLOT_HINT = re.compile(r"\(\s*spoken slot[^)]*\)\s*", re.I)  # models sometimes echo our timing hint


def clean_output(text: str) -> str:
    text = _THINK.sub("", text).strip()
    text = _SLOT_HINT.sub("", text).strip()
    text = _LABEL.sub("", text).strip()
    return text.strip("\"'“”«»「」").strip()


class LLMTranslator(TranslationEngine):
    info = EngineInfo(
        id="llm",
        kind="translation",
        name="Instruct LLM (context-aware)",
        family="core",
        description="Chat LLMs in 4-bit (unsloth) that fit a 16 GB T4. Batched, uses previous lines as context, keeps code-switched terms for the voice, and the system prompt and temperature are editable.",
        source_languages=list(L.SOURCE_CODES),
        targets=list(L.TARGET_CODES),
        requires=["transformers", "accelerate", "bitsandbytes"],
        install="pip install transformers accelerate bitsandbytes",
        badges=["context-aware", "4-bit", "editable prompt"],
        links={"models": "https://huggingface.co/unsloth", "default": "https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-unsloth-bnb-4bit"},
        vram_gb=MODELS[0][2],
        params=[
            ParamSpec("model", "Model", "select", MODELS[0][0], [option(m[0], m[1]) for m in MODELS], help="4-bit checkpoints need an NVIDIA GPU; 16-bit models also run on CPU (slowly)."),
            ParamSpec("custom_model", "Custom model id", "text", "", help="Any Hugging Face chat model id — overrides the list above"),
            ParamSpec("system_prompt", "System prompt", "textarea", DEFAULT_SYSTEM_PROMPT, help="Placeholders: " + " ".join("{" + p + "}" for p in PLACEHOLDERS)),
            ParamSpec("temperature", "Temperature", "number", 0.2, min=0, max=1.5, step=0.05, help="0 = greedy and repeatable; higher = more varied wording"),
            ParamSpec("top_p", "Top-p", "number", 0.9, min=0.1, max=1, step=0.05, help="Nucleus sampling, used when temperature > 0"),
            ParamSpec("context_lines", "Context lines", "number", 4, min=0, max=16, step=1, help="Previously translated lines shown to the model"),
            ParamSpec("batch_size", "Batch size", "number", 8, min=1, max=32, step=1, help="Segments generated together — faster, uses a little more VRAM"),
            ParamSpec("max_new_tokens", "Max new tokens", "number", 256, min=32, max=1024, step=16),
        ],
    )
    load_params = ("model", "custom_model")

    @staticmethod
    def _model_id(params: Dict[str, Any]) -> str:
        return (params.get("custom_model") or "").strip() or params.get("model") or MODELS[0][0]

    @classmethod
    def required_vram_gb(cls, params: Dict[str, Any], vram_gb: Optional[float] = None) -> Optional[float]:
        entry = _MODELS.get(cls._model_id(params))
        if not entry:
            return None  # custom model: unknown size
        batch = max(1, int(params.get("batch_size") or 1))
        return round(entry[2] + 0.1 * (batch - 1), 1)

    @classmethod
    def needs_cuda(cls, params: Dict[str, Any], vram_gb: Optional[float] = None) -> bool:
        entry = _MODELS.get(cls._model_id(params))
        return bool(entry and entry[3])

    @classmethod
    def preview(cls, params: Dict[str, Any], source: Optional[str], target: Optional[str]) -> Dict[str, str]:
        try:
            return {"system_prompt": render_system_prompt(params.get("system_prompt"), source or "en", target or "arz")}
        except KeyError:
            return {}

    def load(self, ctx: TaskContext) -> None:
        from transformers import AutoModelForCausalLM, AutoTokenizer

        model_id = self._model_id(self.params)
        if self.needs_cuda(self.params) and not self.is_cuda:
            raise RuntimeError(f"{model_id} is a bitsandbytes 4-bit checkpoint and needs a CUDA GPU")
        ctx.progress(0.02, f"Loading {model_id}…")
        self.tok = AutoTokenizer.from_pretrained(model_id)
        self.tok.padding_side = "left"  # decoder-only batching
        if self.tok.pad_token is None:
            self.tok.pad_token = self.tok.eos_token
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id, dtype=self.torch_dtype(), device_map="cuda:0" if self.is_cuda else "cpu"
        ).eval()

    def _prompt(self, system: str, history: List[Tuple[str, str]], n_ctx: int, item: Dict[str, Any]) -> str:
        messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
        for src, tgt in history[-n_ctx:] if n_ctx else []:
            messages += [{"role": "user", "content": src}, {"role": "assistant", "content": tgt}]
        seconds = item.get("duration")
        hint = f"\n\n(spoken slot ≈ {seconds:.1f} s)" if seconds else ""
        messages.append({"role": "user", "content": item["text"].strip() + hint})
        # enable_thinking=False turns off Qwen3's reasoning; other templates ignore it
        return self.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)

    def translate(self, items: Sequence[Dict[str, Any]], source: str, target: str, ctx: TaskContext) -> Iterator[Tuple[str, str]]:
        import torch

        system = render_system_prompt(self.params.get("system_prompt"), source, target)
        temperature = float(self.params.get("temperature") or 0)
        n_ctx = int(self.params.get("context_lines") or 0)
        gen: Dict[str, Any] = dict(max_new_tokens=int(self.params.get("max_new_tokens") or 256), pad_token_id=self.tok.pad_token_id)
        if temperature > 0:
            gen.update(do_sample=True, temperature=temperature, top_p=float(self.params.get("top_p") or 0.9))
        else:
            gen.update(do_sample=False, temperature=None, top_p=None, top_k=None)

        history: List[Tuple[str, str]] = []
        for batch in batched(list(items), max(1, int(self.params.get("batch_size") or 1))):
            prompts = [self._prompt(system, history, n_ctx, it) for it in batch]
            enc = self.tok(prompts, return_tensors="pt", padding=True, add_special_tokens=False).to(self.model.device)
            with track("translation", f"LLM translate · {len(batch)} line{'s' if len(batch) != 1 else ''}"), torch.inference_mode():
                out = self.model.generate(**enc, **gen)
            width = enc["input_ids"].shape[1]
            for it, seq in zip(batch, out):
                text = clean_output(self.tok.decode(seq[width:], skip_special_tokens=True))
                history.append((it["text"].strip(), text))
                yield it["id"], text
